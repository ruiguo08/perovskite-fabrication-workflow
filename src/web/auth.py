"""Local account authentication, authorization, and CSRF protection."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash

from .repository import ROLE_RANK, SessionRecord, UserRecord, UserRole, WebRepository

PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASH.hash("not-a-real-account-password")
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

# Argon2 verification is CPU-heavy (tens to hundreds of milliseconds); it
# must not run on the event loop, and unbounded concurrent hashing would let
# a burst of login attempts exhaust the default thread pool.
_HASHING_CONCURRENCY = asyncio.Semaphore(4)


async def _verify_password(password: str, password_hash: str) -> bool:
    async with _HASHING_CONCURRENCY:
        return await asyncio.to_thread(PASSWORD_HASH.verify, password, password_hash)


async def hash_password_async(password: str, *, username: str | None = None) -> str:
    """Async variant of :func:`hash_password` for request handlers."""
    validate_password(password, username=username)
    async with _HASHING_CONCURRENCY:
        return await asyncio.to_thread(PASSWORD_HASH.hash, password)


@dataclass(frozen=True)
class AuthSettings:
    secure_cookies: bool = True
    session_hours: int = 12
    idle_minutes: int = 120
    login_failure_limit: int = 5
    lockout_minutes: int = 15

    @property
    def session_cookie_name(self) -> str:
        return "__Host-perovskite_session" if self.secure_cookies else "perovskite_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-perovskite_csrf" if self.secure_cookies else "perovskite_csrf"

    @property
    def login_csrf_cookie_name(self) -> str:
        return "__Host-perovskite_login_csrf" if self.secure_cookies else "perovskite_login_csrf"


@dataclass(frozen=True)
class AuthContext:
    user: UserRecord
    session: SessionRecord
    csrf_token: str


@dataclass(frozen=True)
class IssuedSession:
    session_token: str
    csrf_token: str
    expires_at: datetime


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "username must be 3-64 characters using lowercase letters, numbers, '.', '_' or '-'"
        )
    return normalized


def validate_password(password: str, *, username: str | None = None) -> None:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must contain at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"password must not exceed {PASSWORD_MAX_LENGTH} characters")
    if username and username.casefold() in password.casefold():
        raise ValueError("password must not contain the username")


def hash_password(password: str, *, username: str | None = None) -> str:
    validate_password(password, username=username)
    return PASSWORD_HASH.hash(password)


async def authenticate_credentials(
    repository: WebRepository,
    settings: AuthSettings,
    *,
    username: str,
    password: str,
) -> UserRecord | None:
    try:
        normalized_username = normalize_username(username)
    except ValueError:
        await _verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    user = await repository.get_user_by_username(normalized_username)
    if user is None:
        await _verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    now = _utc_now()
    if not user.is_active:
        await _verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if user.locked_until is not None and user.locked_until > now:
        await _verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    lockout_until = now + timedelta(minutes=settings.lockout_minutes)
    attempt_reserved = await repository.reserve_login_attempt(
        user.id,
        attempted_at=now,
        failure_limit=settings.login_failure_limit,
        lockout_until=lockout_until,
    )
    if not attempt_reserved:
        await _verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if await _verify_password(password, user.password_hash):
        await repository.record_successful_login(user.id)
        # Return the record that was verified, not a fresh re-read: a
        # concurrent reset between verification and a re-read would surface
        # the new password_changed_at and defeat the currency predicate in
        # create_session. Role or display-name changes land on the next
        # request.
        return user
    return None


async def issue_session(
    repository: WebRepository,
    settings: AuthSettings,
    *,
    user: UserRecord,
    client_ip: str | None,
    user_agent: str | None,
) -> IssuedSession:
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = _utc_now() + timedelta(hours=settings.session_hours)
    await repository.create_session(
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        user_id=user.id,
        expires_at=expires_at,
        client_ip=client_ip,
        user_agent=user_agent,
        password_changed_at=user.password_changed_at,
    )
    return IssuedSession(
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


async def resolve_auth_context(request: Request) -> AuthContext | None:
    repository: WebRepository = request.app.state.repository
    settings: AuthSettings = request.app.state.auth_settings
    session_token = request.cookies.get(settings.session_cookie_name)
    csrf_token = request.cookies.get(settings.csrf_cookie_name, "")
    if not session_token:
        return None
    session = await repository.get_session(hash_token(session_token))
    if session is None or not session.user.is_active:
        return None
    # Defense in depth for the login/reset race: a session created before
    # the most recent password change must not authenticate even if it
    # escaped the reset's session wipe.
    password_changed_at = session.user.password_changed_at
    if password_changed_at is not None and session.created_at < password_changed_at:
        await repository.delete_session(
            session.token_hash,
            actor_user_id=session.user.id,
            client_ip=_client_ip(request),
        )
        return None
    now = _utc_now()
    idle_deadline = session.last_seen_at + timedelta(minutes=settings.idle_minutes)
    if session.expires_at <= now or idle_deadline <= now:
        await repository.delete_session(
            session.token_hash,
            actor_user_id=session.user.id,
            client_ip=_client_ip(request),
        )
        return None
    if not csrf_token or not hmac.compare_digest(
        hash_token(csrf_token),
        session.csrf_token_hash,
    ):
        return None
    if now - session.last_seen_at >= timedelta(minutes=5):
        await repository.touch_session(session.token_hash, now)
    return AuthContext(user=session.user, session=session, csrf_token=csrf_token)


async def require_user(request: Request) -> AuthContext:
    auth_context: AuthContext | None = getattr(request.state, "auth", None)
    if auth_context is not None:
        return auth_context
    if request.url.path.startswith("/api/"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    next_path = quote(request.url.path, safe="/")
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="authentication required",
        headers={"Location": f"/login?next={next_path}"},
    )


def require_role(minimum_role: UserRole) -> Any:
    async def role_dependency(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> AuthContext:
        if ROLE_RANK[auth_context.user.role] >= ROLE_RANK[minimum_role]:
            return auth_context
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{minimum_role.value} access is required",
        )

    return role_dependency


async def require_csrf(
    request: Request,
    auth_context: Annotated[AuthContext, Depends(require_user)],
) -> None:
    submitted_token = request.headers.get("x-csrf-token", "")
    if not submitted_token:
        form = await request.form()
        submitted_token = str(form.get("csrf_token", ""))
    if submitted_token and hmac.compare_digest(submitted_token, auth_context.csrf_token):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="invalid or missing CSRF token",
    )


def new_login_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def has_valid_login_csrf(request: Request, submitted_token: str) -> bool:
    settings: AuthSettings = request.app.state.auth_settings
    cookie_token = request.cookies.get(settings.login_csrf_cookie_name, "")
    return bool(
        cookie_token
        and submitted_token
        and hmac.compare_digest(cookie_token, submitted_token)
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_safe_internal_path(value: str) -> bool:
    """Reject open-redirect vectors: backslashes, control characters,
    protocol-relative paths, and scheme-prefixed URLs."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return False
    if "\\" in value:
        return False
    if any(ord(char) < 0x20 for char in value):
        return False
    return True


def safe_next_path(value: str | None) -> str:
    """Return a safe app-internal path.

    Returns '/experiments' as a safe fallback for absent or invalid values —
    this is the legacy default. The React GET /login route calls
    ``safe_next_path_or_none`` instead so it can emit a bare /app/login
    without a next parameter.
    """
    if value and _is_safe_internal_path(value):
        return value
    return "/experiments"


def safe_next_path_or_none(value: str | None) -> str | None:
    """Return a safe app-internal path, or None when absent/unsafe.

    None signals 'no destination' so the React GET /login redirect can emit a
    bare /app/login. A valid value starts with '/', is not protocol-relative,
    and carries no backslash or control characters.
    """
    if value and _is_safe_internal_path(value):
        return value
    return None


def set_session_cookies(response: Any, issued: IssuedSession, settings: AuthSettings) -> None:
    max_age = max(int((issued.expires_at - _utc_now()).total_seconds()), 0)
    shared = {
        "secure": settings.secure_cookies,
        "samesite": "strict",
        "path": "/",
        "max_age": max_age,
    }
    response.set_cookie(
        settings.session_cookie_name,
        issued.session_token,
        httponly=True,
        **shared,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        httponly=False,
        **shared,
    )
    response.delete_cookie(
        settings.login_csrf_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookies(response: Any, settings: AuthSettings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=False,
        samesite="strict",
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
