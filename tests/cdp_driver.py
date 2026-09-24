"""Minimal Chrome DevTools Protocol driver used by the run-sheet browser tests.

Implements just enough of the CDP (JSON over a raw RFC 6455 WebSocket) to
launch headless Chrome with a forced 320px layout viewport, drive real mouse
and keyboard input into React controls, and read back the DOM. It also tracks
uncaught page exceptions, console errors, and failed network requests so the
tests fail loudly when the page is not behaving.

This is test-only infrastructure; it never touches production code.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

_CHROME_CANDIDATES = (
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    "/opt/google/chrome/chrome",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
)


def _is_client_abort(params: dict[str, Any]) -> bool:
    """True for browser-cancelled requests, which are benign.

    ``net::ERR_ABORTED`` fires when a navigation replaces an in-flight
    request or the page tears a fetch down (for example the router jumping
    to /app/login after a 401); it is not a server or connectivity failure.
    """

    return str(params.get("errorText", "")) == "net::ERR_ABORTED"


def discover_chrome_executable(    candidates: Sequence[str] | None = None,
    *,
    exists: Callable[[str], bool] | None = None,
) -> str | None:
    """Return the first existing Chrome/Chromium executable.

    Posix locations are checked before Windows paths so a Linux runner can
    never fall back to a Windows-style default, which previously produced
    FileNotFoundError at launch time.
    """

    if candidates is None:
        candidates = _CHROME_CANDIDATES
    if exists is None:

        def _exists(path: str) -> bool:
            if Path(path).is_file():
                return True
            return shutil.which(path) is not None

        exists = _exists
    for candidate in candidates:
        if exists(candidate):
            return candidate
    return None


def _build_frame(payload: bytes, opcode: int = 1) -> bytes:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    mask = os.urandom(4)
    header += mask
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes(header) + masked


def _read_frame(stream: socket.socket) -> bytes:
    header = _read_exact(stream, 2)
    if not header:
        return b""
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exact(stream, 8))[0]
    masked = bool(header[1] & 0x80)
    mask = _read_exact(stream, 4) if masked else None
    payload = _read_exact(stream, length)
    if masked and mask:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    if header[0] & 0x0F == 8:  # close frame
        return b""
    return payload


def _read_exact(stream: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.recv(size - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


def _http_get(url: str, timeout: float = 10.0) -> Any:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname
    port = parsed.port or 80
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    host_header = hostname if port == 80 else f"{hostname}:{port}"
    with socket.create_connection((hostname, port), timeout=timeout) as stream:
        if hostname in ("127.0.0.1", "localhost"):
            stream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        stream.settimeout(timeout)
        stream.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_header}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii")
        )
        response = b""
        while True:
            try:
                chunk = stream.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            response += chunk
    body = response.split(b"\r\n\r\n", 1)[-1]
    return json.loads(body.decode("utf-8"))


def _ws_connect(url: str) -> socket.socket:
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or "/"
    host_header = hostname if port == 80 else f"{hostname}:{port}"
    stream = socket.create_connection((hostname, port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host_header}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    stream.sendall(request.encode("ascii"))
    response = b""
    while b"\r\n\r\n" not in response:
        response += stream.recv(4096)
    if b"101" not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError(f"websocket upgrade failed: {response[:200]!r}")
    return stream


class CdpSession:
    """One CDP WebSocket connection with id-sequenced request/response."""

    def __init__(self, ws_url: str) -> None:
        self._socket = _ws_connect(ws_url)
        self._next_id = 0
        self._events: list[dict[str, Any]] = []
        self._request_methods: dict[str, str] = {}
        self._closed = False

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        if self._closed:
            raise RuntimeError("CDP session is closed")
        self._next_id += 1
        request_id = self._next_id
        message = json.dumps(
            {"id": request_id, "method": method, "params": params or {}}
        ).encode("utf-8")
        self._socket.sendall(_build_frame(message))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = _read_frame(self._socket)
            if not payload:
                continue
            try:
                parsed = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if "id" in parsed and parsed.get("id") == request_id:
                if "error" in parsed:
                    raise RuntimeError(f"CDP {method} error: {parsed['error']}")
                return parsed.get("result", {})
            if "method" in parsed:
                self._events.append(parsed)
        raise TimeoutError(f"CDP {method} timed out")

    def api_post_responses(self) -> list[dict[str, Any]]:
        """Return method-aware response records for captured API requests."""

        results: list[dict[str, Any]] = []
        for event in self._events:
            if event.get("method") == "Network.responseReceived":
                params = event.get("params") or {}
                response = params.get("response") or {}
                url = response.get("url") or ""
                if "/api/" in url:
                    parsed = urllib.parse.urlsplit(url)
                    results.append({
                        "method": self._request_methods.get(params.get("requestId", ""), "GET"),
                        "url": url,
                        "pathname": parsed.path,
                        "status": int(response.get("status") or 0),
                        "request_id": params.get("requestId", ""),
                    })
        return results

    def wait_for_response(
        self,
        *,
        method: str,
        pathname: str,
        status: int,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        """Drain CDP events until exactly one matching response appears.

        Each iteration performs a bounded CDP ``Runtime.evaluate`` call to
        drain newly queued WebSocket events into ``self._events``.

        Consumes exactly one matching event (method + pathname + status).
        More than one match raises ``AssertionError`` with all matching records.
        Nonmatching events (including 500s) remain for ``check_errors()``.
        """

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Drain newly queued WebSocket events by performing a harmless
            # bounded CDP call. Without this, events queued after the last
            # call() would never enter self._events.
            self.call("Runtime.evaluate", {"expression": "1", "returnByValue": True})

            # Scan events — collect all exact matches, keep nonmatches.
            remaining: list[dict[str, Any]] = []
            matches: list[dict[str, Any]] = []
            for event in self._events:
                if event.get("method") == "Network.requestWillBeSent":
                    request = event.get("params", {}).get("request") or {}
                    self._request_methods[
                        event.get("params", {}).get("requestId", "")
                    ] = request.get("method", "GET")
                    remaining.append(event)
                    continue
                if event.get("method") == "Network.responseReceived":
                    params = event.get("params") or {}
                    response = params.get("response") or {}
                    url = response.get("url") or ""
                    parsed = urllib.parse.urlsplit(url)
                    req_method = self._request_methods.get(params.get("requestId", ""), "GET")
                    resp_status = int(response.get("status") or 0)
                    if (
                        req_method == method
                        and parsed.path == pathname
                        and resp_status == status
                    ):
                        matches.append({
                            "method": req_method,
                            "url": url,
                            "pathname": parsed.path,
                            "status": resp_status,
                            "request_id": params.get("requestId", ""),
                        })
                        continue  # consume this match
                remaining.append(event)
            self._events = remaining

            if len(matches) > 1:
                raise AssertionError(
                    f"wait_for_response({method} {pathname} → {status}) "
                    f"found {len(matches)} matching responses; expected exactly 1: "
                    f"{matches}"
                )
            if len(matches) == 1:
                # Now check remaining events for real errors.
                self.check_errors()
                return matches[0]
            # No match yet — check non-response errors only.
            self._check_non_response_errors()
            time.sleep(0.05)

        # Diagnostics: show what we captured.
        all_responses = self.api_post_responses()
        raise TimeoutError(
            f"wait_for_response({method} {pathname} → {status}) did not appear "
            f"within {timeout:.0f}s. Captured responses: {all_responses}"
        )

    def _check_non_response_errors(self) -> None:
        """Check only non-HTTP-response errors (exceptions, console, loading)."""

        remaining: list[dict[str, Any]] = []
        for event in self._events:
            method = event.get("method")
            params = event.get("params") or {}
            if method == "Network.requestWillBeSent":
                request = params.get("request") or {}
                self._request_methods[params.get("requestId", "")] = request.get(
                    "method", "GET"
                )
                remaining.append(event)
                continue
            if method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails") or {}
                text = (
                    details.get("exception", {}).get("description")
                    or details.get("text")
                    or "unknown exception"
                )
                raise RuntimeError(f"uncaught page exception: {text}")
            if method == "Runtime.consoleAPICalled" and params.get("type") == "error":
                args = params.get("args") or []
                text = " ".join(
                    str(arg.get("value") or arg.get("description") or "")
                    for arg in args
                )
                raise RuntimeError(f"page console.error: {text}")
            if method == "Network.loadingFailed":
                if _is_client_abort(params):
                    continue
                raise RuntimeError(
                    f"network request failed: {params.get('errorText', 'failure')}"
                )
            remaining.append(event)
        self._events = remaining

    def check_errors(self) -> None:
        """Raise on uncaught exceptions, console errors, and failed requests.

        No URL-based suppression — use ``wait_for_response`` for expected
        non-2xx responses (e.g., an intentional 401 from a session-expiry
        test).
        """

        remaining: list[dict[str, Any]] = []
        for event in self._events:
            method = event.get("method")
            params = event.get("params") or {}
            if method == "Network.requestWillBeSent":
                request = params.get("request") or {}
                self._request_methods[params.get("requestId", "")] = request.get(
                    "method", "GET"
                )
                remaining.append(event)
                continue
            if method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails") or {}
                text = (
                    details.get("exception", {}).get("description")
                    or details.get("text")
                    or "unknown exception"
                )
                raise RuntimeError(f"uncaught page exception: {text}")
            if method == "Runtime.consoleAPICalled" and params.get("type") == "error":
                args = params.get("args") or []
                text = " ".join(
                    str(arg.get("value") or arg.get("description") or "")
                    for arg in args
                )
                raise RuntimeError(f"page console.error: {text}")
            if method == "Network.loadingFailed":
                if _is_client_abort(params):
                    continue
                raise RuntimeError(
                    f"network request failed: {params.get('errorText', 'failure')}"
                )
            if method == "Network.responseReceived":
                response = params.get("response") or {}
                status = int(response.get("status") or 0)
                url = response.get("url") or ""
                request_method = self._request_methods.get(params.get("requestId", ""), "GET")
                if status >= 500:
                    raise RuntimeError(f"server error {status} for {url}")
                if (
                    "/api/" in url
                    and request_method != "GET"
                    and not (200 <= status < 300)
                    and not (status == 401 and url.endswith("/api/session"))
                ):
                    raise RuntimeError(f"API request failed {status} for {url}")
            remaining.append(event)
        self._events = remaining

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.close()
        except OSError:
            pass


def get_cookies(session: CdpSession, url: str) -> list[dict[str, Any]]:
    result = session.call("Network.getCookies", {"urls": [url]})
    return result.get("cookies", [])


def launch_chrome_with_viewport(
    url: str,
    *,
    width: int = 320,
    height: int = 900,
    user_data_dir: str | None = None,
    chrome: str | None = None,
) -> tuple[subprocess.Popen, CdpSession]:
    """Launch headless Chrome and force the layout viewport to (width, height)."""

    if chrome is None:
        chrome = discover_chrome_executable()
        if chrome is None:
            raise RuntimeError(
                "no Chrome or Chromium executable found; install Google "
                "Chrome to run the browser tests"
            )
    debug_port = _available_port()
    if user_data_dir is None:
        user_data_dir = str(Path(tempfile.mkdtemp()) / "profile")
    process = subprocess.Popen(
        [
            chrome,
            "--headless",
            "--disable-background-networking",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--no-sandbox",
            "--no-first-run",
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={user_data_dir}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    session = None
    try:
        deadline = time.monotonic() + 20
        ws_url = None
        while time.monotonic() < deadline:
            try:
                targets = _http_get(f"http://127.0.0.1:{debug_port}/json")
                for target in targets:
                    if target.get("type") == "page":
                        ws_url = target["webSocketDebuggerUrl"]
                        break
            except Exception:
                pass
            if ws_url:
                break
            time.sleep(0.2)
        if not ws_url:
            raise RuntimeError("Chrome CDP page target did not appear")
        session = CdpSession(ws_url)
        session.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
        # Hide scrollbars so document.documentElement.clientWidth equals the
        # 320px layout viewport exactly (no 15px scrollbar deduction).
        try:
            session.call("Emulation.setScrollbarsHidden", {"hidden": True})
        except RuntimeError:
            pass
        session.call("Page.enable")
        session.call("Runtime.enable")
        session.call("Log.enable")
        session.call("Network.enable")
        # Capture the pathname the server redirect landed on before the SPA
        # boots, so redirect tests never race the router's own navigation
        # (for example the unauthenticated jump to /app/login).
        session.call("Page.enable")
        session.call(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "window.__initialPath = window.location.pathname;"},
        )
        session.call("Page.navigate", {"url": url})
        return process, session
    except Exception:
        if session is not None:
            session.close()
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise


def evaluate(session: CdpSession, expression: str) -> Any:
    result = session.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        },
    )
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        text = (
            details.get("exception", {}).get("description")
            or details.get("text")
            or "evaluation failed"
        )
        raise RuntimeError(f"page evaluation failed: {text}")
    return result.get("result", {}).get("value")


def _is_navigation_race(error: RuntimeError) -> bool:
    """True when a CDP call failed only because the page was navigating.

    ``Runtime.evaluate`` (and other calls bound to an execution context) fail
    with "Inspected target navigated or closed" or a "Cannot find context"
    error while the old document is being torn down for a navigation the test
    itself just triggered. Those races are transient: the next poll lands on
    the new document.
    """

    message = str(error)
    return (
        "Inspected target navigated" in message
        or "Cannot find context" in message
        or "Target closed" in message
    )


def wait_for_expression(
    session: CdpSession,
    expression: str,
    timeout: float = 25.0,
) -> Any:
    """Poll until the expression is truthy, surfacing page errors and JS stalls.

    A CDP call that fails because the page is mid-navigation (the test just
    set ``location.href``) is retried on the next poll instead of failing the
    test; any other evaluation error is a real page failure and propagates.
    """

    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        session.check_errors()
        try:
            last = evaluate(session, expression)
        except RuntimeError as error:
            if _is_navigation_race(error):
                time.sleep(0.1)
                continue
            raise AssertionError(
                f"page failed while waiting for: {expression}\n{error}"
            ) from error
        if last:
            return last
        time.sleep(0.1)
    raise TimeoutError(
        f"condition did not become truthy within {timeout:.0f}s: {expression} "
        f"(last={last!r})"
    )


def click_until(
    session: CdpSession,
    expression: str,
    *,
    verify: str,
    attempts: int = 4,
    verify_timeout: float = 3.0,
) -> None:
    """Click and re-click while the verify expression stays falsy.

    A trusted mouse click can miss when a fixed overlay (for example a toast
    that auto-dismisses seconds later) covers the element or when a re-render
    shifts layout between the coordinate read and the mouse events. Retrying
    the click keeps these cases transient instead of timing out the suite.
    """

    for _ in range(attempts):
        click_center(session, expression)
        try:
            wait_for_expression(session, verify, timeout=verify_timeout)
            return
        except TimeoutError:
            continue
    raise TimeoutError(f"click did not achieve: {verify}")


def click_center(session: CdpSession, expression: str) -> tuple[float, float]:
    """Real trusted mouse click at the center of the element matched by expr."""

    scrolled = evaluate(
        session,
        f"(function() {{ const el = ({expression}); if (!el) return false; "
        "el.scrollIntoView({block: 'center', inline: 'center'}); return true; })()",
    )
    if not scrolled:
        raise AssertionError(f"no element matched for click: {expression}")
    # Wait for the layout to settle after scrolling: re-read the rect until
    # two consecutive reads agree, so a re-render or settling scroll cannot
    # shift the element between the coordinate read and the mouse events.
    rect_expression = (
        f"(function() {{ const el = ({expression}); const r = el.getBoundingClientRect(); "
        "return {x: r.x, y: r.y, width: r.width, height: r.height}; })()"
    )
    rect = evaluate(session, rect_expression)
    previous = None
    for _ in range(10):
        if previous is not None and rect == previous:
            break
        previous = rect
        time.sleep(0.05)
        rect = evaluate(session, rect_expression)
    x = rect["x"] + rect["width"] / 2
    y = rect["y"] + rect["height"] / 2
    for event_type in ("mousePressed", "mouseReleased"):
        session.call(
            "Input.dispatchMouseEvent",
            {
                "type": event_type,
                "x": x,
                "y": y,
                "button": "left",
                "clickCount": 1,
            },
        )
    return x, y


def press_space(session: CdpSession, expression: str) -> None:
    """Focus the element and press the Space key (checkbox fallback)."""

    focused = evaluate(
        session,
        f"(function() {{ const el = ({expression}); if (!el) return false; "
        "el.focus(); return true; })()",
    )
    if not focused:
        raise AssertionError(f"no element matched for space: {expression}")
    for event_type, key, code, text in (
        ("keyDown", " ", "Space", " "),
        ("keyUp", " ", "Space", " "),
    ):
        session.call(
            "Input.dispatchKeyEvent",
            {
                "type": event_type,
                "key": key,
                "code": code,
                "text": text,
                "windowsVirtualKeyCode": 32,
                "nativeVirtualKeyCode": 32,
            },
        )


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def set_file_input(session: CdpSession, expression: str, file_path: str) -> None:
    """Set a real file on an <input type=file> through CDP DOM.setFileInputFiles.

    The genuine file-input path is required so React's onChange receives a real
    FileList (synthetic events cannot populate input.files).
    """
    session.call("DOM.enable")
    document = session.call("DOM.getDocument", {"depth": 0})
    root_node_id = document.get("root", {}).get("nodeId")
    # Resolve the element to a stable nodeId via DOM.querySelector on the root.
    selector = "input[type=file]"
    node = session.call("DOM.querySelector", {"nodeId": root_node_id, "selector": selector})
    node_id = node.get("nodeId")
    if node_id is None or node_id == 0:
        raise AssertionError(f"no file input found for set_file_input (expression: {expression})")
    absolute = str(Path(file_path).resolve())
    session.call("DOM.setFileInputFiles", {"nodeId": node_id, "files": [absolute]})
    # Ensure the change event reaches React listeners.
    evaluate(
        session,
        f"(function() {{ const el = ({expression}); if (!el) return false; "
        "el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()",
    )
