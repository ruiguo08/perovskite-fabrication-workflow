"""Cross-domain helpers shared by the repository domain mixins: time
normalization, actor roles, audit events, metrics normalization,
experiment locking and transitions, and layout resolution.
Domain-specific helpers live beside their domain mixin. No request/HTTP
logic lives here."""

from __future__ import annotations

from typing import Any, Mapping
from sqlalchemy.ext.asyncio import AsyncConnection
from perovskite_bo import ExperimentStatus
from sqlalchemy import and_, select, update
from datetime import datetime, timezone

from ..database import (
    DISPLAY_NAME_MAX_LENGTH,
    baseline_versions,
    baselines,
    experiments,
    users,
)
# Audit persistence lives in the low-level web.audit_trail module so the
# services layer can share it without an import cycle; this alias keeps
# the historical repository call sites unchanged.
from ..audit_trail import add_audit_event as _add_audit_event
from .records import UserRole

import hashlib
import json
import math

async def _actor_role(
    connection: AsyncConnection, actor_user_id: int | None
) -> UserRole:
    if actor_user_id is None:
        raise PermissionError("an authenticated actor is required")
    value = await connection.scalar(
        select(users.c.role).where(
            users.c.id == actor_user_id,
            users.c.is_active.is_(True),
        )
    )
    if value is None:
        raise PermissionError("the acting user does not exist or is inactive")
    return UserRole(value)

async def _locked_experiment(
    connection: AsyncConnection,
    experiment_id: int,
) -> Mapping[str, Any]:
    row = (
        await connection.execute(
            select(experiments)
            .where(experiments.c.id == experiment_id)
            .with_for_update()
        )
    ).mappings().one_or_none()
    if row is None:
        raise KeyError(f"unknown experiment id: {experiment_id}")
    return row

async def _transition_experiment(
    connection: AsyncConnection,
    experiment_id: int,
    *,
    allowed: set[ExperimentStatus],
    target: ExperimentStatus,
    metrics: dict[str, float] | None = None,
) -> None:
    values: dict[str, Any] = {"status": target.value, "updated_at": _utc_now()}
    if metrics is not None:
        values["metrics"] = metrics
    result = await connection.execute(
        update(experiments)
        .where(
            and_(
                experiments.c.id == experiment_id,
                experiments.c.status.in_([item.value for item in allowed]),
            )
        )
        .values(**values)
    )
    if result.rowcount == 1:
        return
    row = await _locked_experiment(connection, experiment_id)
    raise ValueError(
        f"cannot move experiment {experiment_id} from {row['status']} to {target.value}"
    )

async def _validate_baseline_version_for_condition(
    connection: AsyncConnection,
    baseline_version_id: int | None,
    *,
    actor_user_id: int | None,
    require_active: bool = True,
) -> None:
    """Enforce baseline invocation authorization for condition creation.

    Rules (applied uniformly on every write path that accepts, preserves,
    creates, or replaces ``source_baseline_version_id``):

    - A Personal baseline revision may only be invoked by its owner;
      every other actor - including instructors and administrators - is
      outside the resource boundary and receives the uniform 404-style
      ``KeyError``.
    - When ``require_active`` is set (creation paths), an archived baseline
      is rejected; provenance-only updates of an already bound condition use
      ``require_active=False`` so existing expanded snapshots never depend on
      future baseline changes.
    """
    if baseline_version_id is None:
        return
    row = (
        await connection.execute(
            select(
                baselines.c.status,
                baselines.c.scope,
                baselines.c.owner_user_id,
            )
            .select_from(baseline_versions)
            .join(baselines, baselines.c.id == baseline_versions.c.baseline_id)
            .where(baseline_versions.c.id == baseline_version_id)
        )
    ).mappings().one_or_none()
    if row is None:
        raise KeyError(f"unknown baseline version id: {baseline_version_id}")
    if str(row["scope"]) == "personal" and row["owner_user_id"] != actor_user_id:
        # "Only the creator can invoke it" applies to all non-owners.
        raise KeyError(f"unknown baseline version id: {baseline_version_id}")
    if require_active and str(row["status"]) != "active":
        raise ValueError("new conditions cannot use an archived baseline")

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def _canonical_hash(snapshot: dict[str, Any]) -> str:
    """Deterministic SHA-256 of a recipe snapshot with sorted keys."""

    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

def _inserted_id(result: Any) -> int:
    primary_key = result.inserted_primary_key
    if not primary_key or primary_key[0] is None:
        raise RuntimeError("database did not return an inserted primary key")
    return int(primary_key[0])

def _normalize_display_name(display_name: str) -> str:
    normalized = display_name.strip()
    if not normalized:
        raise ValueError("display name must not be blank")
    if len(normalized) > DISPLAY_NAME_MAX_LENGTH:
        raise ValueError(
            f"display name must not exceed {DISPLAY_NAME_MAX_LENGTH} characters"
        )
    return normalized

def _normalize_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for name, value in metrics.items():
        if isinstance(value, bool):
            raise TypeError(f"metric {name!r} must be a finite number")
        try:
            normalized_value = float(value)
        except (TypeError, ValueError) as error:
            raise TypeError(f"metric {name!r} must be a finite number") from error
        if not math.isfinite(normalized_value):
            raise ValueError(f"metric {name!r} must be finite")
        normalized[str(name)] = normalized_value
    return normalized

def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

