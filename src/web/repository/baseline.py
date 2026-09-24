"""Baseline-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping
from sqlalchemy import and_, func, insert, or_, select, update

from ..database import (
    BASELINE_NAME_MAX_LENGTH,
    BASELINE_RECIPE_SCHEMA_VERSION,
    baseline_versions,
    baselines,
    users,
)
from .helpers import _actor_role, _add_audit_event, _as_utc, _canonical_hash, _inserted_id, _utc_now
from .records import ROLE_RANK
from .records import UserRole

import json

def _baseline_record(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row.get("recipe_snapshot") or {}
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "status": str(row.get("status") or "active"),
        "scope": str(row.get("scope") or "personal"),
        "owner_user_id": (
            int(row["owner_user_id"])
            if row.get("owner_user_id") is not None
            else None
        ),
        "owner_display_name": (
            str(row["owner_display_name"])
            if row.get("owner_display_name") is not None
            else None
        ),
        "promoted_by_user_id": (
            int(row["promoted_by_user_id"])
            if row.get("promoted_by_user_id") is not None
            else None
        ),
        "promoted_by_display_name": (
            str(row["promoted_by_display_name"])
            if row.get("promoted_by_display_name") is not None
            else None
        ),
        "promoted_at": (
            _as_utc(row["promoted_at"]).isoformat()
            if row.get("promoted_at") is not None
            else None
        ),
        "promotion_note": (
            str(row["promotion_note"])
            if row.get("promotion_note") is not None
            else None
        ),
        "promoted_version_id": (
            int(row["promoted_version_id"])
            if row.get("promoted_version_id") is not None
            else None
        ),
        "device_recipe": dict(snapshot.get("device_recipe", {})),
        "deposition_process": dict(snapshot.get("deposition_process", {})),
        "current_revision_number": row.get("revision_number"),
        "current_version_id": row.get("version_id"),
        "canonical_hash": str(row["canonical_hash"]) if row.get("canonical_hash") else None,
        "created_at": _as_utc(row["created_at"]).isoformat(),
        "updated_at": _as_utc(row["updated_at"]).isoformat(),
    }

def _baseline_statement() -> Any:
    """Complete baseline projection with current version and provenance names."""
    owner_user = users.alias("baseline_owner_user")
    promoter_user = users.alias("baseline_promoter_user")
    return (
        select(
            baselines.c.id,
            baselines.c.name,
            baselines.c.status,
            baselines.c.scope,
            baselines.c.owner_user_id,
            baselines.c.promoted_by_user_id,
            baselines.c.promoted_at,
            baselines.c.promotion_note,
            baselines.c.promoted_version_id,
            baselines.c.created_at,
            baselines.c.updated_at,
            baseline_versions.c.id.label("version_id"),
            baseline_versions.c.revision_number,
            baseline_versions.c.recipe_schema_version,
            baseline_versions.c.recipe_snapshot,
            baseline_versions.c.canonical_hash,
            owner_user.c.display_name.label("owner_display_name"),
            promoter_user.c.display_name.label("promoted_by_display_name"),
        )
        .select_from(baselines)
        .outerjoin(
            baseline_versions,
            baseline_versions.c.id == baselines.c.current_version_id,
        )
        .outerjoin(owner_user, owner_user.c.id == baselines.c.owner_user_id)
        .outerjoin(
            promoter_user,
            promoter_user.c.id == baselines.c.promoted_by_user_id,
        )
    )

def _baseline_version_record(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row["recipe_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return {
        "id": int(row["id"]),
        "baseline_id": int(row["baseline_id"]),
        "revision_number": int(row["revision_number"]),
        "recipe_schema_version": int(row["recipe_schema_version"]),
        "device_recipe": dict(snapshot.get("device_recipe", {})),
        "deposition_process": dict(snapshot.get("deposition_process", {})),
        "canonical_hash": str(row["canonical_hash"]),
        "change_note": str(row["change_note"]),
        "created_by_id": (
            int(row["created_by_id"])
            if row["created_by_id"] is not None
            else None
        ),
        "created_at": _as_utc(row["created_at"]).isoformat(),
    }

def _normalize_baseline_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("baseline name must not be blank")
    if len(normalized) > BASELINE_NAME_MAX_LENGTH:
        raise ValueError(
            f"baseline name must not exceed {BASELINE_NAME_MAX_LENGTH} characters"
        )
    return normalized

class BaselinesMixin:
    """Baseline creation, revision, promotion, and deletion."""

    async def save_baseline(
        self,
        name: str,
        device_recipe: dict[str, Any],
        deposition_process: dict[str, Any],
        *,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        normalized_name = _normalize_baseline_name(name)
        now = _utc_now()
        snapshot = {
            "device_recipe": device_recipe,
            "deposition_process": deposition_process,
        }
        canonical = _canonical_hash(snapshot)
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            scope = "personal" if actor_role == UserRole.STUDENT else "shared"
            result = await connection.execute(
                insert(baselines).values(
                    name=normalized_name,
                    device_recipe=device_recipe,
                    deposition_process=deposition_process,
                    # A student-created baseline is Personal; instructor and
                    # administrator direct creation is Shared.
                    owner_user_id=(
                        actor_user_id if scope == "personal" else None
                    ),
                    scope=scope,
                    created_at=now,
                    updated_at=now,
                    created_by_id=actor_user_id,
                    updated_by_id=actor_user_id,
                    status="active",
                )
            )
            baseline_id = _inserted_id(result)
            version_result = await connection.execute(
                insert(baseline_versions).values(
                    baseline_id=baseline_id,
                    revision_number=1,
                    recipe_schema_version=BASELINE_RECIPE_SCHEMA_VERSION,
                    recipe_snapshot=snapshot,
                    canonical_hash=canonical,
                    change_note="Initial creation",
                    created_by_id=actor_user_id,
                    created_at=now,
                )
            )
            version_id = _inserted_id(version_result)
            await connection.execute(
                update(baselines)
                .where(baselines.c.id == baseline_id)
                .values(current_version_id=version_id)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="baseline.create",
                entity_type="baseline",
                entity_id=str(baseline_id),
                details={"name": normalized_name, "revision": 1, "scope": scope},
                client_ip=client_ip,
            )
        return await self.get_baseline(baseline_id, actor_user_id=actor_user_id)

    async def update_baseline(
        self,
        baseline_id: int,
        name: str,
        device_recipe: dict[str, Any],
        deposition_process: dict[str, Any],
        *,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Create a new immutable revision instead of overwriting."""

        normalized_name = _normalize_baseline_name(name)
        snapshot = {
            "device_recipe": device_recipe,
            "deposition_process": deposition_process,
        }
        canonical = _canonical_hash(snapshot)
        now = _utc_now()
        async with self.database.begin() as connection:
            baseline_row = (
                await connection.execute(
                    select(
                        baselines.c.id,
                        baselines.c.status,
                        baselines.c.scope,
                        baselines.c.owner_user_id,
                    )
                    .where(baselines.c.id == baseline_id)
                    .with_for_update()
                )
            ).one_or_none()
            if baseline_row is None:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            actor_role = await _actor_role(connection, actor_user_id)
            scope = str(baseline_row.scope)
            if scope == "personal":
                # Only the owner may revise a Personal baseline.
                if baseline_row.owner_user_id != actor_user_id:
                    raise KeyError(f"unknown baseline id: {baseline_id}")
            else:
                # Shared baselines keep the administrator-only revision policy.
                if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.ADMINISTRATOR]:
                    raise KeyError(f"unknown baseline id: {baseline_id}")
            if baseline_row.status != "active":
                raise ValueError("an archived baseline cannot be revised")
            max_rev = await connection.scalar(
                select(func.max(baseline_versions.c.revision_number)).where(
                    baseline_versions.c.baseline_id == baseline_id
                )
            )
            next_revision = int(max_rev or 0) + 1
            version_result = await connection.execute(
                insert(baseline_versions).values(
                    baseline_id=baseline_id,
                    revision_number=next_revision,
                    recipe_schema_version=BASELINE_RECIPE_SCHEMA_VERSION,
                    recipe_snapshot=snapshot,
                    canonical_hash=canonical,
                    change_note=f"Revision {next_revision}",
                    created_by_id=actor_user_id,
                    created_at=now,
                )
            )
            version_id = _inserted_id(version_result)
            result = await connection.execute(
                update(baselines)
                .where(baselines.c.id == baseline_id)
                .values(
                    name=normalized_name,
                    device_recipe=device_recipe,
                    deposition_process=deposition_process,
                    current_version_id=version_id,
                    updated_at=now,
                    updated_by_id=actor_user_id,
                )
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="baseline.update",
                entity_type="baseline",
                entity_id=str(baseline_id),
                details={"name": normalized_name, "revision": next_revision},
                client_ip=client_ip,
            )
        return await self.get_baseline(baseline_id, actor_user_id=actor_user_id)

    async def promote_baseline(
        self,
        baseline_id: int,
        *,
        promoted_by_user_id: int,
        note: str | None = None,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Promote an active Personal baseline to Shared.

        Promotion is explicit and immediate: it records the exact current
        immutable revision, the promoter, the timestamp, and an optional note,
        then the baseline becomes lab-wide visible and usable. The original
        owner is retained as provenance.
        """

        normalized_note = (note or "").strip() or None
        now = _utc_now()
        async with self.database.begin() as connection:
            row = (
                await connection.execute(
                    select(
                        baselines.c.id,
                        baselines.c.name,
                        baselines.c.status,
                        baselines.c.scope,
                        baselines.c.current_version_id,
                        baseline_versions.c.canonical_hash,
                    )
                    .select_from(baselines)
                    .join(
                        baseline_versions,
                        baseline_versions.c.id == baselines.c.current_version_id,
                    )
                    .where(baselines.c.id == baseline_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            if row["scope"] != "personal" or row["status"] != "active":
                raise ValueError("only an active personal baseline can be promoted")
            promoted_version_id = int(row["current_version_id"])
            result = await connection.execute(
                update(baselines)
                .where(baselines.c.id == baseline_id)
                .values(
                    scope="shared",
                    promoted_by_user_id=promoted_by_user_id,
                    promoted_at=now,
                    promotion_note=normalized_note,
                    # Record the exact version; the database-level composite
                    # foreign key (id, promoted_version_id) references the same
                    # baseline's versions.
                    promoted_version_id=promoted_version_id,
                    updated_at=now,
                    updated_by_id=promoted_by_user_id,
                )
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            await _add_audit_event(
                connection,
                actor_user_id=promoted_by_user_id,
                action="baseline.promote",
                entity_type="baseline",
                entity_id=str(baseline_id),
                details={
                    "name": str(row["name"]),
                    "version_id": promoted_version_id,
                    "canonical_hash": str(row["canonical_hash"]),
                    "note": normalized_note or "",
                },
                client_ip=client_ip,
            )
        return await self.get_baseline(baseline_id, actor_user_id=promoted_by_user_id)

    async def get_baseline(
        self,
        baseline_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Return one baseline after applying actor-scoped visibility.

        Students may read only active Shared baselines and their own active
        Personal baselines; instructors and administrators have oversight
        access to every baseline.
        """
        async with self.database.engine.connect() as connection:
            actor_role = (
                await _actor_role(connection, actor_user_id)
                if actor_user_id is not None
                else None
            )
            statement = _baseline_statement().where(baselines.c.id == baseline_id)
            if actor_role == UserRole.STUDENT:
                statement = statement.where(
                    and_(
                        baselines.c.status == "active",
                        or_(
                            baselines.c.scope == "shared",
                            baselines.c.owner_user_id == actor_user_id,
                        ),
                    )
                )
            row = (
                await connection.execute(statement)
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown baseline id: {baseline_id}")
        return _baseline_record(row)

    async def list_baselines(
        self,
        *,
        actor_user_id: int | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """List baselines visible to the actor.

        Students see only active Shared baselines and their own active
        Personal baselines; instructors and administrators see the whole lab
        directory (subject to ``include_archived``).
        """
        async with self.database.engine.connect() as connection:
            actor_role = (
                await _actor_role(connection, actor_user_id)
                if actor_user_id is not None
                else None
            )
            statement = _baseline_statement()
            if actor_role == UserRole.STUDENT:
                statement = statement.where(
                    and_(
                        baselines.c.status == "active",
                        or_(
                            baselines.c.scope == "shared",
                            baselines.c.owner_user_id == actor_user_id,
                        ),
                    )
                )
            elif not include_archived:
                statement = statement.where(baselines.c.status == "active")
            statement = statement.order_by(baselines.c.name)
            rows = (await connection.execute(statement)).mappings().all()
        return [_baseline_record(row) for row in rows]

    async def list_baseline_versions(
        self,
        baseline_id: int,
        *,
        actor_user_id: int,
    ) -> list[dict[str, Any]]:
        """Return all immutable revisions of a visible baseline, oldest first."""

        async with self.database.engine.connect() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            visible_for_students = and_(
                or_(
                    baselines.c.scope == "shared",
                    baselines.c.owner_user_id == actor_user_id,
                ),
                baselines.c.status == "active",
            )
            exists = await connection.scalar(
                select(baselines.c.id).where(
                    baselines.c.id == baseline_id,
                    (
                        visible_for_students
                        if actor_role == UserRole.STUDENT
                        else True
                    ),
                )
            )
            if exists is None:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            rows = (
                await connection.execute(
                    select(baseline_versions)
                    .where(baseline_versions.c.baseline_id == baseline_id)
                    .order_by(baseline_versions.c.revision_number)
                )
            ).mappings().all()
        return [_baseline_version_record(row) for row in rows]

    async def delete_baseline(
        self,
        baseline_id: int,
        *,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> None:
        async with self.database.begin() as connection:
            row = (
                await connection.execute(
                    select(baselines.c.name, baselines.c.status).where(
                        baselines.c.id == baseline_id
                    )
                )
            ).one_or_none()
            if row is None:
                raise KeyError(f"unknown baseline id: {baseline_id}")
            if row.status != "archived":
                await connection.execute(
                    update(baselines)
                    .where(baselines.c.id == baseline_id)
                    .values(
                        status="archived",
                        updated_at=_utc_now(),
                        updated_by_id=actor_user_id,
                    )
                )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="baseline.archive",
                entity_type="baseline",
                entity_id=str(baseline_id),
                details={"name": str(row.name)},
                client_ip=client_ip,
            )
