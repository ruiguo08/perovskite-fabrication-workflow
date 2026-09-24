"""FastAPI application factory for the laboratory web interface."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette import status as _status

from .auth import AuthSettings, hash_password, normalize_username, safe_next_path
from .auth_routes import create_auth_router
from .database import Database, is_postgresql_url, normalize_database_url
from .middleware import configure_middleware
from .repository import UserRole, WebRepository
from .routes import create_router
from .version import __version__

STATIC_APP_DIR = Path(__file__).parent / "static-app"
DEFAULT_EXPERIMENT_SERIES_ID = "usual_v1"


def create_app(
    database_url: str | Path,
    *,
    campaign_id: str | None = None,
    secure_cookies: bool | None = None,
    create_schema: bool | None = None,
    _test_user: tuple[str, str, UserRole] | None = None,
) -> FastAPI:
    """Create the authenticated web app around an async relational repository."""

    configured_campaign_id = campaign_id or os.environ.get("PEROVSKITE_CAMPAIGN_ID")
    if _test_user is not None and not configured_campaign_id:
        configured_campaign_id = DEFAULT_EXPERIMENT_SERIES_ID

    database = Database(
        database_url,
        create_schema=(
            isinstance(database_url, Path) if create_schema is None else create_schema
        ),
    )
    is_postgresql = is_postgresql_url(database.url)
    if _test_user is not None and is_postgresql:
        raise ValueError("test users may only be bootstrapped in an isolated SQLite database")
    repository = WebRepository(database)
    auth_settings = AuthSettings(
        secure_cookies=is_postgresql if secure_cookies is None else secure_cookies,
        session_hours=_positive_int_env("PEROVSKITE_SESSION_HOURS", 12),
        idle_minutes=_positive_int_env("PEROVSKITE_SESSION_IDLE_MINUTES", 120),
        login_failure_limit=_positive_int_env("PEROVSKITE_LOGIN_FAILURE_LIMIT", 5),
        lockout_minutes=_positive_int_env("PEROVSKITE_LOGIN_LOCKOUT_MINUTES", 15),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await database.initialize()
        if _test_user is not None:
            await _create_test_user(repository, _test_user)
            if configured_campaign_id:
                try:
                    await repository.get_campaign(configured_campaign_id)
                except KeyError:
                    user = await repository.get_user_by_username(
                        normalize_username(_test_user[0])
                    )
                    await repository.create_campaign(
                        code=configured_campaign_id,
                        display_name="Test campaign",
                        description="Automatically created for isolated tests",
                        actor_user_id=user.id if user else None,
                    )
        try:
            yield
        finally:
            await database.dispose()

    is_docs_enabled = not is_postgresql or _boolean_env("PEROVSKITE_ENABLE_DOCS", False)
    app = FastAPI(
        title="Perovskite Solar Cell Fabrication Workflow",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if is_docs_enabled else None,
        redoc_url="/redoc" if is_docs_enabled else None,
        openapi_url="/openapi.json" if is_docs_enabled else None,
    )
    app.state.database = database
    app.state.repository = repository
    app.state.auth_settings = auth_settings

    @app.get("/healthz", include_in_schema=False)
    async def healthcheck() -> dict[str, str]:
        async with database.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    allowed_hosts = [
        host.strip()
        for host in os.environ.get(
            "PEROVSKITE_ALLOWED_HOSTS",
            "127.0.0.1,localhost,[::1],testserver",
        ).split(",")
        if host.strip()
    ]
    configure_middleware(
        app,
        allowed_hosts=allowed_hosts,
        require_https=(
            is_postgresql
            and _boolean_env("PEROVSKITE_REQUIRE_HTTPS", True)
        ),
    )
    default_campaign_id = configured_campaign_id
    _register_legacy_redirects(app)
    app.include_router(create_auth_router(repository))
    app.include_router(
        create_router(repository, default_campaign_id=default_campaign_id)
    )
    _mount_spa(app)
    return app


def _register_legacy_redirects(app: FastAPI) -> None:
    """Register 303 redirects from legacy GET URLs to React equivalents.

    These routes do not require authentication — React RequireAuth and the JSON
    APIs handle authentication, role checks, ownership, and 404 isolation.
    Registered before the main router so they match first.
    """

    @app.get("/", include_in_schema=False)
    async def _root() -> RedirectResponse:
        return RedirectResponse(url="/app/", status_code=_status.HTTP_303_SEE_OTHER)

    @app.get("/experiments", include_in_schema=False)
    async def _experiments() -> RedirectResponse:
        return RedirectResponse(url="/app/experiments", status_code=_status.HTTP_303_SEE_OTHER)

    @app.get("/experiments/new", include_in_schema=False)
    async def _new_experiment() -> RedirectResponse:
        return RedirectResponse(url="/app/experiments/new", status_code=_status.HTTP_303_SEE_OTHER)

    @app.get("/experiments/{experiment_id}", include_in_schema=False)
    async def _experiment_detail(experiment_id: int) -> RedirectResponse:
        return RedirectResponse(
            url=f"/app/experiments/{experiment_id}",
            status_code=_status.HTTP_303_SEE_OTHER,
        )

    @app.get("/experiments/{experiment_id}/upload", include_in_schema=False)
    async def _upload(experiment_id: int) -> RedirectResponse:
        return RedirectResponse(
            url=f"/app/experiments/{experiment_id}/upload",
            status_code=_status.HTTP_303_SEE_OTHER,
        )

    @app.get(
        "/experiments/{experiment_id}/results/{file_id}/analysis",
        include_in_schema=False,
    )
    async def _result_analysis(experiment_id: int, file_id: int) -> RedirectResponse:
        return RedirectResponse(
            url=f"/app/results/{file_id}",
            status_code=_status.HTTP_303_SEE_OTHER,
        )

    @app.get("/experiments/{experiment_id}/batches/{batch_id}", include_in_schema=False)
    async def _batch_dashboard(experiment_id: int, batch_id: int) -> RedirectResponse:
        return RedirectResponse(
            url=f"/app/experiments/{experiment_id}/batches/{batch_id}",
            status_code=_status.HTTP_303_SEE_OTHER,
        )

    @app.get("/campaigns", include_in_schema=False)
    async def _campaigns() -> RedirectResponse:
        return RedirectResponse(url="/app/campaigns", status_code=_status.HTTP_303_SEE_OTHER)

    @app.get("/materials", include_in_schema=False)
    async def _materials() -> RedirectResponse:
        return RedirectResponse(url="/app/materials", status_code=_status.HTTP_303_SEE_OTHER)

    @app.get("/admin/users", include_in_schema=False)
    async def _admin_users() -> RedirectResponse:
        return RedirectResponse(url="/app/users", status_code=_status.HTTP_303_SEE_OTHER)


def _mount_spa(app: FastAPI) -> None:
    """Serve the compiled React application under /app/ when it is present.

    The built assets travel inside the Python package (method A in
    docs/react-migration.md), so the routes register only when the build output
    exists. /app/assets/* serves the versioned bundle with immutable cache
    headers; /app and /app/{path:path} return the SPA entry point for
    client-side routes. /api, /healthz, and export downloads keep their own
    behavior and are never shadowed.
    """

    index_html = STATIC_APP_DIR / "index.html"
    if not index_html.is_file():
        return
    assets_dir = STATIC_APP_DIR / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/app/assets",
            StaticFiles(directory=str(assets_dir)),
            name="app-assets",
        )

    @app.get("/app", include_in_schema=False)
    @app.get("/app/{path:path}", include_in_schema=False)
    async def spa_entry(path: str = "") -> FileResponse:
        return FileResponse(index_html, media_type="text/html")


def main() -> None:
    """Run the app behind an HTTPS reverse proxy on the same server."""

    logging.basicConfig(
        level=os.environ.get("PEROVSKITE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_url = os.environ.get("PEROVSKITE_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("PEROVSKITE_DATABASE_URL must point to PostgreSQL")
    normalized_url = normalize_database_url(database_url)
    if not is_postgresql_url(normalized_url):
        raise RuntimeError("the networked web application requires PostgreSQL")
    port = int(os.environ.get("PEROVSKITE_WEB_PORT", "8000"))
    uvicorn.run(
        create_app(database_url),
        host="127.0.0.1",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get(
            "PEROVSKITE_FORWARDED_ALLOW_IPS",
            "127.0.0.1,::1",
        ),
    )


async def _create_test_user(
    repository: WebRepository,
    test_user: tuple[str, str, UserRole],
) -> None:
    username, password, role = test_user
    normalized_username = normalize_username(username)
    if await repository.get_user_by_username(normalized_username) is not None:
        return
    await repository.create_user(
        username=normalized_username,
        display_name="Test User",
        password_hash=hash_password(password, username=normalized_username),
        role=role,
    )


def _boolean_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _positive_int_env(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


if __name__ == "__main__":
    main()
