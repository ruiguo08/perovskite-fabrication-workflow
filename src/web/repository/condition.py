"""Condition-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, delete, insert, select, update
from datetime import datetime

from ..condition_snapshot import (
    canonical_hash as condition_canonical_hash,
    validate_condition_snapshot,
)
from ..database import (
    condition_substrate_exceptions,
    experiment_conditions,
    experiments,
    fabrication_batches,
)
from ..device_layouts import expected_device_count, layout_snapshot
from ..services.catalog_service import get_device_layout
from .helpers import (
    _actor_role,
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _optional_utc,
    _utc_now,
    _validate_baseline_version_for_condition,
)
from ..services.catalog_service import (
    resolve_layout as _resolve_layout,
)
from .records import ROLE_RANK
from .records import (
    ConditionRecord,
    ConditionRole,
    ExceptionDecision,
    PlanStatus,
    SubstrateExceptionRecord,
    UserRole,
)

import json

async def _invalidate_condition_exceptions(
    connection: AsyncConnection,
    condition_id: int,
    *,
    now: datetime,
) -> int:
    result = await connection.execute(
        update(condition_substrate_exceptions)
        .where(
            and_(
                condition_substrate_exceptions.c.condition_id == condition_id,
                condition_substrate_exceptions.c.decision.in_(
                    [
                        ExceptionDecision.PENDING.value,
                        ExceptionDecision.APPROVED.value,
                    ]
                ),
            )
        )
        .values(
            decision=ExceptionDecision.INVALIDATED.value,
            decided_at=now,
            approved_condition_hash=None,
            decision_note="Condition changed; approval auto-invalidated",
        )
    )
    return int(result.rowcount or 0)

async def _validate_plan_conditions(
    connection: AsyncConnection,
    experiment_id: int,
    *,
    plan_type: str | None,
    target_status: PlanStatus,
) -> None:
    if target_status == PlanStatus.CANCELLED:
        return
    rows = (
        await connection.execute(
            select(experiment_conditions).where(
                experiment_conditions.c.experiment_id == experiment_id
            )
        )
    ).mappings().all()
    if not rows:
        raise ValueError("a plan must contain at least one condition")
    roles = [ConditionRole(row["role"]) for row in rows]
    if plan_type == "comparative":
        if roles.count(ConditionRole.CONTROL) != 1:
            raise ValueError("a comparative plan requires exactly one control condition")
        if roles.count(ConditionRole.TARGET) < 1:
            raise ValueError("a comparative plan requires at least one target condition")
        if ConditionRole.STANDALONE in roles:
            raise ValueError("a comparative plan cannot contain standalone conditions")
    elif plan_type == "standalone":
        if roles != [ConditionRole.STANDALONE]:
            raise ValueError(
                "a standalone plan requires exactly one standalone condition"
            )
    else:
        raise ValueError("plan_type must be comparative or standalone before release")

    low_count_rows: list[Mapping[str, Any]] = []
    from ..services.catalog_service import get_device_layout

    for row in rows:
        if row["requires_manual_review"]:
            raise ValueError(
                f"condition {row['condition_code']} requires manual review"
            )
        normalized = validate_condition_snapshot(row["recipe_snapshot"])
        if condition_canonical_hash(normalized) != row["canonical_hash"]:
            raise ValueError(
                f"condition {row['condition_code']} snapshot hash is inconsistent"
            )
        frozen_layout_snapshot = row["device_layout_snapshot"]
        if isinstance(frozen_layout_snapshot, str):
            frozen_layout_snapshot = json.loads(frozen_layout_snapshot)
        if not isinstance(frozen_layout_snapshot, Mapping):
            raise ValueError(
                f"condition {row['condition_code']} has no frozen layout snapshot"
            )
        layout = await get_device_layout(
            connection,
            str(row["device_layout_code"]),
            int(frozen_layout_snapshot.get("version", 0) or 0),
        )
        if layout is None:
            raise ValueError(
                f"condition {row['condition_code']} references device layout"
                f" {row['device_layout_code']!r} v{frozen_layout_snapshot.get('version')}"
                ", which no longer exists"
            )
        if row["device_layout_snapshot"] != layout_snapshot(layout):
            raise ValueError(
                f"condition {row['condition_code']} layout snapshot is inconsistent"
            )
        if int(row["expected_device_count"]) != expected_device_count(
            int(row["planned_substrate_count"]), layout
        ):
            raise ValueError(
                f"condition {row['condition_code']} expected device count is inconsistent"
            )
        if int(row["planned_substrate_count"]) < 3:
            low_count_rows.append(row)

    # Strict approval workflow: every plan must pass through
    # PENDING_APPROVAL -> APPROVED before RELEASED. Submission is allowed for
    # all plans; low-count conditions still require an exception request
    # (pending or approved) to exist before submission, and an approved
    # exception before APPROVED/RELEASED.
    for row in low_count_rows:
        exception = (
            await connection.execute(
                select(condition_substrate_exceptions)
                .where(
                    condition_substrate_exceptions.c.condition_id == row["id"],
                    condition_substrate_exceptions.c.decision.in_(
                        [
                            ExceptionDecision.PENDING.value,
                            ExceptionDecision.APPROVED.value,
                        ]
                    ),
                )
                .order_by(condition_substrate_exceptions.c.id.desc())
            )
        ).mappings().one_or_none()
        if exception is None:
            raise ValueError(
                f"condition {row['condition_code']} requires a substrate exception"
            )
        if target_status in {
            PlanStatus.APPROVED,
            PlanStatus.RELEASED,
            PlanStatus.IN_PROGRESS,
            PlanStatus.COMPLETED,
        }:
            if exception["decision"] != ExceptionDecision.APPROVED.value:
                raise ValueError(
                    f"condition {row['condition_code']} substrate exception is not approved"
                )
            if exception["approved_condition_hash"] != row["canonical_hash"]:
                raise ValueError(
                    f"condition {row['condition_code']} approval is stale"
                )

def _condition_record(row: Mapping[str, Any]) -> ConditionRecord:
    snapshot = row["recipe_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    layout_snapshot = row["device_layout_snapshot"]
    if isinstance(layout_snapshot, str):
        layout_snapshot = json.loads(layout_snapshot)
    return ConditionRecord(
        id=int(row["id"]),
        experiment_id=int(row["experiment_id"]),
        role=ConditionRole(row["role"]),
        condition_code=str(row["condition_code"]),
        condition_name=str(row["condition_name"]),
        recipe_snapshot=dict(snapshot),
        recipe_schema_version=int(row["recipe_schema_version"]),
        canonical_hash=str(row["canonical_hash"]),
        source_baseline_version_id=row["source_baseline_version_id"],
        device_layout_code=str(row["device_layout_code"]),
        device_layout_snapshot=dict(layout_snapshot),
        planned_substrate_count=int(row["planned_substrate_count"]),
        expected_device_count=int(row["expected_device_count"]),
        requires_manual_review=bool(row["requires_manual_review"]),
        created_at=_as_utc(row["created_at"]),
        created_by_id=row["created_by_id"],
    )

def _exception_record(row: Mapping[str, Any]) -> SubstrateExceptionRecord:
    return SubstrateExceptionRecord(
        id=int(row["id"]),
        condition_id=int(row["condition_id"]),
        requested_count=int(row["requested_count"]),
        reason=str(row["reason"]),
        requested_by_id=row["requested_by_id"],
        requested_at=_as_utc(row["requested_at"]),
        decision=ExceptionDecision(row["decision"]),
        decided_by_id=row["decided_by_id"],
        decided_at=_optional_utc(row["decided_at"]),
        decision_note=str(row["decision_note"]),
        approved_condition_hash=row["approved_condition_hash"],
    )

def _next_condition_code(
    experiment_code: str,
    role: ConditionRole,
    existing_codes: list[str],
) -> str:
    if role == ConditionRole.CONTROL:
        return f"{experiment_code}-C"
    prefix = (
        f"{experiment_code}-T"
        if role == ConditionRole.TARGET
        else f"{experiment_code}-S"
    )
    indexes: list[int] = []
    for code in existing_codes:
        if not code.startswith(prefix):
            continue
        suffix = code[len(prefix):]
        if role == ConditionRole.STANDALONE and suffix == "":
            indexes.append(1)
        elif suffix.isdigit():
            indexes.append(int(suffix))
    index = max(indexes, default=0) + 1
    if role == ConditionRole.STANDALONE and index == 1:
        return prefix
    return f"{prefix}{index}"

def _validate_plan_transition(
    current: PlanStatus,
    target: PlanStatus,
    actor_role: UserRole,
) -> None:
    allowed = {
        PlanStatus.DRAFT: {
            PlanStatus.PENDING_APPROVAL,
            PlanStatus.CANCELLED,
        },
        PlanStatus.PENDING_APPROVAL: {
            PlanStatus.APPROVED,
            PlanStatus.CANCELLED,
        },
        PlanStatus.APPROVED: {PlanStatus.RELEASED, PlanStatus.CANCELLED},
        PlanStatus.RELEASED: {PlanStatus.IN_PROGRESS, PlanStatus.CANCELLED},
        PlanStatus.IN_PROGRESS: {PlanStatus.COMPLETED, PlanStatus.CANCELLED},
        PlanStatus.COMPLETED: set(),
        PlanStatus.CANCELLED: set(),
    }
    if target not in allowed[current]:
        raise ValueError(
            f"plan status cannot change from {current.value} to {target.value}"
        )
    if (
        target == PlanStatus.APPROVED
        and ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]
    ):
        raise PermissionError("instructor access is required to approve a plan")

async def _require_fabrication_batches(
    connection: AsyncConnection,
    experiment_id: int,
    target: PlanStatus,
) -> None:
    """Require an active batch to start and a finished batch to complete.

    Result upload is keyed per fabrication batch, so a plan that reaches
    completed with zero batches could never receive characterization data.
    """
    if target not in (PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED):
        return
    statuses = (
        await connection.execute(
            select(fabrication_batches.c.status)
            .where(fabrication_batches.c.experiment_id == experiment_id)
        )
    ).scalars().all()
    if not statuses:
        raise ValueError("at least one fabrication batch must be frozen before fabrication starts or completes")
    if target is PlanStatus.IN_PROGRESS and all(status == "cancelled" for status in statuses):
        raise ValueError("at least one non-cancelled fabrication batch is required to start fabrication")
    if target is PlanStatus.COMPLETED:
        if "completed" not in statuses:
            raise ValueError("at least one completed fabrication batch is required to complete the plan")
        if any(status not in {"completed", "cancelled"} for status in statuses):
            raise ValueError("all fabrication batches must be completed or cancelled before completing the plan")


class ConditionsMixin:
    """Per-condition recipe snapshots, plan-status transitions, and substrate-count exceptions."""

    # ------------------------------------------------------------------
    # Experiment conditions (per-condition complete recipe snapshots)
    # ------------------------------------------------------------------
    async def create_condition(
        self,
        *,
        experiment_id: int,
        role: ConditionRole | str,
        condition_code: str | None,
        condition_name: str,
        recipe_snapshot: dict[str, Any],
        source_baseline_version_id: int | None,
        device_layout_code: str,
        planned_substrate_count: int,
        requires_manual_review: bool = False,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> ConditionRecord:
        normalized_role = ConditionRole(role)
        normalized_code = condition_code.strip() if condition_code else ""
        normalized_name = condition_name.strip()
        if not normalized_name:
            raise ValueError("condition name must not be blank")
        if planned_substrate_count < 1:
            raise ValueError("planned substrate count must be at least 1")
        normalized_snapshot = validate_condition_snapshot(recipe_snapshot)
        snapshot_hash = condition_canonical_hash(normalized_snapshot)
        intended_plan_type = (
            "standalone"
            if normalized_role == ConditionRole.STANDALONE
            else "comparative"
        )
        now = _utc_now()
        async with self.database.begin() as connection:
            plan_row = (
                await connection.execute(
                    select(
                        experiments.c.experiment_code,
                        experiments.c.plan_type,
                        experiments.c.plan_status,
                    )
                    .where(experiments.c.id == experiment_id)
                    # Serialize with plan-status transitions and batch
                    # freezes on the parent experiment row (consistent lock
                    # order: experiment first, then condition rows).
                    .with_for_update()
                )
            ).one_or_none()
            if plan_row is None:
                raise KeyError(f"unknown experiment id: {experiment_id}")
            if plan_row.plan_status in {
                PlanStatus.RELEASED.value,
                PlanStatus.IN_PROGRESS.value,
                PlanStatus.COMPLETED.value,
                PlanStatus.CANCELLED.value,
            }:
                raise ValueError("released or closed plans cannot be modified")
            if plan_row.plan_type not in (None, intended_plan_type):
                raise ValueError(
                    f"{normalized_role.value} conditions are incompatible with "
                    f"a {plan_row.plan_type} plan"
                )
            existing_conditions = (
                await connection.execute(
                    select(
                        experiment_conditions.c.condition_code,
                        experiment_conditions.c.role,
                        experiment_conditions.c.source_baseline_version_id,
                    ).where(
                        experiment_conditions.c.experiment_id == experiment_id
                    )
                )
            ).all()
            existing_codes = [str(row.condition_code) for row in existing_conditions]
            existing_roles = [ConditionRole(row.role) for row in existing_conditions]
            existing_sources = {
                row.source_baseline_version_id for row in existing_conditions
            }
            # source_baseline_version_id is provenance only — every condition
            # stores its own complete recipe snapshot, so a student may add
            # conditions to a from-scratch plan without referencing any
            # baseline (the same semantics as experiment creation).
            if existing_sources and existing_sources != {
                source_baseline_version_id
            }:
                raise ValueError(
                    "all conditions in a plan must use the same baseline revision"
                )
            if (
                normalized_role == ConditionRole.CONTROL
                and ConditionRole.CONTROL in existing_roles
            ):
                raise ValueError("a comparative plan can contain only one control")
            if normalized_role == ConditionRole.STANDALONE and existing_roles:
                raise ValueError("a standalone plan can contain only one condition")
            expected_code = _next_condition_code(
                str(plan_row.experiment_code), normalized_role, existing_codes
            )
            if normalized_code and normalized_code != expected_code:
                raise ValueError(f"condition code must be {expected_code}")
            normalized_code = expected_code
            await _validate_baseline_version_for_condition(
                connection, source_baseline_version_id,
                actor_user_id=actor_user_id,
            )
            layout = await _resolve_layout(connection, device_layout_code)
            layout_copy = layout_snapshot(layout)
            device_count = expected_device_count(planned_substrate_count, layout)
            result = await connection.execute(
                insert(experiment_conditions).values(
                    experiment_id=experiment_id,
                    role=normalized_role.value,
                    condition_code=normalized_code,
                    condition_name=normalized_name,
                    recipe_snapshot=normalized_snapshot,
                    recipe_schema_version=int(normalized_snapshot["schema_version"]),
                    canonical_hash=snapshot_hash,
                    source_baseline_version_id=source_baseline_version_id,
                    device_layout_code=layout.code,
                    device_layout_snapshot=layout_copy,
                    planned_substrate_count=planned_substrate_count,
                    expected_device_count=device_count,
                    requires_manual_review=requires_manual_review,
                    created_at=now,
                    created_by_id=actor_user_id,
                )
            )
            condition_id = _inserted_id(result)
            await connection.execute(
                update(experiments)
                .where(experiments.c.id == experiment_id)
                .values(
                    plan_type=intended_plan_type,
                    # A plan still mid-review keeps its status (the approval
                    # gate re-validates every condition before approving),
                    # but an already-approved plan must return to draft: the
                    # new condition has not been reviewed by an instructor,
                    # so releasing as-is would bypass the review gate. The
                    # released-or-closed check above blocks later statuses.
                    plan_status=(
                        PlanStatus.PENDING_APPROVAL.value
                        if plan_row.plan_status
                        == PlanStatus.PENDING_APPROVAL.value
                        else PlanStatus.DRAFT.value
                    ),
                    updated_at=now,
                )
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="condition.create",
                entity_type="experiment_condition",
                entity_id=str(condition_id),
                details={
                    "experiment_id": experiment_id,
                    "role": normalized_role.value,
                    "condition_code": normalized_code,
                },
                client_ip=client_ip,
            )
        return await self.get_condition(condition_id)

    async def update_condition(
        self,
        condition_id: int,
        *,
        condition_name: str,
        recipe_snapshot: dict[str, Any],
        source_baseline_version_id: int | None,
        device_layout_code: str,
        planned_substrate_count: int,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> ConditionRecord:
        normalized_name = condition_name.strip()
        if not normalized_name:
            raise ValueError("condition name must not be blank")
        if planned_substrate_count < 1:
            raise ValueError("planned substrate count must be at least 1")
        normalized_snapshot = validate_condition_snapshot(recipe_snapshot)
        snapshot_hash = condition_canonical_hash(normalized_snapshot)
        now = _utc_now()
        async with self.database.begin() as connection:
            row = (
                await connection.execute(
                    select(
                        experiment_conditions.c.experiment_id,
                        experiment_conditions.c.source_baseline_version_id,
                        experiment_conditions.c.canonical_hash,
                        experiment_conditions.c.planned_substrate_count,
                        experiment_conditions.c.device_layout_code,
                        experiment_conditions.c.device_layout_snapshot,
                        experiment_conditions.c.requires_manual_review,
                        experiments.c.plan_status,
                    )
                    .select_from(experiment_conditions)
                    .join(
                        experiments,
                        experiments.c.id == experiment_conditions.c.experiment_id,
                    )
                    .where(experiment_conditions.c.id == condition_id)
                    # Serialize with plan-status transitions and batch
                    # freezes on the parent experiment row (consistent lock
                    # order: experiment first, then condition rows).
                    .with_for_update(of=experiments)
                )
            ).one_or_none()
            if row is None:
                raise KeyError(f"unknown condition id: {condition_id}")
            if row.plan_status in {
                PlanStatus.RELEASED.value,
                PlanStatus.IN_PROGRESS.value,
                PlanStatus.COMPLETED.value,
                PlanStatus.CANCELLED.value,
            }:
                raise ValueError("released or closed plans cannot be modified")
            if (
                source_baseline_version_id
                != row.source_baseline_version_id
            ):
                raise ValueError(
                    "a condition's source baseline revision cannot be changed"
                )
            await _validate_baseline_version_for_condition(
                connection,
                source_baseline_version_id,
                actor_user_id=actor_user_id,
                require_active=False,
            )
            # Clear the manual-review flag only when the edit changes a
            # substantive field (recipe/canonical hash, substrate count, or
            # layout). Metadata-only edits (e.g. renaming) preserve it, so a
            # rename alone cannot silently wave an unvetted condition through.
            # A condition whose layout code is unchanged stays on the exact
            # layout version frozen in its snapshot; a NEW layout code selects
            # the catalog's latest version.
            saved_layout_snapshot = row.device_layout_snapshot
            if isinstance(saved_layout_snapshot, str):
                saved_layout_snapshot = json.loads(saved_layout_snapshot)
            if (
                isinstance(saved_layout_snapshot, Mapping)
                and device_layout_code == row.device_layout_code
                and saved_layout_snapshot.get("version") is not None
            ):
                layout = await _resolve_layout(
                    connection,
                    device_layout_code,
                    version=int(saved_layout_snapshot["version"]),
                )
            else:
                layout = await _resolve_layout(connection, device_layout_code)
            substantive_changed = (
                snapshot_hash != row.canonical_hash
                or planned_substrate_count != row.planned_substrate_count
                or layout.code != row.device_layout_code
            )
            resolved_manual_review = (
                False if substantive_changed else bool(row.requires_manual_review)
            )
            await connection.execute(
                update(experiment_conditions)
                .where(experiment_conditions.c.id == condition_id)
                .values(
                    condition_name=normalized_name,
                    recipe_snapshot=normalized_snapshot,
                    recipe_schema_version=int(normalized_snapshot["schema_version"]),
                    canonical_hash=snapshot_hash,
                    source_baseline_version_id=source_baseline_version_id,
                    device_layout_code=layout.code,
                    device_layout_snapshot=layout_snapshot(layout),
                    planned_substrate_count=planned_substrate_count,
                    expected_device_count=expected_device_count(
                        planned_substrate_count, layout
                    ),
                    requires_manual_review=resolved_manual_review,
                )
            )
            invalidated = await _invalidate_condition_exceptions(
                connection, condition_id, now=now
            )
            # An edit invalidates any approval the plan already holds: the
            # approved content is what changed, so the plan must return to
            # draft and pass the approval gate again (concurrent-release
            # contract: exactly one of edit/release commits).
            await connection.execute(
                update(experiments)
                .where(experiments.c.id == row.experiment_id)
                .values(plan_status=PlanStatus.DRAFT.value, updated_at=now)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="condition.update",
                entity_type="experiment_condition",
                entity_id=str(condition_id),
                details={"invalidated_exceptions": invalidated},
                client_ip=client_ip,
            )
        return await self.get_condition(condition_id)

    async def delete_condition(
        self,
        condition_id: int,
        *,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> None:
        now = _utc_now()
        async with self.database.begin() as connection:
            row = (
                await connection.execute(
                    select(
                        experiment_conditions.c.experiment_id,
                        experiments.c.plan_status,
                    )
                    .select_from(experiment_conditions)
                    .join(
                        experiments,
                        experiments.c.id == experiment_conditions.c.experiment_id,
                    )
                    .where(experiment_conditions.c.id == condition_id)
                    # Same parent-row lock order as update_condition.
                    .with_for_update(of=experiments)
                )
            ).one_or_none()
            if row is None:
                raise KeyError(f"unknown condition id: {condition_id}")
            if row.plan_status in {
                PlanStatus.RELEASED.value,
                PlanStatus.IN_PROGRESS.value,
                PlanStatus.COMPLETED.value,
                PlanStatus.CANCELLED.value,
            }:
                raise ValueError("released or closed plans cannot be modified")
            await connection.execute(
                delete(experiment_conditions).where(
                    experiment_conditions.c.id == condition_id
                )
            )
            await connection.execute(
                update(experiments)
                .where(experiments.c.id == row.experiment_id)
                # A delete invalidates any approval the plan holds, same as
                # an edit: the deleted condition was part of what was
                # approved (concurrent-release contract: exactly one of
                # delete/release commits).
                .values(plan_status=PlanStatus.DRAFT.value, updated_at=now)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="condition.delete",
                entity_type="experiment_condition",
                entity_id=str(condition_id),
                details={"experiment_id": row.experiment_id},
                client_ip=client_ip,
            )

    async def get_condition(self, condition_id: int) -> ConditionRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(experiment_conditions).where(
                        experiment_conditions.c.id == condition_id
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown condition id: {condition_id}")
        return _condition_record(row)

    async def list_conditions_for_experiment(
        self, experiment_id: int
    ) -> list[ConditionRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(experiment_conditions)
                    .where(experiment_conditions.c.experiment_id == experiment_id)
                    .order_by(experiment_conditions.c.id)
                )
            ).mappings().all()
        return [_condition_record(row) for row in rows]

    async def update_plan_status(
        self,
        experiment_id: int,
        plan_status: PlanStatus,
        *,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> None:
        async with self.database.begin() as connection:
            plan = (
                await connection.execute(
                    select(
                        experiments.c.created_by_id,
                        experiments.c.plan_type,
                        experiments.c.plan_status,
                    )
                    .where(experiments.c.id == experiment_id)
                    .with_for_update()
                )
            ).one_or_none()
            if plan is None:
                raise KeyError(f"unknown experiment id: {experiment_id}")
            actor_role = await _actor_role(connection, actor_user_id)
            if (
                actor_role == UserRole.STUDENT
                and plan.created_by_id != actor_user_id
            ):
                raise PermissionError("students can modify only their own plans")
            current = (
                PlanStatus(plan.plan_status)
                if plan.plan_status is not None
                else PlanStatus.DRAFT
            )
            _validate_plan_transition(current, plan_status, actor_role)
            await _validate_plan_conditions(
                connection,
                experiment_id,
                plan_type=plan.plan_type,
                target_status=plan_status,
            )
            await _require_fabrication_batches(connection, experiment_id, plan_status)
            await connection.execute(
                update(experiments)
                .where(experiments.c.id == experiment_id)
                .values(plan_status=plan_status.value, updated_at=_utc_now())
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="plan.status_change",
                entity_type="experiment",
                entity_id=str(experiment_id),
                details={
                    "from": current.value,
                    "to": plan_status.value,
                },
                client_ip=client_ip,
            )

    # ------------------------------------------------------------------
    # Substrate exception approval
    # ------------------------------------------------------------------
    async def request_substrate_exception(
        self,
        *,
        condition_id: int,
        requested_count: int,
        reason: str,
        requested_by_id: int | None,
        client_ip: str | None = None,
    ) -> SubstrateExceptionRecord:
        if not reason.strip():
            raise ValueError("exception reason must not be blank")
        if requested_count not in (1, 2):
            raise ValueError("a substrate exception may request only 1 or 2 substrates")
        now = _utc_now()
        async with self.database.begin() as connection:
            condition = (
                await connection.execute(
                    select(
                        experiment_conditions.c.planned_substrate_count,
                        experiments.c.created_by_id,
                        experiments.c.plan_status,
                    )
                    .select_from(experiment_conditions)
                    .join(
                        experiments,
                        experiments.c.id == experiment_conditions.c.experiment_id,
                    )
                    .where(experiment_conditions.c.id == condition_id)
                )
            ).one_or_none()
            if condition is None:
                raise KeyError(f"unknown condition id: {condition_id}")
            actor_role = await _actor_role(connection, requested_by_id)
            if (
                actor_role == UserRole.STUDENT
                and condition.created_by_id != requested_by_id
            ):
                raise PermissionError(
                    "students can request exceptions only for their own plans"
                )
            if condition.plan_status not in (None, PlanStatus.DRAFT.value):
                raise ValueError("exceptions can be requested only while a plan is draft")
            if condition.planned_substrate_count != requested_count:
                raise ValueError(
                    "requested count must equal the condition's planned substrate count"
                )
            try:
                result = await connection.execute(
                    insert(condition_substrate_exceptions).values(
                        condition_id=condition_id,
                        requested_count=requested_count,
                        reason=reason.strip(),
                        requested_by_id=requested_by_id,
                        requested_at=now,
                        decision=ExceptionDecision.PENDING.value,
                        decision_note="",
                    )
                )
            except IntegrityError as error:
                raise ValueError(
                    "this condition already has an active substrate exception"
                ) from error
            exception_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=requested_by_id,
                action="exception.request",
                entity_type="condition_substrate_exception",
                entity_id=str(exception_id),
                details={
                    "condition_id": condition_id,
                    "requested_count": requested_count,
                },
                client_ip=client_ip,
            )
        return await self.get_substrate_exception(exception_id)

    async def get_substrate_exception(
        self, exception_id: int
    ) -> SubstrateExceptionRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(condition_substrate_exceptions).where(
                        condition_substrate_exceptions.c.id == exception_id
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown substrate exception id: {exception_id}")
        return _exception_record(row)

    async def get_pending_exception_for_condition(
        self, condition_id: int
    ) -> SubstrateExceptionRecord | None:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(condition_substrate_exceptions).where(
                        and_(
                            condition_substrate_exceptions.c.condition_id == condition_id,
                            condition_substrate_exceptions.c.decision.in_([
                                ExceptionDecision.PENDING.value,
                                ExceptionDecision.APPROVED.value,
                            ]),
                        )
                    )
                    .order_by(condition_substrate_exceptions.c.id.desc())
                )
            ).mappings().one_or_none()
        return _exception_record(row) if row else None

    async def list_active_substrate_exceptions_for_experiment(
        self, experiment_id: int
    ) -> list[SubstrateExceptionRecord]:
        """Return the current pending or approved exception for each condition."""

        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(condition_substrate_exceptions)
                    .select_from(condition_substrate_exceptions)
                    .join(
                        experiment_conditions,
                        experiment_conditions.c.id
                        == condition_substrate_exceptions.c.condition_id,
                    )
                    .where(
                        experiment_conditions.c.experiment_id == experiment_id,
                        condition_substrate_exceptions.c.decision.in_([
                            ExceptionDecision.PENDING.value,
                            ExceptionDecision.APPROVED.value,
                        ]),
                    )
                    .order_by(condition_substrate_exceptions.c.id)
                )
            ).mappings().all()
        return [_exception_record(row) for row in rows]

    async def list_substrate_exceptions_for_experiment(
        self, experiment_id: int
    ) -> list[SubstrateExceptionRecord]:
        """Return the complete exception decision history for a plan export."""

        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(condition_substrate_exceptions)
                    .select_from(condition_substrate_exceptions)
                    .join(
                        experiment_conditions,
                        experiment_conditions.c.id
                        == condition_substrate_exceptions.c.condition_id,
                    )
                    .where(experiment_conditions.c.experiment_id == experiment_id)
                    .order_by(condition_substrate_exceptions.c.id)
                )
            ).mappings().all()
        return [_exception_record(row) for row in rows]

    async def decide_substrate_exception(
        self,
        exception_id: int,
        *,
        decision: ExceptionDecision,
        decided_by_id: int | None,
        decision_note: str = "",
        client_ip: str | None = None,
    ) -> SubstrateExceptionRecord:
        if decision not in (ExceptionDecision.APPROVED, ExceptionDecision.REJECTED):
            raise ValueError("decision must be approved or rejected")
        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, decided_by_id)
            if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
                raise PermissionError(
                    "instructor access is required to decide substrate exceptions"
                )
            exception = (
                await connection.execute(
                    select(
                        condition_substrate_exceptions.c.decision,
                        experiment_conditions.c.canonical_hash,
                    )
                    .select_from(condition_substrate_exceptions)
                    .join(
                        experiment_conditions,
                        experiment_conditions.c.id
                        == condition_substrate_exceptions.c.condition_id,
                    )
                    .where(condition_substrate_exceptions.c.id == exception_id)
                    .with_for_update()
                )
            ).one_or_none()
            if exception is None:
                raise KeyError(f"unknown substrate exception id: {exception_id}")
            if exception.decision != ExceptionDecision.PENDING.value:
                raise ValueError(
                    f"substrate exception {exception_id} is not pending"
                )
            values: dict[str, Any] = {
                "decision": decision.value,
                "decided_by_id": decided_by_id,
                "decided_at": now,
                "decision_note": decision_note.strip(),
            }
            if decision == ExceptionDecision.APPROVED:
                values["approved_condition_hash"] = exception.canonical_hash
            result = await connection.execute(
                update(condition_substrate_exceptions)
                .where(condition_substrate_exceptions.c.id == exception_id)
                .where(
                    condition_substrate_exceptions.c.decision
                    == ExceptionDecision.PENDING.value
                )
                .values(**values)
            )
            if result.rowcount != 1:
                raise ValueError(f"substrate exception {exception_id} changed concurrently")
            await _add_audit_event(
                connection,
                actor_user_id=decided_by_id,
                action=f"exception.{decision.value}",
                entity_type="condition_substrate_exception",
                entity_id=str(exception_id),
                details={"decision": decision.value},
                client_ip=client_ip,
            )
        return await self.get_substrate_exception(exception_id)

    async def invalidate_exceptions_for_condition(
        self,
        condition_id: int,
        *,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> int:
        """Invalidate any approved/pending exceptions after a condition change."""

        now = _utc_now()
        async with self.database.begin() as connection:
            count = await _invalidate_condition_exceptions(
                connection, condition_id, now=now
            )
            if count:
                await _add_audit_event(
                    connection,
                    actor_user_id=actor_user_id,
                    action="exception.invalidated",
                    entity_type="condition_substrate_exception",
                    entity_id=str(condition_id),
                    details={"invalidated_count": count},
                    client_ip=client_ip,
                )
        return count
