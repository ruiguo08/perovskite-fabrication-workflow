"""Vite dev proxy login/logout smoke test.

The development flow places the browser at the Vite origin
(http://127.0.0.1:<vite-port>) and proxies /api to FastAPI on a different
origin. The proxy rewrites the Origin header to the API origin (see
frontend/vite.config.ts), which is what makes state-changing requests pass the
backend same-origin middleware. This test exercises that real path:

- login through the proxy (login-CSRF cookie + JSON login),
- session read-through,
- logout through the proxy with the session CSRF token,
- CSRF enforcement (missing token is rejected),
- same-origin enforcement (a browser-driven cross-site signal is rejected),
- direct-to-backend foreign Origin is rejected (the production path, no
  proxy) using the same session endpoints.

Requires Node + corepack pnpm and is skipped unless PEROVSKITE_VITE_SMOKE=1
(a deliberate integration gate, like the PostgreSQL tests).
"""

import os
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from web.repository import UserRole

FRONTEND_DIR = REPOSITORY_ROOT / "frontend"
USERNAME = "smoke-admin"
PASSWORD = "correct horse battery staple"
VITE_PORT = int(os.environ.get("PEROVSKITE_VITE_PORT", "5187"))
VITE_ORIGIN = f"http://127.0.0.1:{VITE_PORT}"
FOREIGN_ORIGIN = "http://evil.example"
CURL = shutil.which("curl")


class _CurlResponse:
    def __init__(self, status_code: int, body: str, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    @property
    def text(self) -> str:
        return self._body

    def json(self) -> dict[str, object]:
        return json.loads(self._body)


class _CurlCookies:
    def __init__(self, jar_path: Path) -> None:
        self.jar_path = jar_path

    def get(self, name: str) -> str | None:
        if not self.jar_path.is_file():
            return None
        for line in self.jar_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#HttpOnly_"):
                line = line.removeprefix("#HttpOnly_")
            elif line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) == 7 and fields[5] == name:
                return fields[6]
        return None


class _CurlClient:
    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url
        self._tmp = tempfile.TemporaryDirectory()
        self._jar_path = Path(self._tmp.name) / "cookies.txt"
        self.cookies = _CurlCookies(self._jar_path)
        self.headers: dict[str, str | None] = {}

    def __enter__(self) -> "_CurlClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self._tmp.cleanup()

    def get(self, path: str) -> _CurlResponse:
        return self._request("GET", path)

    def post(self, path: str, *, json: dict[str, object] | None = None) -> _CurlResponse:
        return self._request("POST", path, json_body=json)

    def patch(self, path: str, *, json: dict[str, object] | None = None) -> _CurlResponse:
        return self._request("PATCH", path, json_body=json)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, object] | None = None,
    ) -> _CurlResponse:
        if CURL is None:
            raise RuntimeError("curl is not available")
        marker = "__PEROVSKITE_STATUS__"
        header_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        header_file.close()
        command = [
            CURL,
            "--silent",
            "--show-error",
            "--max-time",
            "15",
            "--cookie",
            str(self._jar_path),
            "--cookie-jar",
            str(self._jar_path),
            "--dump-header",
            header_file.name,
            "--request",
            method,
        ]
        for name, value in self.headers.items():
            if value is not None:
                command.extend(["--header", f"{name}: {value}"])
        if json_body is not None:
            command.extend(
                [
                    "--header",
                    "Content-Type: application/json",
                    "--data-binary",
                    json.dumps(json_body),
                ]
            )
        command.extend(
            [
                "--write-out",
                f"\n{marker}%{{http_code}}",
                self.base_url + path,
            ]
        )
        completed = subprocess.run(
            command,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "curl request failed")
        body, status_text = completed.stdout.rsplit(f"\n{marker}", 1)
        # Parse response headers from the dump file
        response_headers: dict[str, str] = {}
        try:
            header_content = Path(header_file.name).read_text(encoding="utf-8", errors="replace")
            for line in header_content.splitlines():
                if ":" in line and not line.startswith("HTTP"):
                    key, _, value = line.partition(":")
                    response_headers[key.strip().lower()] = value.strip()
        finally:
            Path(header_file.name).unlink(missing_ok=True)
        return _CurlResponse(int(status_text), body, response_headers)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _corepack_command() -> list[str] | None:
    corepack = shutil.which("corepack")
    if corepack is None:
        return None
    if os.name == "nt":
        return ["cmd", "/c", corepack, "pnpm"]
    return [corepack, "pnpm"]


def _wait_for(
    url: str,
    timeout_seconds: float = 90,
    *,
    process: subprocess.Popen[bytes] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        try:
            if CURL is None:
                return False
            completed = subprocess.run(
                [
                    CURL,
                    "--silent",
                    "--output",
                    os.devnull,
                    "--write-out",
                    "%{http_code}",
                    "--max-time",
                    "2",
                    url,
                ],
                capture_output=True,
                encoding="ascii",
                errors="replace",
                timeout=5,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout == "200":
                return True
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(0.5)
    return False


@unittest.skipUnless(
    os.environ.get("PEROVSKITE_VITE_SMOKE") == "1",
    "set PEROVSKITE_VITE_SMOKE=1 to run the Vite proxy smoke test",
)
class ViteProxySmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (FRONTEND_DIR / "node_modules").is_dir():
            raise unittest.SkipTest("frontend dependencies are not installed")
        cls._pnpm = _corepack_command()
        if cls._pnpm is None:
            raise unittest.SkipTest("corepack pnpm is not available")
        if CURL is None:
            raise unittest.SkipTest("curl is not available")

        cls._tmp = tempfile.TemporaryDirectory()
        database_path = Path(cls._tmp.name) / "smoke.sqlite3"
        backend_port = _free_port()
        cls.backend_origin = f"http://127.0.0.1:{backend_port}"

        runner = Path(cls._tmp.name) / "run_backend.py"
        runner.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(REPOSITORY_ROOT / 'src')!r})\n"
            f"sys.path.insert(0, {str(REPOSITORY_ROOT)!r})\n"
            "import uvicorn\n"
            "from web import create_app\n"
            "from web.repository import UserRole\n"
            f"app = create_app(Path({str(database_path)!r}), secure_cookies=False,\n"
            "                create_schema=True,\n"
            f"                _test_user=({USERNAME!r}, {PASSWORD!r}, UserRole.ADMINISTRATOR))\n"
            "from tests.layout_fixtures import STANDARD_LAYOUTS\n"
            "import asyncio\n"
            "from decimal import Decimal\n"
            "asyncio.run(app.state.database.initialize())\n"
            "from web.services.catalog_service import create_device_layout\n"
            "async def _seed_layouts() -> None:\n"
            "    async with app.state.database.engine.begin() as connection:\n"
            "        for layout in STANDARD_LAYOUTS:\n"
            "            try:\n"
            "                await create_device_layout(\n"
            "                    connection, code=layout['code'], version=layout['version'],\n"
            "                    substrate_width_mm=Decimal(layout['substrate_width_mm']),\n"
            "                    substrate_length_mm=Decimal(layout['substrate_length_mm']),\n"
            "                    devices_per_substrate=layout['devices_per_substrate'],\n"
            "                    device_active_area_cm2=Decimal(layout['device_active_area_cm2']),\n"
            "                    total_active_area_cm2=Decimal(layout['total_active_area_cm2']),\n"
            "                    description=layout['description'])\n"
            "            except ValueError:\n"
            "                pass\n"
            "asyncio.run(_seed_layouts())\n"
            f"uvicorn.run(app, host='127.0.0.1', port={backend_port}, log_level='warning')\n",
            encoding="utf-8",
        )
        backend_log = Path(cls._tmp.name) / "backend.log"
        cls._backend_log_handle = backend_log.open("w")
        cls._backend = subprocess.Popen(
            [sys.executable, str(runner)],
            stdout=cls._backend_log_handle,
            stderr=subprocess.STDOUT,
        )
        if not _wait_for(f"{cls.backend_origin}/healthz", process=cls._backend):
            cls._shutdown()
            raise RuntimeError(
                f"FastAPI backend did not become ready (exit code "
                f"{cls._backend.returncode}); runner:\n"
                + runner.read_text(encoding="utf-8")
                + "\nlog:\n"
                + backend_log.read_text(encoding="utf-8")[-2000:]
            )

        vite_log = Path(cls._tmp.name) / "vite.log"
        cls._vite_log_handle = vite_log.open("w")
        cls._vite = subprocess.Popen(
            [
                *cls._pnpm,
                "dev",
                "--host",
                "127.0.0.1",
                "--port",
                str(VITE_PORT),
                "--strictPort",
            ],
            cwd=FRONTEND_DIR,
            env={
                **os.environ,
                "VITE_PROXY_TARGET": cls.backend_origin,
                "BROWSER": "none",
            },
            stdout=cls._vite_log_handle,
            stderr=subprocess.STDOUT,
        )
        # /healthz through the Vite port only returns 200 once both the Vite
        # dev server and its proxy to the backend are live.
        if not _wait_for(
            f"{VITE_ORIGIN}/healthz", process=cls._vite
        ):
            cls._shutdown()
            raise RuntimeError(
                "Vite dev proxy did not become ready; log: "
                + vite_log.read_text(encoding="utf-8")[-2000:]
            )

    @classmethod
    def _shutdown(cls) -> None:
        for process in (getattr(cls, "_vite", None), getattr(cls, "_backend", None)):
            if process is None or process.poll() is not None:
                continue
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                process.wait(timeout=10)
            else:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for handle_name in ("_vite_log_handle", "_backend_log_handle"):
            handle = getattr(cls, handle_name, None)
            if handle is not None and not handle.closed:
                handle.close()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._shutdown()
        deadline = time.monotonic() + 5
        while True:
            try:
                cls._tmp.cleanup()
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)

    def _login(self, client: _CurlClient) -> None:
        csrf = client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200)
        token = csrf.json()["login_csrf_token"]
        login = client.post(
            "/api/auth/login",
            json={
                "username": USERNAME,
                "password": PASSWORD,
                "login_csrf": token,
            },
        )
        self.assertEqual(login.status_code, 200)
        self.assertIsNotNone(client.cookies.get("perovskite_session"))

    def test_login_and_logout_through_vite_proxy(self) -> None:
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            client.headers["Origin"] = VITE_ORIGIN
            self._login(client)
            session = client.get("/api/session")
            self.assertEqual(session.status_code, 200)
            self.assertEqual(session.json()["username"], USERNAME)

            client.headers["X-CSRF-Token"] = client.cookies.get(
                "perovskite_csrf"
            )
            logout = client.post("/api/auth/logout")
            self.assertEqual(logout.status_code, 204)
            self.assertEqual(client.get("/api/session").status_code, 401)

    def test_missing_csrf_token_is_rejected_through_proxy(self) -> None:
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            client.headers["Origin"] = VITE_ORIGIN
            self._login(client)
            logout = client.post("/api/auth/logout")
            self.assertEqual(logout.status_code, 403)

    def test_cross_site_signal_is_rejected_through_proxy(self) -> None:
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            self._login(client)
            client.headers["X-CSRF-Token"] = client.cookies.get(
                "perovskite_csrf"
            )
            client.headers["Sec-Fetch-Site"] = "cross-site"
            logout = client.post("/api/auth/logout")
            self.assertEqual(logout.status_code, 403)

    def test_foreign_origin_is_rejected_direct_to_backend(self) -> None:
        # Without the dev proxy (the production path), a mismatched Origin is
        # rejected by the same-origin middleware.
        with _CurlClient(base_url=self.backend_origin) as client:
            client.headers["Origin"] = FOREIGN_ORIGIN
            csrf = client.get("/api/auth/login-csrf")
            self.assertEqual(csrf.status_code, 200)
            token = csrf.json()["login_csrf_token"]
            login = client.post(
                "/api/auth/login",
                json={
                    "username": USERNAME,
                    "password": PASSWORD,
                    "login_csrf": token,
                },
            )
            self.assertEqual(login.status_code, 403)

    def _seed_experiment_and_batch(self, client: _CurlClient) -> tuple[int, int]:
        """Create a valid experiment and fabrication batch for export testing."""
        from tests.test_web_app import releasable_result_recipe
        client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")
        created = client.post("/api/experiments", json={"recipe": releasable_result_recipe()})
        self.assertEqual(created.status_code, 201, created.text)
        experiment_id = created.json()["id"]
        for status in ("pending_approval", "approved", "released"):
            transition = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": status},
            )
            self.assertEqual(transition.status_code, 204)
        batch = client.post(
            f"/api/experiments/{experiment_id}/fabrication-batches",
            json={},
        )
        self.assertEqual(batch.status_code, 201, batch.text)
        batch_id = batch.json()["id"]
        for status in ("ready", "in_progress"):
            resp = client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={"status": status},
            )
            self.assertEqual(resp.status_code, 204)
        return experiment_id, batch_id

    def test_experiment_export_is_proxied_to_backend(self) -> None:
        """Experiment export JSON must reach the backend through the Vite proxy."""
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            client.headers["Origin"] = VITE_ORIGIN
            self._login(client)
            experiment_id, _ = self._seed_experiment_and_batch(client)
            response = client.get(f"/experiments/{experiment_id}/export.json")
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response.headers.get("content-disposition", ""))
            self.assertIn("application/json", response.headers.get("content-type", ""))
            body = response.json()
            self.assertIn("schema_version", body)

    def test_batch_export_is_proxied_to_backend(self) -> None:
        """Fabrication-batch export JSON must reach the backend through the Vite proxy."""
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            client.headers["Origin"] = VITE_ORIGIN
            self._login(client)
            experiment_id, batch_id = self._seed_experiment_and_batch(client)
            response = client.get(
                f"/experiments/{experiment_id}/batches/{batch_id}/export.json"
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response.headers.get("content-disposition", ""))
            self.assertIn("application/json", response.headers.get("content-type", ""))
            body = response.json()
            self.assertIn("schema_version", body)

    def test_app_experiments_is_not_proxied(self) -> None:
        """/app/experiments/1 must be served by Vite/React, not the backend."""
        with _CurlClient(base_url=VITE_ORIGIN) as client:
            response = client.get("/app/experiments/1")
            # Vite serves the SPA index.html for any /app/... path.
            self.assertEqual(response.status_code, 200)
            self.assertIn("<div id=\"root\"></div>", response._body)


if __name__ == "__main__":
    unittest.main()
