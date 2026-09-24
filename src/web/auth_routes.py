"""Legacy login redirect plus JSON authentication and account-management routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError

from .auth import (
    AuthContext,
    AuthSettings,
    authenticate_credentials,
    clear_session_cookies,
    hash_password_async,
    has_valid_login_csrf,
    issue_session,
    new_login_csrf_token,
    normalize_username,
    require_csrf,
    require_role,
    require_user,
    safe_next_path_or_none,
    set_session_cookies,
)
from .models import (
    LoginRequest,
    SessionInfoResponse,
    UserCreatePayload,
    UserPasswordResetPayload,
    UserResponse,
    UserUpdatePayload,
)
from .repository import UserRole, WebRepository


def create_auth_router(repository: WebRepository) -> APIRouter:
    router = APIRouter()

    @router.get("/login", response_model=None)
    async def login_page(request: Request, next: str | None = None) -> RedirectResponse:
        from urllib.parse import urlencode

        sanitized = safe_next_path_or_none(next)
        if sanitized:
            query = urlencode({"next": sanitized})
            return RedirectResponse(
                url=f"/app/login?{query}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url="/app/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # ------------------------------------------------------------------
    # JSON session and authentication endpoints for the React application
    # ------------------------------------------------------------------

    @router.get("/api/session", response_model=SessionInfoResponse)
    async def session_info(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SessionInfoResponse:
        return SessionInfoResponse(
            id=auth_context.user.id,
            username=auth_context.user.username,
            display_name=auth_context.user.display_name,
            role=auth_context.user.role.value,
            csrf_available=bool(auth_context.csrf_token),
        )

    @router.get("/api/auth/login-csrf", response_model=None)
    async def login_csrf(request: Request) -> JSONResponse:
        """Mint a login CSRF token for a JSON login, using the same cookie."""
        token = new_login_csrf_token()
        settings: AuthSettings = request.app.state.auth_settings
        response = JSONResponse({"login_csrf_token": token})
        response.set_cookie(
            settings.login_csrf_cookie_name,
            token,
            secure=settings.secure_cookies,
            httponly=True,
            samesite="strict",
            path="/",
            max_age=600,
        )
        return response

    @router.post("/api/auth/login", response_model=SessionInfoResponse)
    async def login_json(
        request: Request,
        payload: LoginRequest,
    ) -> JSONResponse:
        """Create a session from JSON credentials with the existing CSRF check."""
        if not has_valid_login_csrf(request, payload.login_csrf):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The login page expired. Please try again.",
            )
        settings: AuthSettings = request.app.state.auth_settings
        user = await authenticate_credentials(
            repository,
            settings,
            username=payload.username,
            password=payload.password,
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Invalid username or password, or the account is "
                    "temporarily locked."
                ),
            )
        try:
            issued = await issue_session(
                repository,
                settings,
                user=user,
                client_ip=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except PermissionError:
            # The credentials were verified against a hash that a concurrent
            # password reset has since replaced; the client must start over.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account credentials changed during sign-in. Please sign in again.",
            ) from None
        response = JSONResponse(
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.value,
                "csrf_available": True,
            }
        )
        set_session_cookies(response, issued, settings)
        return response

    @router.post(
        "/api/auth/logout",
        response_model=None,
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def logout_json(
        request: Request,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> Response:
        await repository.delete_session(
            auth_context.session.token_hash,
            actor_user_id=auth_context.user.id,
            client_ip=_client_ip(request),
        )
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        clear_session_cookies(response, request.app.state.auth_settings)
        return response

    # ------------------------------------------------------------------
    # Administrator JSON account management for the React application
    # ------------------------------------------------------------------

    @router.get(
        "/api/users",
        response_model=list[UserResponse],
    )
    async def list_users_json(
        _auth_context: Annotated[
            AuthContext,
            Depends(require_role(UserRole.ADMINISTRATOR)),
        ],
    ) -> list[UserResponse]:
        return [_user_response(user) for user in await repository.list_users()]

    @router.post(
        "/api/users",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_user_json(
        request: Request,
        payload: UserCreatePayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_role(UserRole.ADMINISTRATOR)),
        ],
    ) -> UserResponse:
        try:
            username = normalize_username(payload.username)
            display_name = payload.display_name.strip()
            if not display_name:
                raise ValueError("display name must not be blank")
            password_hash = await hash_password_async(payload.password, username=username)
            user = await repository.create_user(
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                role=UserRole(payload.role),
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="an account with this username already exists",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _user_response(user)

    @router.patch(
        "/api/users/{user_id}",
        response_model=UserResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_user_json(
        request: Request,
        user_id: int,
        payload: UserUpdatePayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_role(UserRole.ADMINISTRATOR)),
        ],
    ) -> UserResponse:
        try:
            user = await repository.update_user(
                user_id,
                role=UserRole(payload.role),
                is_active=payload.is_active,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _user_response(user)

    @router.post(
        "/api/users/{user_id}/password",
        response_model=None,
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def reset_user_password_json(
        request: Request,
        user_id: int,
        payload: UserPasswordResetPayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_role(UserRole.ADMINISTRATOR)),
        ],
    ) -> Response:
        try:
            user = await repository.get_user(user_id)
            await repository.reset_password(
                user_id,
                password_hash=await hash_password_async(
                    payload.password,
                    username=user.username,
                ),
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _user_response(user: Any) -> UserResponse:
    """Serialize account metadata without exposing authentication state."""

    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role.value,
        is_active=user.is_active,
        locked_until=user.locked_until.isoformat() if user.locked_until else None,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        password_changed_at=user.password_changed_at.isoformat(),
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
