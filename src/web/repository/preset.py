"""Layer-preset-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from perovskite_bo.device_recipe import (
    DeviceLayer,
    PerovskiteDepositionProcess,
    validate_deposition_process,
)

from typing import Any, Mapping
from sqlalchemy import and_, func, insert, or_, select, update
from copy import deepcopy

from ..database import (
    LAYER_PRESET_NAME_MAX_LENGTH,
    LAYER_PRESET_SCHEMA_VERSION,
    layer_preset_versions,
    layer_presets,
)
from .helpers import _actor_role, _add_audit_event, _as_utc, _canonical_hash, _inserted_id, _utc_now
from .records import ROLE_RANK
from .records import UserRole

import json

def _layer_preset_record(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row["preset_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    version_id = int(row["version_id"])
    layer = deepcopy(snapshot["layer"])
    scope = str(row["scope"])
    layer["preset_id"] = (
        str(row["catalog_key"])
        if row.get("catalog_key")
        else f"{scope}-preset-version:{version_id}"
    )
    deposition_process = snapshot.get("deposition_process")
    return {
        "id": int(row["id"]),
        "preset_key": layer["preset_id"],
        "name": str(row["name"]),
        "status": str(row["status"]),
        "scope": scope,
        "layer": layer,
        "deposition_process": (
            deepcopy(deposition_process) if deposition_process is not None else None
        ),
        "current_revision_number": int(row["revision_number"]),
        "current_version_id": version_id,
        "canonical_hash": str(row["canonical_hash"]),
        "created_at": _as_utc(row["created_at"]).isoformat(),
        "updated_at": _as_utc(row["updated_at"]).isoformat(),
    }

def _layer_preset_statement() -> Any:
    return (
        select(
            layer_presets.c.id,
            layer_presets.c.name,
            layer_presets.c.status,
            layer_presets.c.scope,
            layer_presets.c.catalog_key,
            layer_presets.c.created_at,
            layer_presets.c.updated_at,
            layer_preset_versions.c.id.label("version_id"),
            layer_preset_versions.c.revision_number,
            layer_preset_versions.c.preset_schema_version,
            layer_preset_versions.c.preset_snapshot,
            layer_preset_versions.c.canonical_hash,
        )
        .select_from(layer_presets)
        .join(
            layer_preset_versions,
            and_(
                layer_preset_versions.c.id == layer_presets.c.current_version_id,
                layer_preset_versions.c.layer_preset_id == layer_presets.c.id,
            ),
        )
    )

def _layer_preset_version_record(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row["preset_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    return {
        "id": int(row["id"]),
        "layer_preset_id": int(row["layer_preset_id"]),
        "revision_number": int(row["revision_number"]),
        "preset_schema_version": int(row["preset_schema_version"]),
        "layer": deepcopy(snapshot["layer"]),
        "deposition_process": deepcopy(snapshot.get("deposition_process")),
        "canonical_hash": str(row["canonical_hash"]),
        "created_by_id": (
            int(row["created_by_id"])
            if row["created_by_id"] is not None
            else None
        ),
        "created_at": _as_utc(row["created_at"]).isoformat(),
    }

def _normalize_layer_preset_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ValueError("layer preset name must not be blank")
    if len(normalized) > LAYER_PRESET_NAME_MAX_LENGTH:
        raise ValueError(
            "layer preset name must not exceed "
            f"{LAYER_PRESET_NAME_MAX_LENGTH} characters"
        )
    return normalized

def _normalize_layer_preset_scope(scope: str) -> str:
    normalized = scope.strip().lower()
    if normalized not in {"personal", "shared"}:
        raise ValueError("layer preset scope must be personal or shared")
    return normalized

def _normalize_layer_preset_snapshot(
    layer: Mapping[str, Any],
    deposition_process: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized_layer = DeviceLayer.model_validate(dict(layer)).model_dump(mode="json")
    normalized_layer["preset_id"] = None
    if normalized_layer["layer_type"] == "perovskite":
        if deposition_process is None:
            raise ValueError("a perovskite layer preset requires a deposition process")
        # Presets are copied verbatim into baselines and experiments, so the
        # snapshot must already satisfy the same completeness rules as a saved
        # baseline (every spin/VCD/anneal stage fully filled in).
        normalized_process = validate_deposition_process(
            PerovskiteDepositionProcess.model_validate(dict(deposition_process)).model_dump(mode="json")
        )
    else:
        if deposition_process is not None:
            raise ValueError(
                "only a perovskite layer preset may include a deposition process"
            )
        normalized_process = None
    return {
        "layer": normalized_layer,
        "deposition_process": normalized_process,
    }

class LayerPresetsMixin:
    """Layer preset creation, revision, promotion, and listing."""

    async def create_layer_preset(
        self,
        *,
        name: str,
        layer: Mapping[str, Any],
        deposition_process: Mapping[str, Any] | None,
        scope: str = "personal",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Create the first immutable revision of an actor-owned layer preset."""

        normalized_name = _normalize_layer_preset_name(name)
        snapshot = _normalize_layer_preset_snapshot(layer, deposition_process)
        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            normalized_scope = _normalize_layer_preset_scope(scope)
            if normalized_scope == "shared" and ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
                raise PermissionError("only instructors may create shared layer presets")
            result = await connection.execute(
                insert(layer_presets).values(
                    owner_user_id=actor_user_id if normalized_scope == "personal" else None,
                    scope=normalized_scope,
                    name=normalized_name,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            preset_id = _inserted_id(result)
            version_result = await connection.execute(
                insert(layer_preset_versions).values(
                    layer_preset_id=preset_id,
                    revision_number=1,
                    preset_schema_version=LAYER_PRESET_SCHEMA_VERSION,
                    preset_snapshot=snapshot,
                    canonical_hash=_canonical_hash(snapshot),
                    created_by_id=actor_user_id,
                    created_at=now,
                )
            )
            version_id = _inserted_id(version_result)
            await connection.execute(
                update(layer_presets)
                .where(layer_presets.c.id == preset_id)
                .values(current_version_id=version_id)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="layer_preset.create",
                entity_type="layer_preset",
                entity_id=str(preset_id),
                details={"name": normalized_name, "revision": 1},
                client_ip=client_ip,
            )
        return await self.get_layer_preset(preset_id, actor_user_id=actor_user_id)

    async def update_layer_preset(
        self,
        preset_id: int,
        *,
        name: str,
        layer: Mapping[str, Any],
        deposition_process: Mapping[str, Any] | None,
        scope: str = "personal",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Append a revision to an active preset owned by the actor."""

        normalized_name = _normalize_layer_preset_name(name)
        snapshot = _normalize_layer_preset_snapshot(layer, deposition_process)
        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            normalized_scope = _normalize_layer_preset_scope(scope)
            row = (
                await connection.execute(
                    select(
                        layer_presets.c.id,
                        layer_presets.c.status,
                        layer_presets.c.scope,
                    )
                    .where(
                        layer_presets.c.id == preset_id,
                        or_(
                            and_(
                                layer_presets.c.scope == "personal",
                                layer_presets.c.owner_user_id == actor_user_id,
                            ),
                            and_(
                                layer_presets.c.scope == "shared",
                                ROLE_RANK[actor_role] >= ROLE_RANK[UserRole.INSTRUCTOR],
                            ),
                        ),
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise KeyError(f"unknown layer preset id: {preset_id}")
            if row.status != "active":
                raise ValueError("an inactive layer preset cannot be modified")
            if normalized_scope != row.scope:
                raise ValueError("layer preset scope cannot be changed")
            next_revision = int(
                await connection.scalar(
                    select(func.max(layer_preset_versions.c.revision_number)).where(
                        layer_preset_versions.c.layer_preset_id == preset_id
                    )
                )
                or 0
            ) + 1
            version_result = await connection.execute(
                insert(layer_preset_versions).values(
                    layer_preset_id=preset_id,
                    revision_number=next_revision,
                    preset_schema_version=LAYER_PRESET_SCHEMA_VERSION,
                    preset_snapshot=snapshot,
                    canonical_hash=_canonical_hash(snapshot),
                    created_by_id=actor_user_id,
                    created_at=now,
                )
            )
            version_id = _inserted_id(version_result)
            await connection.execute(
                update(layer_presets)
                .where(layer_presets.c.id == preset_id)
                .values(
                    name=normalized_name,
                    current_version_id=version_id,
                    updated_at=now,
                )
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="layer_preset.revise",
                entity_type="layer_preset",
                entity_id=str(preset_id),
                details={"name": normalized_name, "revision": next_revision},
                client_ip=client_ip,
            )
        return await self.get_layer_preset(preset_id, actor_user_id=actor_user_id)

    async def deactivate_layer_preset(
        self,
        preset_id: int,
        *,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> None:
        """Hide an actor-owned preset from future experiment creation."""

        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            result = await connection.execute(
                update(layer_presets)
                .where(
                    layer_presets.c.id == preset_id,
                    or_(
                        and_(
                            layer_presets.c.scope == "personal",
                            layer_presets.c.owner_user_id == actor_user_id,
                        ),
                        and_(
                            layer_presets.c.scope == "shared",
                            ROLE_RANK[actor_role] >= ROLE_RANK[UserRole.INSTRUCTOR],
                        ),
                    ),
                )
                .values(status="inactive", updated_at=_utc_now())
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown layer preset id: {preset_id}")
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="layer_preset.deactivate",
                entity_type="layer_preset",
                entity_id=str(preset_id),
                details={},
                client_ip=client_ip,
            )

    async def promote_layer_preset(
        self,
        preset_id: int,
        *,
        promoted_by_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Promote an active Personal layer preset to Shared (instructor or above).

        Mirrors :meth:`promote_baseline`: the promotion is explicit and
        immediate, records an audit event with the promoter, and detaches the
        owner so the preset becomes lab-wide selectable. One-way — presets
        cannot be demoted back to Personal.
        """

        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, promoted_by_user_id)
            if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
                raise PermissionError(
                    "only instructors may promote layer presets to shared"
                )
            row = (
                await connection.execute(
                    select(
                        layer_presets.c.name,
                        layer_presets.c.scope,
                        layer_presets.c.status,
                    )
                    .where(layer_presets.c.id == preset_id)
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise KeyError(f"unknown layer preset id: {preset_id}")
            if row.scope != "personal" or row.status != "active":
                raise ValueError("only an active personal layer preset can be promoted")
            collision = await connection.scalar(
                select(layer_presets.c.id).where(
                    layer_presets.c.scope == "shared",
                    layer_presets.c.name == row.name,
                    layer_presets.c.id != preset_id,
                )
            )
            if collision is not None:
                raise ValueError(
                    f"a shared layer preset named {row.name!r} already exists"
                )
            await connection.execute(
                layer_presets.update()
                .where(layer_presets.c.id == preset_id)
                .values(
                    scope="shared",
                    owner_user_id=None,
                    updated_at=now,
                )
            )
            await _add_audit_event(
                connection,
                actor_user_id=promoted_by_user_id,
                action="layer_preset.promote",
                entity_type="layer_preset",
                entity_id=str(preset_id),
                details={},
                client_ip=client_ip,
            )
        return await self.get_layer_preset(preset_id, actor_user_id=promoted_by_user_id)

    async def get_layer_preset(
        self,
        preset_id: int,
        *,
        actor_user_id: int,
    ) -> dict[str, Any]:
        statement = _layer_preset_statement().where(
            layer_presets.c.id == preset_id,
            or_(
                layer_presets.c.scope == "shared",
                layer_presets.c.owner_user_id == actor_user_id,
            ),
        )
        async with self.database.engine.connect() as connection:
            row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown layer preset id: {preset_id}")
        return _layer_preset_record(row)

    async def list_layer_preset_versions(
        self,
        preset_id: int,
        *,
        actor_user_id: int,
    ) -> list[dict[str, Any]]:
        """Return immutable revisions after applying actor-scoped visibility."""

        async with self.database.engine.connect() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            shared_visibility = layer_presets.c.scope == "shared"
            if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
                shared_visibility = and_(
                    shared_visibility,
                    layer_presets.c.status == "active",
                )
            visible = await connection.scalar(
                select(layer_presets.c.id).where(
                    layer_presets.c.id == preset_id,
                    or_(
                        shared_visibility,
                        layer_presets.c.owner_user_id == actor_user_id,
                    ),
                )
            )
            if visible is None:
                raise KeyError(f"unknown layer preset id: {preset_id}")
            rows = (
                await connection.execute(
                    select(layer_preset_versions)
                    .where(layer_preset_versions.c.layer_preset_id == preset_id)
                    .order_by(layer_preset_versions.c.revision_number)
                )
            ).mappings().all()
        return [_layer_preset_version_record(row) for row in rows]

    async def list_layer_presets(
        self,
        *,
        actor_user_id: int,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            shared_visibility = layer_presets.c.scope == "shared"
            if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
                shared_visibility = and_(
                    shared_visibility,
                    layer_presets.c.status == "active",
                )
            statement = (
                _layer_preset_statement()
                .where(
                    or_(
                        shared_visibility,
                        layer_presets.c.owner_user_id == actor_user_id,
                    )
                )
                .order_by(layer_presets.c.name)
            )
            if not include_inactive:
                statement = statement.where(layer_presets.c.status == "active")
            rows = (await connection.execute(statement)).mappings().all()
        return [_layer_preset_record(row) for row in rows]

    async def list_promotable_layer_presets(
        self,
        *,
        actor_user_id: int,
    ) -> list[dict[str, Any]]:
        """Active personal layer presets owned by other users (instructor view).

        These are the promotion candidates: presets a student saved for
        themselves that an instructor may promote to shared so every student
        can select them.
        """

        async with self.database.engine.connect() as connection:
            statement = (
                _layer_preset_statement()
                .where(
                    and_(
                        layer_presets.c.scope == "personal",
                        layer_presets.c.status == "active",
                        layer_presets.c.owner_user_id != actor_user_id,
                    )
                )
                .order_by(layer_presets.c.name)
            )
            rows = (await connection.execute(statement)).mappings().all()
        return [_layer_preset_record(row) for row in rows]
