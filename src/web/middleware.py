"""Request safety, logging, and timing middleware for the web application."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
# FastAPI registers its default 400-for-anything handler under the
# *Starlette* HTTPException key, so overriding it requires that exact class.
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import resolve_auth_context

LOGGER = logging.getLogger("perovskite_bo.web")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Transport-level body cap. Two layers cooperate:
#
# 1. The declared Content-Length precheck below rejects oversized requests
#    from the header alone, before any body byte is buffered. The declared
#    length is client-controlled, so this alone is bypassable.
# 2. RequestBodyLimitMiddleware wraps the raw ASGI receive channel and
#    counts the actual body bytes of every http.request message — chunked
#    requests, requests without Content-Length, and requests that lie about
#    their length all hit the same accounting — and terminates with 413 the
#    moment the cap is exceeded, without buffering the remainder.
#
# The reverse proxy (Caddy request_body max_size) stays the authoritative
# hard cap; this closes the direct-uvicorn exposure.
MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024
BODY_BEARING_METHODS = frozenset({"POST", "PUT", "PATCH"})


class RequestBodyLimitMiddleware:
    """ASGI middleware enforcing the request-body cap on actual bytes.

    Wrapping receive (instead of reading the body) keeps the request
    streaming: the consumer still pulls message by message, and the count
    rises with what has actually been delivered. When the running total
    exceeds the cap the receive call raises ``RequestBodyTooLarge``; the
    exception escapes to this middleware (possibly wrapped in an
    ExceptionGroup by anyio task groups inside BaseHTTPMiddleware) and the
    413 response is emitted here. Only the one http.request message that
    crosses the limit is read past it, never the whole body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in BODY_BEARING_METHODS:
            await self.app(scope, receive, send)
            return

        received_bytes = 0

        async def counting_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > MAX_REQUEST_BODY_BYTES:
                    raise RequestBodyTooLarge(received_bytes)
            return message

        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        try:
            await self.app(scope, counting_receive, send)
        except (
            Exception,
            BaseExceptionGroup,
        ) as exc:  # ExceptionGroup derives from BaseException, not Exception
            violation = _find_request_body_violation(exc)
            if violation is None:
                raise
            LOGGER.warning(
                "rejected oversized request body method=%s path=%s client=%s "
                "received_bytes=%d",
                scope["method"],
                scope["path"],
                client_host,
                violation.received_bytes,
            )
            detail = '{"detail":"request body exceeds the allowed size"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": status.HTTP_413_CONTENT_TOO_LARGE,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                        (b"content-length", str(len(detail.encode())).encode()),
                    ],
                }
            )
            await send(
                {"type": "http.response.body", "body": detail.encode()}
            )


def _find_request_body_violation(
    exc: BaseException,
) -> RequestBodyTooLarge | None:
    """Locate a RequestBodyTooLarge inside an exception (group) chain.

    BaseHTTPMiddleware runs the downstream app in an anyio task group, so
    the receive-channel exception can surface wrapped in an ExceptionGroup
    (and FastAPI's body parser may already have converted a sibling into a
    400 HTTPException whose __cause__ still points back at the group).
    """

    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, RequestBodyTooLarge):
            return current
        if isinstance(current, BaseExceptionGroup):
            stack.extend(current.exceptions)
        cause = current.__cause__
        if cause is not None:
            stack.append(cause)
        context = current.__context__
        if context is not None and id(context) not in seen:
            stack.append(context)
    return None


class RequestBodyTooLarge(HTTPException):
    """Raised from the wrapped receive channel when the body cap is exceeded.

    Subclasses HTTPException so FastAPI's request-body parsing re-raises it
    (its generic ``except Exception`` would otherwise convert the failure to
    a misleading 400); the handler registered by ``configure_middleware``
    renders the 413 response.
    """

    def __init__(self, received_bytes: int) -> None:
        super().__init__(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"request body exceeded {MAX_REQUEST_BODY_BYTES} bytes "
                f"({received_bytes} received)"
            ),
        )
        self.received_bytes = received_bytes


def configure_middleware(
    app: FastAPI,
    *,
    allowed_hosts: list[str],
    require_https: bool = False,
) -> None:
    """Install deployment guardrails and centralized request observability."""

    # The receive-channel cap violation surfaces to FastAPI's body parser as
    # an ExceptionGroup (BaseHTTPMiddleware runs the router in an anyio task
    # group), which its generic handler converts to a misleading 400. Both
    # handlers below unwrap the chain first: a direct RequestBodyTooLarge
    # renders as 413, and a 400 whose cause chain still holds the violation
    # is corrected to 413. The response flows back through the observability
    # middleware, so it carries the standard security headers and log entry.
    async def _request_body_too_large_handler(
        request: Request, exc: RequestBodyTooLarge
    ) -> JSONResponse:
        LOGGER.warning(
            "rejected oversized request body method=%s path=%s client=%s "
            "received_bytes=%d",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
            exc.received_bytes,
        )
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "request body exceeds the allowed size"},
        )

    async def _http_exception_with_body_limit_handler(
        request: Request, exc: HTTPException
    ) -> Response:
        if _find_request_body_violation(exc) is not None:
            return await _request_body_too_large_handler(
                request,
                _find_request_body_violation(exc),  # type: ignore[arg-type]
            )
        return await http_exception_handler(request, exc)

    app.add_exception_handler(RequestBodyTooLarge, _request_body_too_large_handler)
    # Replaces the framework's default 400-for-anything handler; falls back
    # to it for every HTTPException not caused by the body cap.
    app.add_exception_handler(
        HTTPException, _http_exception_with_body_limit_handler
    )

    @app.middleware("http")
    async def protect_and_observe(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = perf_counter()
        request.state.auth = (
            None
            if request.url.path.startswith("/app/assets/")
            else await resolve_auth_context(request)
        )
        if not _is_same_origin_request(request):
            LOGGER.warning(
                "rejected cross-site request method=%s path=%s client=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            response = JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "cross-site state-changing requests are not allowed"},
            )
        elif _declares_oversized_body(request):
            LOGGER.warning(
                "rejected oversized request body method=%s path=%s client=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            response = JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": "request body exceeds the allowed size"},
            )
        else:
            try:
                response = await call_next(request)
            except Exception:
                LOGGER.exception(
                    "unhandled request error method=%s path=%s",
                    request.method,
                    request.url.path,
                )
                raise
        duration_ms = (perf_counter() - started_at) * 1_000
        response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; connect-src 'self'; "
            "font-src 'self'; form-action 'self'; frame-ancestors 'none'; "
            "img-src 'self' data:; object-src 'none'; script-src 'self'; "
            "style-src 'self'"
        )
        if request.url.path.startswith("/app/assets/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        if require_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        LOGGER.info(
            "request method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    # These guards wrap the application middleware so rejected hosts and plain
    # HTTP requests never trigger session/database work.
    if require_https:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    # BaseHTTPMiddleware (the @app.middleware decorator above) re-wraps the
    # request's receive channel, so the byte counter must sit OUTSIDE it in
    # the raw ASGI stack to see the original messages.
    app.add_middleware(RequestBodyLimitMiddleware)


def _declares_oversized_body(request: Request) -> bool:
    """True when the request declares a body larger than the accepted cap.

    Only the declared Content-Length is consulted — the body is never read,
    which is the point. Requests without the header (e.g. chunked transfer
    encoding) fall through to the per-endpoint checks.
    """

    if request.method not in BODY_BEARING_METHODS:
        return False
    raw_length = request.headers.get("content-length")
    if raw_length is None:
        return False
    try:
        declared = int(raw_length)
    except ValueError:
        return False
    return declared > MAX_REQUEST_BODY_BYTES


def _is_same_origin_request(request: Request) -> bool:
    if request.method.upper() in SAFE_METHODS:
        return True
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False
    origin = request.headers.get("origin")
    if not origin:
        return True
    supplied = urlsplit(origin)
    expected = urlsplit(str(request.base_url))
    return (supplied.scheme, supplied.netloc) == (expected.scheme, expected.netloc)
