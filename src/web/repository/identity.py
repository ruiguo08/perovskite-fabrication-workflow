"""Identity-domain (users/sessions) methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping
from sqlalchemy import and_, case, delete, func, insert, or_, select, text, update
from datetime import datetime

from ..database import sessions, users
from .helpers import (
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _normalize_display_name,
    _optional_utc,
    _utc_now,
)
from .records import SessionRecord, UserRecord, UserRole

def _user_record(row: Mapping[str, Any]) -> UserRecord:
    return UserRecord(
        id=int(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        password_hash=str(row["password_hash"]),
        role=UserRole(row["role"]),
        is_active=bool(row["is_active"]),
        failed_login_count=int(row["failed_login_count"]),
        locked_until=_optional_utc(row["locked_until"]),
        last_login_at=_optional_utc(row["last_login_at"]),
        password_changed_at=_as_utc(row["password_changed_at"]),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
    )

class UsersMixin:
    """Local accounts, login throttling, and session records."""

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str,
        role: UserRole,
        actor_user_id: int | None = None,
        client_ip: str | None = None,
    ) -> UserRecord:
        normalized_display_name = _normalize_display_name(display_name)
        now = _utc_now()
        async with self.database.begin() as connection:
            result = await connection.execute(
                insert(users).values(
                    username=username,
                    display_name=normalized_display_name,
                    password_hash=password_hash,
                    role=role.value,
                    is_active=True,
                    failed_login_count=0,
                    password_changed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            user_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="user.create",
                entity_type="user",
                entity_id=str(user_id),
                details={"username": username, "role": role.value},
                client_ip=client_ip,
            )
        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> UserRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(select(users).where(users.c.id == user_id))
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown user id: {user_id}")
        return _user_record(row)

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(users).where(users.c.username == username)
                )
            ).mappings().one_or_none()
        return _user_record(row) if row is not None else None

    async def list_users(self) -> list[UserRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(select(users).order_by(users.c.username))
            ).mappings().all()
        return [_user_record(row) for row in rows]

    async def reserve_login_attempt(
        self,
        user_id: int,
        *,
        attempted_at: datetime,
        failure_limit: int,
        lockout_until: datetime,
    ) -> bool:
        """Atomically reserve one password attempt and lock at the configured limit."""

        if failure_limit <= 0:
            raise ValueError("failure limit must be positive")
        expired_lock = and_(
            users.c.locked_until.is_not(None),
            users.c.locked_until <= attempted_at,
        )
        previous_failures = case(
            (expired_lock, 0),
            else_=users.c.failed_login_count,
        )
        next_failures = previous_failures + 1
        async with self.database.begin() as connection:
            result = await connection.execute(
                update(users)
                .where(
                    users.c.id == user_id,
                    users.c.is_active.is_(True),
                    or_(
                        users.c.locked_until.is_(None),
                        users.c.locked_until <= attempted_at,
                    ),
                )
                .values(
                    failed_login_count=next_failures,
                    locked_until=case(
                        (next_failures >= failure_limit, lockout_until),
                        else_=None,
                    ),
                    updated_at=attempted_at,
                )
                .returning(users.c.id, users.c.failed_login_count)
            )
            row = result.mappings().one_or_none()
            if row is None:
                return False
            # Brute-force attempts and lockouts are the strongest attack
            # surface of the app, so they are audited like every other
            # state mutation.
            locked = int(row["failed_login_count"]) >= failure_limit
            await _add_audit_event(
                connection,
                actor_user_id=user_id,
                action="session.lockout" if locked else "session.login_failed",
                entity_type="user",
                entity_id=str(user_id),
                details={
                    "failed_login_count": int(row["failed_login_count"]),
                    "locked_until": (
                        lockout_until.isoformat() if locked else None
                    ),
                },
                client_ip=None,
            )
            return True

    async def record_successful_login(self, user_id: int) -> None:
        now = _utc_now()
        async with self.database.begin() as connection:
            await connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    failed_login_count=0,
                    locked_until=None,
                    last_login_at=now,
                    updated_at=now,
                )
            )

    async def create_session(
        self,
        *,
        token_hash: str,
        csrf_token_hash: str,
        user_id: int,
        expires_at: datetime,
        client_ip: str | None,
        user_agent: str | None,
        password_changed_at: datetime,
    ) -> None:
        """Create a session only if the verified credentials are still current.

        ``password_changed_at`` is the value captured when the password hash
        was verified. Locking the user row and re-reading the column closes
        the window where an administrator password reset commits between hash
        verification and session insertion: either the reset commits first
        (the comparison fails and login is rejected) or the session insert
        commits first and the reset's session wipe removes it.
        """
        now = _utc_now()
        async with self.database.begin() as connection:
            current = (
                await connection.execute(
                    select(users.c.password_changed_at)
                    .where(users.c.id == user_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if current is None:
                raise KeyError(f"unknown user id: {user_id}")
            if _as_utc(current) != _as_utc(password_changed_at):
                raise PermissionError("account credentials changed during sign-in")
            await connection.execute(
                insert(sessions).values(
                    token_hash=token_hash,
                    csrf_token_hash=csrf_token_hash,
                    user_id=user_id,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=expires_at,
                    client_ip=client_ip,
                    user_agent=(user_agent or "")[:512],
                )
            )
            await _add_audit_event(
                connection,
                actor_user_id=user_id,
                action="session.login",
                entity_type="session",
                entity_id=token_hash[:12],
                details={},
                client_ip=client_ip,
            )

    async def get_session(self, token_hash: str) -> SessionRecord | None:
        statement = (
            select(
                sessions.c.token_hash,
                sessions.c.csrf_token_hash,
                sessions.c.created_at.label("session_created_at"),
                sessions.c.last_seen_at.label("session_last_seen_at"),
                sessions.c.expires_at.label("session_expires_at"),
                *[column for column in users.c],
            )
            .join(users, users.c.id == sessions.c.user_id)
            .where(sessions.c.token_hash == token_hash)
        )
        async with self.database.engine.connect() as connection:
            row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return SessionRecord(
            token_hash=str(row["token_hash"]),
            csrf_token_hash=str(row["csrf_token_hash"]),
            created_at=_as_utc(row["session_created_at"]),
            last_seen_at=_as_utc(row["session_last_seen_at"]),
            expires_at=_as_utc(row["session_expires_at"]),
            user=_user_record(row),
        )

    async def touch_session(self, token_hash: str, at: datetime) -> None:
        async with self.database.begin() as connection:
            await connection.execute(
                update(sessions)
                .where(sessions.c.token_hash == token_hash)
                .values(last_seen_at=at)
            )

    async def delete_session(
        self,
        token_hash: str,
        *,
        actor_user_id: int | None,
        client_ip: str | None,
    ) -> None:
        async with self.database.begin() as connection:
            await connection.execute(
                delete(sessions).where(sessions.c.token_hash == token_hash)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="session.logout",
                entity_type="session",
                entity_id=token_hash[:12],
                details={},
                client_ip=client_ip,
            )

    async def delete_expired_sessions(self, now: datetime) -> int:
        async with self.database.begin() as connection:
            result = await connection.execute(
                delete(sessions).where(sessions.c.expires_at <= now)
            )
        return int(result.rowcount or 0)

    async def update_user(
        self,
        user_id: int,
        *,
        role: UserRole,
        is_active: bool,
        actor_user_id: int,
        client_ip: str | None,
    ) -> UserRecord:
        if user_id == actor_user_id and (role != UserRole.ADMINISTRATOR or not is_active):
            raise ValueError("administrators cannot remove or deactivate their own access")
        async with self.database.begin() as connection:
            # Serialize administrator-count checks so two concurrent
            # demotions can never slip past the last-admin guard.
            if connection.dialect.name == "postgresql":
                await connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtextextended('perovskite_admin_guard', 0))"
                    )
                )
            # Two administrators must not be able to demote each other into a
            # zero-administrator state only recoverable via the admin CLI.
            # Only relevant when the target is currently an active
            # administrator and this change removes that status.
            if user_id != actor_user_id and (role != UserRole.ADMINISTRATOR or not is_active):
                target_row = (
                    await connection.execute(
                        select(users.c.role, users.c.is_active).where(
                            users.c.id == user_id
                        )
                    )
                ).mappings().one_or_none()
                if (
                    target_row is not None
                    and target_row["role"] == UserRole.ADMINISTRATOR.value
                    and target_row["is_active"]
                ):
                    other_active_admins = await connection.scalar(
                        select(func.count())
                        .select_from(users)
                        .where(
                            users.c.role == UserRole.ADMINISTRATOR.value,
                            users.c.is_active.is_(True),
                            users.c.id != user_id,
                        )
                    )
                    if other_active_admins is not None and int(other_active_admins) == 0:
                        raise ValueError(
                            "at least one active administrator must remain"
                        )
            result = await connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(role=role.value, is_active=is_active, updated_at=_utc_now())
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown user id: {user_id}")
            if not is_active:
                await connection.execute(delete(sessions).where(sessions.c.user_id == user_id))
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="user.update",
                entity_type="user",
                entity_id=str(user_id),
                details={"role": role.value, "is_active": is_active},
                client_ip=client_ip,
            )
        return await self.get_user(user_id)

    async def reset_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        actor_user_id: int,
        client_ip: str | None,
    ) -> None:
        now = _utc_now()
        async with self.database.begin() as connection:
            result = await connection.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    password_hash=password_hash,
                    failed_login_count=0,
                    locked_until=None,
                    password_changed_at=now,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown user id: {user_id}")
            await connection.execute(delete(sessions).where(sessions.c.user_id == user_id))
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="user.reset_password",
                entity_type="user",
                entity_id=str(user_id),
                details={},
                client_ip=client_ip,
            )
