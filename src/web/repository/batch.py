"""Fabrication-batch-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from sqlalchemy.ext.asyncio import AsyncConnection
from datetime import datetime
from sqlalchemy import delete, func, insert, select, text, update

from ..condition_snapshot import (
    canonical_hash as condition_canonical_hash,
    validate_condition_snapshot,
)
from ..database import (
    BATCH_CODE_MAX_LENGTH,
    condition_substrate_exceptions,
    execution_deviations,
    experiment_conditions,
    experiments,
    fabrication_batch_conditions,
    fabrication_batches,
    fabrication_devices,
    fabrication_substrates,
    process_execution_members,
    process_executions,
    result_device_assignments,
    result_files,
    solution_preparation_uses,
    solution_preparations,
)
from ..device_layouts import DeviceLayout
from ..execution_snapshots import (
    PROCESS_SNAPSHOT_SCHEMA_VERSION,
    SOLUTION_SNAPSHOT_SCHEMA_VERSION,
    snapshot_hash,
    validate_process_snapshot,
    validate_solution_snapshot,
)
from .helpers import (
    _actor_role,
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _optional_utc,
    _utc_now,
)
from ..services.catalog_service import (
    resolve_layout as _resolve_layout,
)
from .records import DEVIATION_TYPES
from .records import (
    BatchStatus,
    ExceptionDecision,
    ExecutionDeviationRecord,
    ExecutionStatus,
    FabricationBatchRecord,
    FabricationDeviceRecord,
    FabricationSubstrateRecord,
    FrozenBatchConditionRecord,
    PlanStatus,
    PreparationStatus,
    ProcessExecutionRecord,
    SolutionPreparationRecord,
    SubstrateDeviceStatus,
    UserRole,
)
from .result import _result_assignment_statement, _result_record

import hashlib
import json
import math

async def _attach_substrates_to_condition_executions(
    connection: AsyncConnection,
    batch_condition_id: int,
    substrate_ids: Sequence[int],
) -> int:
    """Add the missing process_execution_members rows for new substrates.

    Every execution group whose members target the condition gains one member
    row per new substrate, copying the group's frozen execution identity
    (layer ordinal and layer snapshot hash); no recipe or live-catalog
    reference is invented.  Returns the count of member rows actually
    inserted.
    """

    if not substrate_ids:
        return 0
    groups = (
        await connection.execute(
            select(
                process_execution_members.c.process_execution_id,
                process_execution_members.c.layer_ordinal,
                process_execution_members.c.layer_snapshot_hash,
            )
            .distinct()
            .where(
                process_execution_members.c.batch_condition_id
                == batch_condition_id
            )
        )
    ).all()
    inserted = 0
    for process_execution_id, layer_ordinal, layer_snapshot_hash in groups:
        existing_ids = set(
            (
                await connection.execute(
                    select(process_execution_members.c.substrate_id).where(
                        process_execution_members.c.process_execution_id
                        == int(process_execution_id),
                        process_execution_members.c.layer_ordinal
                        == int(layer_ordinal),
                        process_execution_members.c.batch_condition_id
                        == batch_condition_id,
                    )
                )
            ).scalars().all()
        )
        for substrate_id in substrate_ids:
            if int(substrate_id) in existing_ids:
                continue
            await connection.execute(
                insert(process_execution_members).values(
                    process_execution_id=int(process_execution_id),
                    substrate_id=int(substrate_id),
                    batch_condition_id=batch_condition_id,
                    layer_ordinal=int(layer_ordinal),
                    layer_snapshot_hash=layer_snapshot_hash,
                )
            )
            inserted += 1
    return inserted

async def _batch_for_actor(
    connection: AsyncConnection,
    batch_id: int,
    actor_user_id: int,
    *,
    allowed_statuses: set[BatchStatus] | None = None,
) -> Mapping[str, Any]:
    """Lock a batch and enforce experiment ownership for student writes."""

    row = (
        await connection.execute(
            select(
                fabrication_batches,
                experiments.c.created_by_id.label("experiment_owner_id"),
            )
            .select_from(
                fabrication_batches.join(
                    experiments,
                    experiments.c.id == fabrication_batches.c.experiment_id,
                )
            )
            .where(fabrication_batches.c.id == batch_id)
            .with_for_update()
        )
    ).mappings().one_or_none()
    if row is None:
        raise KeyError(f"unknown fabrication batch id: {batch_id}")
    role = await _actor_role(connection, actor_user_id)
    if role == UserRole.STUDENT and row["experiment_owner_id"] != actor_user_id:
        raise PermissionError("students can update batches only for their own plans")
    current = BatchStatus(row["status"])
    if allowed_statuses is not None and current not in allowed_statuses:
        allowed_text = ", ".join(sorted(status.value for status in allowed_statuses))
        raise ValueError(
            f"batch status must be one of [{allowed_text}] for this operation, "
            f"got '{current.value}'"
        )
    return row

async def _materialize_condition_substrates(
    connection: AsyncConnection,
    *,
    batch_condition_id: int,
    substrate_code_prefix: str,
    layout: DeviceLayout,
    start_ordinal: int,
    count: int,
    now: datetime,
) -> list[int]:
    """Create blank-mark substrate rows with the layout's complete device rows.

    Shared by batch creation and by completion-time materialization of extra
    actual substrates so the two paths cannot drift. Returns the inserted
    substrate ids in ordinal order.
    """

    if count <= 0:
        return []
    if layout.devices_per_substrate > 9:
        raise ValueError("a marked substrate cannot exceed 9 devices")
    substrate_ids: list[int] = []
    for ordinal in range(start_ordinal, start_ordinal + count):
        substrate_code = f"{substrate_code_prefix}-S{ordinal:02d}"
        # The physical laser mark (e.g. A001) is a factory-etched fact recorded
        # at result-CSV upload; device marks follow once the CSV associates
        # the substrate, so both stay null here.
        sub_result = await connection.execute(
            insert(fabrication_substrates).values(
                batch_condition_id=batch_condition_id,
                substrate_ordinal=ordinal,
                substrate_code=substrate_code,
                substrate_mark=None,
                status="planned",
                notes="",
                created_at=now,
                updated_at=now,
            )
        )
        substrate_id = _inserted_id(sub_result)
        substrate_ids.append(substrate_id)
        for device_ordinal in range(1, layout.devices_per_substrate + 1):
            await connection.execute(
                insert(fabrication_devices).values(
                    substrate_id=substrate_id,
                    device_ordinal=device_ordinal,
                    device_code=f"{substrate_code}-D{device_ordinal:02d}",
                    device_mark=None,
                    device_active_area_cm2=str(layout.device_active_area_cm2),
                    status="planned",
                    notes="",
                    created_at=now,
                    updated_at=now,
                )
            )
    return substrate_ids

async def _record_actual_substrate_counts(
    connection: AsyncConnection,
    batch_id: int,
    actual_substrate_counts: Mapping[int, int] | None,
    *,
    batch_code: str,
    now: datetime,
    shortfall_deviations: Sequence[tuple[int, str]] | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    """Record and validate actual substrate counts at batch completion.

    Returns a summary of new rows materialized (substrates, devices, members)
    for the audit event.
    """
    if not actual_substrate_counts:
        raise ValueError(
            "every condition must declare its actual substrate count before "
            "the batch can be completed"
        )
    summary: dict[str, Any] = {
        "new_substrates": 0,
        "new_devices": 0,
        "new_execution_members": 0,
        "new_shortfall_deviations": 0,
    }
    condition_rows = (
        await connection.execute(
            select(
                fabrication_batch_conditions.c.id,
                fabrication_batch_conditions.c.condition_name,
                fabrication_batch_conditions.c.condition_code,
                fabrication_batch_conditions.c.device_layout_code,
                fabrication_batch_conditions.c.device_layout_snapshot,
                fabrication_batch_conditions.c.planned_substrate_count,
                fabrication_batch_conditions.c.recipe_snapshot,
            ).where(
                fabrication_batch_conditions.c.fabrication_batch_id == batch_id
            )
        )
    ).mappings().all()
    condition_ids = {int(row["id"]) for row in condition_rows}
    provided_ids = set(actual_substrate_counts.keys())
    if provided_ids != condition_ids:
        missing = sorted(condition_ids - provided_ids)
        unknown = sorted(provided_ids - condition_ids)
        if missing or unknown:
            raise ValueError(
                "actual substrate counts must cover exactly the batch "
                f"conditions (missing: {missing}, unknown: {unknown})"
            )
    if sum(int(count) for count in actual_substrate_counts.values()) > 99:
        raise ValueError("a fabrication batch cannot exceed 99 marked substrates")
    condition_names = {int(row["id"]): str(row["condition_name"]) for row in condition_rows}
    normalized_shortfalls: dict[int, str] = {}
    for condition_id, description in shortfall_deviations or []:
        if int(condition_id) not in condition_ids:
            raise ValueError(
                f"shortfall deviation targets unknown condition id {condition_id}"
            )
        if int(condition_id) in normalized_shortfalls:
            raise ValueError(
                f"condition {condition_names[int(condition_id)]} has duplicate "
                "shortfall explanations"
            )
        text = str(description).strip()
        if not text:
            raise ValueError(
                f"condition {condition_names[int(condition_id)]} has a blank "
                "shortfall explanation"
            )
        normalized_shortfalls[int(condition_id)] = text
    # ── Pre-check pass: validate ALL conditions before any write ─────
    # Every condition must pass validation before a single substrate, device,
    # member, or deviation row is inserted.  This guarantees that a failure
    # in condition 2 cannot leave condition 1's materialization behind even
    # within the transaction (defense in depth on top of the rollback).
    for row in condition_rows:
        condition_id = int(row["id"])
        actual = int(actual_substrate_counts[condition_id])
        planned = int(row["planned_substrate_count"])
        has_shortfall = actual < planned
        if actual < 0:
            raise ValueError(
                f"actual substrate count for {row['condition_name']} must not "
                "be negative"
            )
        if condition_id in normalized_shortfalls and not has_shortfall:
            raise ValueError(
                f"condition {row['condition_name']} has no shortfall "
                f"({actual} actual vs {planned} planned); remove its "
                "shortfall explanation"
            )
        if has_shortfall and condition_id not in normalized_shortfalls:
            raise ValueError(
                f"condition {row['condition_name']} declares {actual} "
                f"actual substrates vs {planned} planned; include a "
                "shortfall_deviation in the completion request explaining "
                "the shortfall"
            )
        if actual > planned:
            required_ordinals = _required_layer_ordinals_from_snapshot(
                row.get("recipe_snapshot")
            )
            existing_ordinals = set(
                (
                    await connection.execute(
                        select(
                            process_execution_members.c.layer_ordinal
                        )
                        .distinct()
                        .where(
                            process_execution_members.c.batch_condition_id
                            == condition_id
                        )
                    )
                ).scalars().all()
            )
            # Even when the recipe has no required ordinals, the condition
            # must have at least one execution group to attach new substrates.
            if not existing_ordinals:
                raise ValueError(
                    f"condition {row['condition_name']} has no frozen "
                    "execution groups to attach the new substrates to; "
                    "the batch state is inconsistent"
                )
            if required_ordinals:
                missing_ordinals = required_ordinals - existing_ordinals
                if missing_ordinals:
                    raise ValueError(
                        f"condition {row['condition_name']} is missing "
                        f"frozen execution groups for layer ordinals "
                        f"{sorted(missing_ordinals)}; cannot materialize "
                        "extra substrates without all required groups"
                    )

    # ── Write pass: all pre-checks passed, now commit writes ─────────
    for row in condition_rows:
        condition_id = int(row["id"])
        actual = int(actual_substrate_counts[condition_id])
        planned = int(row["planned_substrate_count"])
        has_shortfall = actual < planned
        if has_shortfall:
            await connection.execute(
                insert(execution_deviations).values(
                    fabrication_batch_id=batch_id,
                    category="substrate",
                    severity="warning",
                    deviation_type="fabrication_shortfall",
                    description=normalized_shortfalls[condition_id],
                    planned_value={"substrate_count": planned},
                    actual_value={"substrate_count": actual},
                    recorded_by_id=actor_user_id,
                    recorded_at=now,
                    condition_id=condition_id,
                    created_at=now,
                )
            )
            summary["new_shortfall_deviations"] += 1
        await connection.execute(
            update(fabrication_batch_conditions)
            .where(fabrication_batch_conditions.c.id == condition_id)
            .values(actual_substrate_count=actual)
        )
        if actual > planned:
            # Extra substrates must match the geometry frozen when the batch
            # was created, not a later catalog version.
            frozen_layout_snapshot = row["device_layout_snapshot"]
            if isinstance(frozen_layout_snapshot, str):
                frozen_layout_snapshot = json.loads(frozen_layout_snapshot)
            frozen_version = (
                int(frozen_layout_snapshot["version"])
                if isinstance(frozen_layout_snapshot, Mapping)
                and frozen_layout_snapshot.get("version") is not None
                else None
            )
            extra_layout = await _resolve_layout(
                connection,
                str(row["device_layout_code"]),
                version=frozen_version,
            )
            new_substrate_ids = await _materialize_condition_substrates(
                connection,
                batch_condition_id=condition_id,
                substrate_code_prefix=f"{batch_code}-{row['condition_code']}",
                layout=extra_layout,
                start_ordinal=planned + 1,
                count=actual - planned,
                now=now,
            )
            summary["new_substrates"] += len(new_substrate_ids)
            summary["new_devices"] += len(new_substrate_ids) * extra_layout.devices_per_substrate
            member_count = await _attach_substrates_to_condition_executions(
                connection, condition_id, new_substrate_ids
            )
            summary["new_execution_members"] += member_count
    summary["actual_substrate_counts"] = {
        str(k): v for k, v in actual_substrate_counts.items()
    }
    return summary

async def _validate_batch_complete(
    connection: AsyncConnection, batch_id: int
) -> None:
    incomplete_preparations = await connection.scalar(
        select(func.count())
        .select_from(solution_preparations)
        .where(
            solution_preparations.c.fabrication_batch_id == batch_id,
            solution_preparations.c.status.not_in(
                [PreparationStatus.CONSUMED.value, PreparationStatus.DISCARDED.value]
            ),
        )
    )
    if int(incomplete_preparations or 0):
        raise ValueError(
            "all solution preparations must be consumed or discarded before completion"
        )
    incomplete_executions = await connection.scalar(
        select(func.count())
        .select_from(process_executions)
        .where(
            process_executions.c.fabrication_batch_id == batch_id,
            process_executions.c.status.not_in(
                [
                    ExecutionStatus.COMPLETED.value,
                    ExecutionStatus.FAILED.value,
                    ExecutionStatus.CANCELLED.value,
                ]
            ),
        )
    )
    if int(incomplete_executions or 0):
        raise ValueError(
            "all process executions must be terminal before batch completion"
        )

async def _validate_batch_ready(
    connection: AsyncConnection, batch_id: int
) -> None:
    orphan_preparations = await connection.scalar(
        select(func.count())
        .select_from(solution_preparations)
        .where(
            solution_preparations.c.fabrication_batch_id == batch_id,
            ~select(solution_preparation_uses.c.id)
            .where(
                solution_preparation_uses.c.solution_preparation_id
                == solution_preparations.c.id
            )
            .exists(),
        )
    )
    if int(orphan_preparations or 0):
        raise ValueError("every solution preparation must have at least one use")
    orphan_executions = await connection.scalar(
        select(func.count())
        .select_from(process_executions)
        .where(
            process_executions.c.fabrication_batch_id == batch_id,
            ~select(process_execution_members.c.id)
            .where(
                process_execution_members.c.process_execution_id
                == process_executions.c.id
            )
            .exists(),
        )
    )
    if int(orphan_executions or 0):
        raise ValueError("every process execution must have at least one member")

async def _validate_deviation_links(
    connection: AsyncConnection,
    *,
    fabrication_batch_id: int,
    supersedes_deviation_id: int | None,
    solution_preparation_id: int | None,
    process_execution_id: int | None,
    substrate_id: int | None,
    device_id: int | None,
    condition_id: int | None,
) -> None:
    targets = [
        solution_preparation_id,
        process_execution_id,
        substrate_id,
        device_id,
        condition_id,
    ]
    if sum(value is not None for value in targets) > 1:
        raise ValueError(
            "a deviation may target the batch or one specific execution entity"
        )

    if supersedes_deviation_id is not None:
        parent_batch = await connection.scalar(
            select(execution_deviations.c.fabrication_batch_id).where(
                execution_deviations.c.id == supersedes_deviation_id
            )
        )
        if parent_batch is None or int(parent_batch) != fabrication_batch_id:
            raise ValueError("superseded deviation must belong to the same batch")

    linked_batch: int | None = None
    if solution_preparation_id is not None:
        linked_batch = await connection.scalar(
            select(solution_preparations.c.fabrication_batch_id).where(
                solution_preparations.c.id == solution_preparation_id
            )
        )
    elif process_execution_id is not None:
        linked_batch = await connection.scalar(
            select(process_executions.c.fabrication_batch_id).where(
                process_executions.c.id == process_execution_id
            )
        )
    elif substrate_id is not None:
        linked_batch = await connection.scalar(
            select(fabrication_batch_conditions.c.fabrication_batch_id)
            .select_from(
                fabrication_substrates.join(
                    fabrication_batch_conditions,
                    fabrication_batch_conditions.c.id
                    == fabrication_substrates.c.batch_condition_id,
                )
            )
            .where(fabrication_substrates.c.id == substrate_id)
        )
    elif device_id is not None:
        linked_batch = await connection.scalar(
            select(fabrication_batch_conditions.c.fabrication_batch_id)
            .select_from(
                fabrication_devices.join(
                    fabrication_substrates,
                    fabrication_substrates.c.id
                    == fabrication_devices.c.substrate_id,
                ).join(
                    fabrication_batch_conditions,
                    fabrication_batch_conditions.c.id
                    == fabrication_substrates.c.batch_condition_id,
                )
            )
            .where(fabrication_devices.c.id == device_id)
        )
    elif condition_id is not None:
        linked_batch = await connection.scalar(
            select(fabrication_batch_conditions.c.fabrication_batch_id).where(
                fabrication_batch_conditions.c.id == condition_id
            )
        )
    if any(value is not None for value in targets):
        if linked_batch is None or int(linked_batch) != fabrication_batch_id:
            raise ValueError("deviation target must belong to the same batch")

def _batch_status_transitions(
    current: BatchStatus,
) -> set[BatchStatus]:
    allowed = {
        BatchStatus.DRAFT: {BatchStatus.READY, BatchStatus.CANCELLED},
        BatchStatus.READY: {BatchStatus.IN_PROGRESS, BatchStatus.CANCELLED},
        BatchStatus.IN_PROGRESS: {BatchStatus.COMPLETED, BatchStatus.CANCELLED},
        BatchStatus.COMPLETED: set(),
        BatchStatus.CANCELLED: set(),
    }
    return allowed.get(current, set())

def _execution_deviation_record(row: Mapping[str, Any]) -> ExecutionDeviationRecord:
    planned = row.get("planned_value")
    if isinstance(planned, str):
        planned = json.loads(planned)
    actual = row.get("actual_value")
    if isinstance(actual, str):
        actual = json.loads(actual)
    return ExecutionDeviationRecord(
        id=int(row["id"]),
        fabrication_batch_id=int(row["fabrication_batch_id"]),
        category=str(row["category"]),
        severity=str(row["severity"]),
        deviation_type=str(row["deviation_type"]),
        description=str(row["description"]),
        planned_value=dict(planned) if planned else None,
        actual_value=dict(actual) if actual else None,
        recorded_by_id=row["recorded_by_id"],
        recorded_at=_as_utc(row["recorded_at"]),
        supersedes_deviation_id=row["supersedes_deviation_id"],
        solution_preparation_id=row["solution_preparation_id"],
        process_execution_id=row["process_execution_id"],
        substrate_id=row["substrate_id"],
        device_id=row["device_id"],
        condition_id=row["condition_id"],
        created_at=_as_utc(row["created_at"]),
    )

def _execution_status_transitions(
    current: ExecutionStatus,
) -> set[ExecutionStatus]:
    allowed = {
        ExecutionStatus.PLANNED: {
            ExecutionStatus.READY,
            ExecutionStatus.RUNNING,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.READY: {
            ExecutionStatus.RUNNING,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.RUNNING: {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        },
        ExecutionStatus.COMPLETED: set(),
        ExecutionStatus.FAILED: set(),
        ExecutionStatus.CANCELLED: set(),
    }
    return allowed.get(current, set())

def _fabrication_batch_record(row: Mapping[str, Any]) -> FabricationBatchRecord:
    return FabricationBatchRecord(
        id=int(row["id"]),
        experiment_id=int(row["experiment_id"]),
        batch_number=int(row["batch_number"]),
        batch_code=str(row["batch_code"]),
        status=BatchStatus(row["status"]),
        condition_set_hash=str(row["condition_set_hash"]),
        notes=str(row.get("notes", "")),
        created_by_id=row["created_by_id"],
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
        started_at=_optional_utc(row.get("started_at")),
        completed_at=_optional_utc(row.get("completed_at")),
        cancelled_at=_optional_utc(row.get("cancelled_at")),
    )

def _fabrication_device_assignment_statement(batch_id: int) -> Any:
    return (
        select(
            fabrication_devices.c.id.label("fabrication_device_id"),
            fabrication_devices.c.device_code,
            fabrication_devices.c.device_mark,
            fabrication_devices.c.status.label("device_status"),
            fabrication_substrates.c.id.label("substrate_id"),
            fabrication_substrates.c.substrate_code,
            fabrication_substrates.c.substrate_mark,
            fabrication_batch_conditions.c.id.label("batch_condition_id"),
            fabrication_batch_conditions.c.source_condition_id,
            fabrication_batch_conditions.c.condition_code,
            fabrication_batch_conditions.c.condition_name,
            fabrication_batch_conditions.c.role,
        )
        .select_from(fabrication_devices)
        .join(
            fabrication_substrates,
            fabrication_substrates.c.id == fabrication_devices.c.substrate_id,
        )
        .join(
            fabrication_batch_conditions,
            fabrication_batch_conditions.c.id
            == fabrication_substrates.c.batch_condition_id,
        )
        .where(
            fabrication_batch_conditions.c.fabrication_batch_id == batch_id,
            fabrication_devices.c.status != SubstrateDeviceStatus.EXCLUDED.value,
        )
        .order_by(
            fabrication_batch_conditions.c.condition_code,
            fabrication_substrates.c.substrate_ordinal,
            fabrication_devices.c.device_ordinal,
        )
    )

def _fabrication_device_record(row: Mapping[str, Any]) -> FabricationDeviceRecord:
    return FabricationDeviceRecord(
        id=int(row["id"]),
        substrate_id=int(row["substrate_id"]),
        device_ordinal=int(row["device_ordinal"]),
        device_code=str(row["device_code"]),
        device_mark=(
            str(row["device_mark"])
            if row["device_mark"] is not None
            else None
        ),
        device_active_area_cm2=str(row["device_active_area_cm2"]),
        status=SubstrateDeviceStatus(row["status"]),
        notes=str(row.get("notes", "")),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
    )

def _fabrication_substrate_record(row: Mapping[str, Any]) -> FabricationSubstrateRecord:
    return FabricationSubstrateRecord(
        id=int(row["id"]),
        batch_condition_id=int(row["batch_condition_id"]),
        substrate_ordinal=int(row["substrate_ordinal"]),
        substrate_code=str(row["substrate_code"]),
        substrate_mark=(
            str(row["substrate_mark"])
            if row["substrate_mark"] is not None
            else None
        ),
        status=SubstrateDeviceStatus(row["status"]),
        notes=str(row.get("notes", "")),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
    )

def _frozen_batch_condition_record(row: Mapping[str, Any]) -> FrozenBatchConditionRecord:
    snapshot = row["recipe_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    layout_snap = row["device_layout_snapshot"]
    if isinstance(layout_snap, str):
        layout_snap = json.loads(layout_snap)
    return FrozenBatchConditionRecord(
        id=int(row["id"]),
        fabrication_batch_id=int(row["fabrication_batch_id"]),
        source_condition_id=int(row["source_condition_id"]),
        condition_code=str(row["condition_code"]),
        condition_name=str(row["condition_name"]),
        role=str(row["role"]),
        source_condition_hash=str(row["source_condition_hash"]),
        recipe_snapshot=dict(snapshot),
        recipe_schema_version=int(row["recipe_schema_version"]),
        device_layout_code=str(row["device_layout_code"]),
        device_layout_snapshot=dict(layout_snap),
        planned_substrate_count=int(row["planned_substrate_count"]),
        expected_device_count=int(row["expected_device_count"]),
        actual_substrate_count=(
            int(row["actual_substrate_count"])
            if row["actual_substrate_count"] is not None
            else None
        ),
    )

def _preparation_status_transitions(
    current: PreparationStatus,
) -> set[PreparationStatus]:
    allowed = {
        PreparationStatus.PLANNED: {
            PreparationStatus.PREPARING,
            PreparationStatus.READY,
            PreparationStatus.DISCARDED,
        },
        PreparationStatus.PREPARING: {
            PreparationStatus.READY,
            PreparationStatus.DISCARDED,
        },
        PreparationStatus.READY: {
            PreparationStatus.CONSUMED,
            PreparationStatus.DISCARDED,
        },
        PreparationStatus.CONSUMED: set(),
        PreparationStatus.DISCARDED: set(),
    }
    return allowed.get(current, set())

def _process_execution_record(row: Mapping[str, Any]) -> ProcessExecutionRecord:
    planned = row["planned_process_snapshot"]
    if isinstance(planned, str):
        planned = json.loads(planned)
    actual = row.get("actual_process_snapshot")
    if isinstance(actual, str):
        actual = json.loads(actual)
    return ProcessExecutionRecord(
        id=int(row["id"]),
        fabrication_batch_id=int(row["fabrication_batch_id"]),
        execution_code=str(row["execution_code"]),
        method=str(row["method"]),
        layer_role=str(row["layer_role"]),
        layer_type=str(row["layer_type"]),
        layer_name=str(row["layer_name"]),
        status=ExecutionStatus(row["status"]),
        is_shared=bool(row["is_shared"]),
        planned_process_snapshot=dict(planned),
        planned_snapshot_schema_version=int(
            row["planned_snapshot_schema_version"]
        ),
        planned_canonical_hash=str(row["planned_canonical_hash"]),
        actual_process_snapshot=dict(actual) if actual else None,
        actual_snapshot_schema_version=(
            int(row["actual_snapshot_schema_version"])
            if row.get("actual_snapshot_schema_version") is not None
            else None
        ),
        actual_canonical_hash=row.get("actual_canonical_hash"),
        actual_recording_mode=row.get("actual_recording_mode"),
        equipment_identifier=row.get("equipment_identifier"),
        executed_by_id=row["executed_by_id"],
        started_at=_optional_utc(row.get("started_at")),
        completed_at=_optional_utc(row.get("completed_at")),
        notes=str(row.get("notes", "")),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
    )

def _required_layer_ordinals_from_snapshot(
    recipe_snapshot: Any,
) -> set[int]:
    """Derive the layer ordinals that must have frozen execution groups.

    Mirrors ``_create_execution_groupings``: every device layer with a
    ``process`` key contributes its 1-based ordinal, and the perovskite
    deposition process (spin/vcd/anneal) contributes the perovskite
    layer's ordinal.
    """
    if isinstance(recipe_snapshot, str):
        recipe_snapshot = json.loads(recipe_snapshot)
    if not isinstance(recipe_snapshot, dict):
        return set()
    device = recipe_snapshot.get("device", recipe_snapshot)
    layers = device.get("layers", []) if isinstance(device, dict) else []
    required: set[int] = set()
    for l_idx, layer in enumerate(layers, start=1):
        if isinstance(layer, dict) and layer.get("process"):
            required.add(l_idx)
    perovskite_index = next(
        (i for i, layer in enumerate(layers, start=1)
         if isinstance(layer, dict) and layer.get("layer_type") == "perovskite"),
        None,
    )
    if perovskite_index is not None:
        deposition = recipe_snapshot.get("deposition_process") or {}
        if isinstance(deposition, dict) and (
            deposition.get("spin_steps")
            or deposition.get("vcd_stages")
            or deposition.get("anneal_steps")
        ):
            required.add(perovskite_index)
    return required

def _solution_preparation_record(row: Mapping[str, Any]) -> SolutionPreparationRecord:
    planned = row["planned_solution_snapshot"]
    if isinstance(planned, str):
        planned = json.loads(planned)
    actual = row.get("actual_solution_snapshot")
    if isinstance(actual, str):
        actual = json.loads(actual)
    return SolutionPreparationRecord(
        id=int(row["id"]),
        fabrication_batch_id=int(row["fabrication_batch_id"]),
        preparation_code=str(row["preparation_code"]),
        status=PreparationStatus(row["status"]),
        planned_solution_snapshot=dict(planned),
        planned_snapshot_schema_version=int(
            row["planned_snapshot_schema_version"]
        ),
        planned_canonical_hash=str(row["planned_canonical_hash"]),
        actual_solution_snapshot=dict(actual) if actual else None,
        actual_snapshot_schema_version=(
            int(row["actual_snapshot_schema_version"])
            if row.get("actual_snapshot_schema_version") is not None
            else None
        ),
        actual_canonical_hash=row.get("actual_canonical_hash"),
        actual_recording_mode=row.get("actual_recording_mode"),
        prepared_by_id=row["prepared_by_id"],
        prepared_at=_optional_utc(row.get("prepared_at")),
        completed_at=_optional_utc(row.get("completed_at")),
        notes=str(row.get("notes", "")),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
    )

class FabricationBatchesMixin:
    """Fabrication batches, solution preparations, process executions, and execution deviations."""

    # ------------------------------------------------------------------
    # Fabrication Batches
    # ------------------------------------------------------------------
    async def create_fabrication_batch(
        self,
        experiment_id: int,
        *,
        notes: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> FabricationBatchRecord:
        """Create a fabrication batch, freeze conditions, generate substrates/devices.

        This is a single-transaction operation that creates the batch, copies
        condition snapshots, generates substrates and devices, and creates
        solution preparation and process execution groupings.
        """
        normalized_notes = notes.strip()[:2000]
        now = _utc_now()
        async with self.database.begin() as connection:
            # 1. Verify experiment exists and is released
            plan_row = (
                await connection.execute(
                    select(
                        experiments.c.id,
                        experiments.c.experiment_code,
                        experiments.c.plan_status,
                        experiments.c.plan_type,
                        experiments.c.created_by_id,
                    )
                    .where(experiments.c.id == experiment_id)
                    .with_for_update()
                )
            ).one_or_none()
            if plan_row is None:
                raise KeyError(f"unknown experiment id: {experiment_id}")

            # Batches may be frozen while released (the normal path) or while
            # fabrication is already in progress (recovery when the student
            # started fabrication without creating a batch first).
            allowed_plan_statuses = {
                PlanStatus.RELEASED.value,
                PlanStatus.IN_PROGRESS.value,
            }
            if plan_row.plan_status not in allowed_plan_statuses:
                raise ValueError(
                    f"plan status must be 'released' or 'in_progress' to create "
                    f"a batch, got '{plan_row.plan_status}'"
                )

            # 2. Verify actor permissions
            actor_role = await _actor_role(connection, actor_user_id)
            if (
                actor_role == UserRole.STUDENT
                and plan_row.created_by_id != actor_user_id
            ):
                raise PermissionError(
                    "students can create batches only for their own plans"
                )

            # 3. Load conditions and verify
            condition_rows = (
                await connection.execute(
                    select(experiment_conditions)
                    .where(experiment_conditions.c.experiment_id == experiment_id)
                    .order_by(experiment_conditions.c.id)
                )
            ).mappings().all()

            if not condition_rows:
                raise ValueError("a plan must contain at least one condition")

            # Validate no manual review conditions
            for row in condition_rows:
                if row["requires_manual_review"]:
                    raise ValueError(
                        f"condition {row['condition_code']} requires manual review"
                    )
                # Validate hash consistency
                normalized = validate_condition_snapshot(row["recipe_snapshot"])
                if condition_canonical_hash(normalized) != row["canonical_hash"]:
                    raise ValueError(
                        f"condition {row['condition_code']} snapshot hash is inconsistent"
                    )

            # 4. Validate substrate exceptions for <3 conditions
            for row in condition_rows:
                if int(row["planned_substrate_count"]) < 3:
                    exception = (
                        await connection.execute(
                            select(condition_substrate_exceptions)
                            .where(
                                condition_substrate_exceptions.c.condition_id == row["id"],
                                condition_substrate_exceptions.c.decision == ExceptionDecision.APPROVED.value,
                                condition_substrate_exceptions.c.approved_condition_hash == row["canonical_hash"],
                            )
                            .order_by(condition_substrate_exceptions.c.id.desc())
                        )
                    ).mappings().one_or_none()
                    if exception is None:
                        raise ValueError(
                            f"condition {row['condition_code']} has fewer than 3 substrates "
                            "and no valid approval"
                        )

            # 5. Compute next batch number
            max_batch = await connection.scalar(
                select(func.coalesce(func.max(fabrication_batches.c.batch_number), 0))
                .where(fabrication_batches.c.experiment_id == experiment_id)
            )
            next_batch_number = int(max_batch or 0) + 1
            batch_code = f"{plan_row.experiment_code}-B{next_batch_number:02d}"
            if len(batch_code) > BATCH_CODE_MAX_LENGTH:
                raise ValueError(f"batch code must not exceed {BATCH_CODE_MAX_LENGTH} characters")

            # 6. Hash every execution-relevant condition attribute, not only the recipe.
            condition_fingerprints = sorted(
                (
                    {
                        "condition_code": str(row["condition_code"]),
                        "role": str(row["role"]),
                        "recipe_hash": str(row["canonical_hash"]),
                        "device_layout_code": str(row["device_layout_code"]),
                        "device_layout_snapshot": row["device_layout_snapshot"],
                        "planned_substrate_count": int(row["planned_substrate_count"]),
                        "expected_device_count": int(row["expected_device_count"]),
                    }
                    for row in condition_rows
                ),
                key=lambda item: item["condition_code"],
            )
            condition_set_hash = hashlib.sha256(
                json.dumps(
                    condition_fingerprints,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()

            # 7. Create the batch
            result = await connection.execute(
                insert(fabrication_batches).values(
                    experiment_id=experiment_id,
                    batch_number=next_batch_number,
                    batch_code=batch_code,
                    status=BatchStatus.DRAFT.value,
                    condition_set_hash=condition_set_hash,
                    notes=normalized_notes,
                    created_by_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            batch_id = _inserted_id(result)

            # 8. Freeze condition snapshots into batch_conditions
            layout_map: dict[int, Any] = {}
            for row in condition_rows:
                snapshot = row["recipe_snapshot"]
                if isinstance(snapshot, str):
                    snapshot = json.loads(snapshot)
                layout_snap = row["device_layout_snapshot"]
                if isinstance(layout_snap, str):
                    layout_snap = json.loads(layout_snap)

                bc_result = await connection.execute(
                    insert(fabrication_batch_conditions).values(
                        fabrication_batch_id=batch_id,
                        source_condition_id=row["id"],
                        condition_code=str(row["condition_code"]),
                        condition_name=str(row["condition_name"]),
                        role=str(row["role"]),
                        source_condition_hash=str(row["canonical_hash"]),
                        recipe_snapshot=snapshot,
                        recipe_schema_version=int(row["recipe_schema_version"]),
                        device_layout_code=str(row["device_layout_code"]),
                        device_layout_snapshot=layout_snap,
                        planned_substrate_count=int(row["planned_substrate_count"]),
                        expected_device_count=int(row["expected_device_count"]),
                    )
                )
                bc_id = _inserted_id(bc_result)
                layout_map[bc_id] = {
                    "layout_code": str(row["device_layout_code"]),
                    "layout_version": (
                        int(layout_snap["version"])
                        if isinstance(layout_snap, Mapping)
                        and layout_snap.get("version") is not None
                        else None
                    ),
                    "substrate_count": int(row["planned_substrate_count"]),
                    "condition_code": str(row["condition_code"]),
                    "recipe_snapshot": snapshot,
                }

            # 9. Generate substrates and devices
            total_substrates = sum(item["substrate_count"] for item in layout_map.values())
            if total_substrates > 99:
                raise ValueError("a fabrication batch cannot exceed 99 marked substrates")
            layout_cache: dict[tuple[str, int | None], DeviceLayout] = {}
            for bc_id, lm in layout_map.items():
                cache_key = (lm["layout_code"], lm["layout_version"])
                layout = layout_cache.get(cache_key)
                if layout is None:
                    layout = await _resolve_layout(
                        connection, lm["layout_code"], version=lm["layout_version"]
                    )
                    layout_cache[cache_key] = layout
                # The physical laser mark (e.g. A001) is a factory-etched
                # fact recorded at result-CSV upload, not generated here.
                await _materialize_condition_substrates(
                    connection,
                    batch_condition_id=bc_id,
                    substrate_code_prefix=f"{batch_code}-{lm['condition_code']}",
                    layout=layout,
                    start_ordinal=1,
                    count=lm["substrate_count"],
                    now=now,
                )

            # 10. Create solution preparation groupings
            await self._create_preparation_groupings(
                connection, batch_id, batch_code, layout_map, now
            )

            # 11. Create process execution groupings
            await self._create_execution_groupings(
                connection, batch_id, batch_code, layout_map, now
            )

            # 12. Audit event
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="batch.create",
                entity_type="fabrication_batch",
                entity_id=str(batch_id),
                details={
                    "experiment_id": experiment_id,
                    "batch_code": batch_code,
                    "condition_count": len(condition_rows),
                },
                client_ip=client_ip,
            )

        return await self.get_fabrication_batch(batch_id)

    async def _create_preparation_groupings(
        self,
        connection: AsyncConnection,
        batch_id: int,
        batch_code: str,
        layout_map: dict[int, Any],
        now: datetime,
    ) -> None:
        """Group conditions by solution hash and create preparation entries."""
        # Collect all layers with solutions across all batch conditions
        solution_layers: list[dict[str, Any]] = []
        for bc_id, lm in layout_map.items():
            recipe = lm["recipe_snapshot"]
            device = recipe.get("device", recipe)
            layers = device.get("layers", [])
            for l_idx, layer in enumerate(layers):
                solution = layer.get("solution")
                if not solution:
                    continue
                normalized_solution = validate_solution_snapshot(solution)
                solution_hash = snapshot_hash(normalized_solution)
                solution_layers.append({
                    "batch_condition_id": bc_id,
                    "layer_ordinal": l_idx + 1,
                    "layer_role": str(layer.get("role", "")),
                    "layer_type": str(layer.get("layer_type", "")),
                    "solution": normalized_solution,
                    "solution_hash": solution_hash,
                    "condition_code": str(lm["condition_code"]),
                })

        # Group by solution hash for shared preparations
        groups: dict[str, list[dict[str, Any]]] = {}
        for sl in solution_layers:
            h = sl["solution_hash"]
            if h not in groups:
                groups[h] = []
            groups[h].append(sl)

        # Create one preparation per group
        prep_index = 0
        for sol_hash, members in groups.items():
            prep_index += 1
            prep_code = f"{batch_code}-P{prep_index:02d}"
            # Use the first member's solution as the snapshot
            first_solution = members[0]["solution"]
            prep_result = await connection.execute(
                insert(solution_preparations).values(
                    fabrication_batch_id=batch_id,
                    preparation_code=prep_code,
                    status="planned",
                    planned_solution_snapshot=first_solution,
                    planned_snapshot_schema_version=SOLUTION_SNAPSHOT_SCHEMA_VERSION,
                    planned_canonical_hash=sol_hash,
                    notes="",
                    created_at=now,
                    updated_at=now,
                )
            )
            prep_id = _inserted_id(prep_result)

            for member in members:
                await connection.execute(
                    insert(solution_preparation_uses).values(
                        solution_preparation_id=prep_id,
                        batch_condition_id=member["batch_condition_id"],
                        layer_ordinal=member["layer_ordinal"],
                        layer_role=member["layer_role"],
                        layer_type=member["layer_type"],
                        layer_snapshot_hash=member["solution_hash"],
                    )
                )

    async def _create_execution_groupings(
        self,
        connection: AsyncConnection,
        batch_id: int,
        batch_code: str,
        layout_map: dict[int, Any],
        now: datetime,
    ) -> None:
        """Materialize every process step and share only identical operations."""
        process_layers: list[dict[str, Any]] = []

        def add_operation(
            *,
            batch_condition_id: int,
            condition_code: str,
            layer_ordinal: int,
            layer_role: str,
            layer_type: str,
            layer_name: str,
            method: str,
            process: dict[str, Any],
        ) -> None:
            normalized_process = validate_process_snapshot(
                process,
                expected_method=method,
            )
            identity = {
                "method": method,
                "layer_role": layer_role,
                "layer_type": layer_type,
                "layer_name": layer_name,
                "process": normalized_process,
            }
            grouping_hash = snapshot_hash(identity)
            process_hash = snapshot_hash(normalized_process)
            process_layers.append(
                {
                    "batch_condition_id": batch_condition_id,
                    "layer_ordinal": layer_ordinal,
                    "layer_role": layer_role,
                    "layer_type": layer_type,
                    "layer_name": layer_name,
                    "method": method,
                    "process": normalized_process,
                    "process_hash": process_hash,
                    "grouping_hash": grouping_hash,
                    "condition_code": condition_code,
                }
            )

        for bc_id, lm in layout_map.items():
            recipe = lm["recipe_snapshot"]
            device = recipe.get("device", recipe)
            layers = device.get("layers", [])
            for l_idx, layer in enumerate(layers):
                process = layer.get("process")
                if not process:
                    continue
                layer_role = str(layer.get("role", ""))
                layer_type = str(layer.get("layer_type", ""))
                layer_name = str(layer.get("name", ""))
                method = str(process.get("method", ""))
                if method == "spin_coating":
                    spin_steps = process.get("spin_steps") or []
                    if spin_steps:
                        add_operation(
                            batch_condition_id=bc_id,
                            condition_code=str(lm["condition_code"]),
                            layer_ordinal=l_idx + 1,
                            layer_role=layer_role,
                            layer_type=layer_type,
                            layer_name=layer_name,
                            method="spin_coating",
                            process={"method": "spin_coating", "spin_steps": spin_steps},
                        )
                    anneal_steps = process.get("anneal_steps") or []
                    if anneal_steps:
                        add_operation(
                            batch_condition_id=bc_id,
                            condition_code=str(lm["condition_code"]),
                            layer_ordinal=l_idx + 1,
                            layer_role=layer_role,
                            layer_type=layer_type,
                            layer_name=layer_name,
                            method="annealing",
                            process={"method": "annealing", "anneal_steps": anneal_steps},
                        )
                else:
                    add_operation(
                        batch_condition_id=bc_id,
                        condition_code=str(lm["condition_code"]),
                        layer_ordinal=l_idx + 1,
                        layer_role=layer_role,
                        layer_type=layer_type,
                        layer_name=layer_name,
                        method=method,
                        process=process,
                    )

            # Perovskite spin/VCD/anneal parameters live in the condition-level
            # deposition_process rather than the perovskite layer object.
            deposition = recipe.get("deposition_process") or {}
            perovskite_index = next(
                (
                    index
                    for index, layer in enumerate(layers, start=1)
                    if layer.get("layer_type") == "perovskite"
                ),
                None,
            )
            if perovskite_index is not None:
                common = {
                    "batch_condition_id": bc_id,
                    "condition_code": str(lm["condition_code"]),
                    "layer_ordinal": perovskite_index,
                    "layer_role": "perovskite",
                    "layer_type": "perovskite",
                    "layer_name": "Perovskite",
                }
                spin_steps = deposition.get("spin_steps") or []
                if spin_steps:
                    add_operation(
                        **common,
                        method="spin_coating",
                        process={"method": "spin_coating", "spin_steps": spin_steps},
                    )
                vcd_stages = deposition.get("vcd_stages") or []
                if vcd_stages:
                    vcd_process = {"method": "vcd", "vcd_stages": vcd_stages}
                    gas_backfill_stages = (
                        deposition.get("gas_backfill_stages") or []
                    )
                    if gas_backfill_stages:
                        vcd_process["gas_backfill_stages"] = gas_backfill_stages
                    vcd_process["vcd_step_sequence"] = deposition.get(
                        "vcd_step_sequence"
                    ) or [
                        *(
                            f"vcd_stage{index}"
                            for index in range(1, len(vcd_stages) + 1)
                        ),
                        *(
                            f"gas_backfill_stage{index}"
                            for index in range(1, len(gas_backfill_stages) + 1)
                        ),
                    ]
                    add_operation(
                        **common,
                        method="vcd",
                        process=vcd_process,
                    )
                anneal_steps = deposition.get("anneal_steps") or []
                if anneal_steps:
                    add_operation(
                        **common,
                        method="annealing",
                        process={"method": "annealing", "anneal_steps": anneal_steps},
                    )

        # Group by process hash for shared executions
        groups: dict[str, list[dict[str, Any]]] = {}
        for pl in process_layers:
            h = pl["grouping_hash"]
            if h not in groups:
                groups[h] = []
            groups[h].append(pl)

        execution_index = 0
        for _grouping_hash, members in groups.items():
            execution_index += 1
            first_member = members[0]
            exec_code = f"{batch_code}-E{execution_index:02d}"
            exec_result = await connection.execute(
                insert(process_executions).values(
                    fabrication_batch_id=batch_id,
                    execution_code=exec_code,
                    method=first_member["method"],
                    layer_role=first_member["layer_role"],
                    layer_type=first_member["layer_type"],
                    layer_name=first_member["layer_name"],
                    status="planned",
                    is_shared=len(members) > 1,
                    planned_process_snapshot=first_member["process"],
                    planned_snapshot_schema_version=PROCESS_SNAPSHOT_SCHEMA_VERSION,
                    planned_canonical_hash=first_member["process_hash"],
                    notes="",
                    created_at=now,
                    updated_at=now,
                )
            )
            exec_id = _inserted_id(exec_result)

            # Add members - need to look up substrate IDs
            for member in members:
                bc_id = member["batch_condition_id"]
                # Get all substrates for this batch condition
                substrate_rows = (
                    await connection.execute(
                        select(fabrication_substrates.c.id)
                        .where(fabrication_substrates.c.batch_condition_id == bc_id)
                    )
                ).all()
                for sub_row in substrate_rows:
                    await connection.execute(
                        insert(process_execution_members).values(
                            process_execution_id=exec_id,
                            substrate_id=int(sub_row.id),
                            batch_condition_id=bc_id,
                            layer_ordinal=member["layer_ordinal"],
                            layer_snapshot_hash=member["process_hash"],
                        )
                    )

    async def list_fabrication_batches_for_experiment(
        self, experiment_id: int
    ) -> list[FabricationBatchRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(fabrication_batches)
                    .where(fabrication_batches.c.experiment_id == experiment_id)
                    .order_by(fabrication_batches.c.batch_number)
                )
            ).mappings().all()
        return [_fabrication_batch_record(row) for row in rows]

    async def list_fabrication_batches_for_actor(
        self,
        owner_user_id: int | None,
        *,
        status: BatchStatus | None = None,
        experiment_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Role-scoped fabrication-batch summaries with their experiment codes.

        Students are restricted to batches of their own experiments; instructors
        and administrators receive every batch. Optional status and experiment
        filters narrow the result set.
        """

        conditions = []
        if owner_user_id is not None:
            conditions.append(experiments.c.created_by_id == owner_user_id)
        if status is not None:
            conditions.append(fabrication_batches.c.status == status.value)
        if experiment_id is not None:
            conditions.append(fabrication_batches.c.experiment_id == experiment_id)
        statement = (
            select(
                fabrication_batches.c.id,
                fabrication_batches.c.experiment_id,
                experiments.c.experiment_code,
                fabrication_batches.c.batch_number,
                fabrication_batches.c.batch_code,
                fabrication_batches.c.status,
                fabrication_batches.c.condition_set_hash,
                fabrication_batches.c.notes,
                fabrication_batches.c.created_by_id,
                fabrication_batches.c.created_at,
                fabrication_batches.c.updated_at,
                fabrication_batches.c.started_at,
                fabrication_batches.c.completed_at,
                fabrication_batches.c.cancelled_at,
            )
            .select_from(fabrication_batches)
            .join(experiments, experiments.c.id == fabrication_batches.c.experiment_id)
            .where(*conditions)
            .order_by(fabrication_batches.c.created_at.desc(), fabrication_batches.c.id.desc())
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [
            {
                "id": int(row["id"]),
                "experiment_id": int(row["experiment_id"]),
                "experiment_code": row["experiment_code"],
                "batch_number": int(row["batch_number"]),
                "batch_code": str(row["batch_code"]),
                "status": str(row["status"]),
                "condition_set_hash": str(row["condition_set_hash"]),
                "notes": str(row["notes"]),
                "created_by_id": row["created_by_id"],
                "created_at": _as_utc(row["created_at"]).isoformat(),
                "updated_at": _as_utc(row["updated_at"]).isoformat(),
                "started_at": (
                    _optional_utc(row["started_at"]).isoformat()
                    if row["started_at"]
                    else None
                ),
                "completed_at": (
                    _optional_utc(row["completed_at"]).isoformat()
                    if row["completed_at"]
                    else None
                ),
                "cancelled_at": (
                    _optional_utc(row["cancelled_at"]).isoformat()
                    if row["cancelled_at"]
                    else None
                ),
            }
            for row in rows
        ]

    async def get_fabrication_batch(
        self, batch_id: int
    ) -> FabricationBatchRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(fabrication_batches)
                    .where(fabrication_batches.c.id == batch_id)
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown fabrication batch id: {batch_id}")
        return _fabrication_batch_record(row)

    async def get_batch_device_active_area(self, batch_id: int) -> float | None:
        """Resolve the device active area shared by a batch's conditions.

        Returns ``None`` when the batch has no conditions or its conditions
        disagree on the device layout; a total-current result file then
        cannot be converted to current density unambiguously and must be
        rejected by the parser.
        """

        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(
                        fabrication_batch_conditions.c.device_layout_snapshot
                    ).where(
                        fabrication_batch_conditions.c.fabrication_batch_id
                        == batch_id
                    )
                )
            ).mappings().all()
        areas: set[float] = set()
        for row in rows:
            snapshot = row["device_layout_snapshot"]
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)
            if not isinstance(snapshot, Mapping):
                return None
            raw_area = snapshot.get("device_active_area_cm2")
            try:
                areas.add(float(raw_area))
            except (TypeError, ValueError):
                return None
        if len(areas) != 1:
            return None
        area = areas.pop()
        return area if math.isfinite(area) and area > 0 else None

    async def get_batch_read_model(
        self, batch_id: int, *, include_results: bool = False
    ) -> dict[str, Any]:
        """Fetch every run-sheet collection inside one transaction.

        All rows come from a single database snapshot (repeatable read on
        PostgreSQL), so a concurrent split, merge, or execution update cannot
        produce a document stitching together different committed states.
        Preparation uses and execution members are fetched in bulk instead of
        one query per row.
        """

        async with self.database.begin() as connection:
            if connection.dialect.name == "postgresql":
                await connection.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
            batch_row = (
                await connection.execute(
                    select(fabrication_batches).where(
                        fabrication_batches.c.id == batch_id
                    )
                )
            ).mappings().one_or_none()
            if batch_row is None:
                raise KeyError(f"unknown fabrication batch id: {batch_id}")
            condition_rows = (
                await connection.execute(
                    select(fabrication_batch_conditions)
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(fabrication_batch_conditions.c.id)
                )
            ).mappings().all()
            substrate_rows = (
                await connection.execute(
                    select(fabrication_substrates)
                    .select_from(fabrication_substrates)
                    .join(
                        fabrication_batch_conditions,
                        fabrication_batch_conditions.c.id
                        == fabrication_substrates.c.batch_condition_id,
                    )
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(
                        fabrication_batch_conditions.c.condition_code,
                        fabrication_substrates.c.substrate_ordinal,
                    )
                )
            ).mappings().all()
            device_rows = (
                await connection.execute(
                    select(fabrication_devices)
                    .select_from(fabrication_devices)
                    .join(
                        fabrication_substrates,
                        fabrication_substrates.c.id
                        == fabrication_devices.c.substrate_id,
                    )
                    .join(
                        fabrication_batch_conditions,
                        fabrication_batch_conditions.c.id
                        == fabrication_substrates.c.batch_condition_id,
                    )
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(
                        fabrication_batch_conditions.c.condition_code,
                        fabrication_substrates.c.substrate_ordinal,
                        fabrication_devices.c.device_ordinal,
                    )
                )
            ).mappings().all()
            preparation_rows = (
                await connection.execute(
                    select(solution_preparations)
                    .where(
                        solution_preparations.c.fabrication_batch_id == batch_id
                    )
                    .order_by(solution_preparations.c.id)
                )
            ).mappings().all()
            execution_rows = (
                await connection.execute(
                    select(process_executions)
                    .where(process_executions.c.fabrication_batch_id == batch_id)
                    .order_by(process_executions.c.id)
                )
            ).mappings().all()
            deviation_rows = (
                await connection.execute(
                    select(execution_deviations)
                    .where(
                        execution_deviations.c.fabrication_batch_id == batch_id
                    )
                    .order_by(execution_deviations.c.id)
                )
            ).mappings().all()

            preparation_ids = [int(row["id"]) for row in preparation_rows]
            execution_ids = [int(row["id"]) for row in execution_rows]
            preparation_uses: dict[int, list[dict[str, Any]]] = {
                preparation_id: [] for preparation_id in preparation_ids
            }
            if preparation_ids:
                use_rows = (
                    await connection.execute(
                        select(solution_preparation_uses).where(
                            solution_preparation_uses.c.solution_preparation_id.in_(
                                preparation_ids
                            )
                        )
                    )
                ).mappings().all()
                for row in use_rows:
                    preparation_uses[int(row["solution_preparation_id"])].append(
                        dict(row)
                    )
            execution_members: dict[int, list[dict[str, Any]]] = {
                execution_id: [] for execution_id in execution_ids
            }
            if execution_ids:
                member_rows = (
                    await connection.execute(
                        select(process_execution_members).where(
                            process_execution_members.c.process_execution_id.in_(
                                execution_ids
                            )
                        )
                    )
                ).mappings().all()
                for row in member_rows:
                    execution_members[int(row["process_execution_id"])].append(
                        dict(row)
                    )

            model: dict[str, Any] = {
                "batch": _fabrication_batch_record(batch_row),
                "conditions": [
                    _frozen_batch_condition_record(row) for row in condition_rows
                ],
                "substrates": [
                    _fabrication_substrate_record(row) for row in substrate_rows
                ],
                "devices": [_fabrication_device_record(row) for row in device_rows],
                "preparations": [
                    _solution_preparation_record(row) for row in preparation_rows
                ],
                "preparation_uses": preparation_uses,
                "executions": [
                    _process_execution_record(row) for row in execution_rows
                ],
                "execution_members": execution_members,
                "deviations": [
                    _execution_deviation_record(row) for row in deviation_rows
                ],
            }
            if include_results:
                result_rows = (
                    await connection.execute(
                        select(result_files)
                        .where(result_files.c.fabrication_batch_id == batch_id)
                        .order_by(result_files.c.id)
                    )
                ).mappings().all()
                results = [_result_record(row) for row in result_rows]
                result_ids = [int(result["id"]) for result in results]
                assignments: list[dict[str, Any]] = []
                if result_ids:
                    assignment_rows = (
                        await connection.execute(
                            _result_assignment_statement(result_ids=result_ids)
                        )
                    ).mappings().all()
                    assignments = [dict(row) for row in assignment_rows]
                model["results"] = results
                model["result_assignments"] = assignments
        return model

    async def get_batch_run_sheet(self, batch_id: int) -> dict[str, Any]:
        """Aggregate the complete run-sheet read model for one batch."""

        return await self.get_batch_read_model(batch_id)

    async def update_fabrication_batch_status(
        self,
        batch_id: int,
        status: BatchStatus,
        *,
        actor_user_id: int,
        client_ip: str | None = None,
        actual_substrate_counts: Mapping[int, int] | None = None,
        shortfall_deviations: Sequence[tuple[int, str]] | None = None,
    ) -> FabricationBatchRecord:
        """Deprecated compatibility delegate for the batch-lifecycle operation.

        New code calls :func:`web.operations.batch_lifecycle.update_batch_status`,
        which adds the existence/ownership pre-checks and typed error
        translation on top of :func:`apply_batch_status_update`. This shim
        keeps the historical repository entry point **with its original
        exception contract**: KeyError for unknown ids, ValueError for
        invalid transitions, PermissionError for ownership violations.
        """
        async with self.database.begin() as connection:
            await apply_batch_status_update(
                connection,
                batch_id=batch_id,
                status=status,
                actor_user_id=actor_user_id,
                client_ip=client_ip,
                actual_substrate_counts=actual_substrate_counts,
                shortfall_deviations=shortfall_deviations,
            )
        return await self.get_fabrication_batch(batch_id)


    async def get_fabrication_substrates_for_batch(
        self, batch_id: int
    ) -> list[FabricationSubstrateRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(fabrication_substrates)
                    .select_from(fabrication_substrates)
                    .join(
                        fabrication_batch_conditions,
                        fabrication_batch_conditions.c.id
                        == fabrication_substrates.c.batch_condition_id,
                    )
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(
                        fabrication_batch_conditions.c.condition_code,
                        fabrication_substrates.c.substrate_ordinal,
                    )
                )
            ).mappings().all()
        return [_fabrication_substrate_record(row) for row in rows]

    async def get_fabrication_devices_for_batch(
        self, batch_id: int
    ) -> list[FabricationDeviceRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(fabrication_devices)
                    .select_from(fabrication_devices)
                    .join(
                        fabrication_substrates,
                        fabrication_substrates.c.id
                        == fabrication_devices.c.substrate_id,
                    )
                    .join(
                        fabrication_batch_conditions,
                        fabrication_batch_conditions.c.id
                        == fabrication_substrates.c.batch_condition_id,
                    )
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(
                        fabrication_batch_conditions.c.condition_code,
                        fabrication_substrates.c.substrate_ordinal,
                        fabrication_devices.c.device_ordinal,
                    )
                )
            ).mappings().all()
        return [_fabrication_device_record(row) for row in rows]

    async def list_fabrication_device_assignment_options(
        self, batch_id: int
    ) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    _fabrication_device_assignment_statement(batch_id)
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def get_fabrication_batch_conditions(
        self, batch_id: int
    ) -> list[FrozenBatchConditionRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(fabrication_batch_conditions)
                    .where(
                        fabrication_batch_conditions.c.fabrication_batch_id == batch_id
                    )
                    .order_by(fabrication_batch_conditions.c.id)
                )
            ).mappings().all()
        return [_frozen_batch_condition_record(row) for row in rows]

    # ------------------------------------------------------------------
    # Solution Preparations
    # ------------------------------------------------------------------
    async def create_solution_preparation(
        self,
        *,
        fabrication_batch_id: int,
        planned_solution_snapshot: dict[str, Any],
        notes: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> SolutionPreparationRecord:
        normalized_notes = notes.strip()[:2000]
        now = _utc_now()
        normalized_snapshot = validate_solution_snapshot(planned_solution_snapshot)
        plan_hash = snapshot_hash(normalized_snapshot)
        async with self.database.begin() as connection:
            await _batch_for_actor(
                connection,
                fabrication_batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            # Count existing preparations to generate code
            count = await connection.scalar(
                select(func.count())
                .select_from(solution_preparations)
                .where(solution_preparations.c.fabrication_batch_id == fabrication_batch_id)
            )
            prep_code = f"P{fabrication_batch_id}-{int(count or 0) + 1:02d}"
            result = await connection.execute(
                insert(solution_preparations).values(
                    fabrication_batch_id=fabrication_batch_id,
                    preparation_code=prep_code,
                    status="planned",
                    planned_solution_snapshot=normalized_snapshot,
                    planned_snapshot_schema_version=SOLUTION_SNAPSHOT_SCHEMA_VERSION,
                    planned_canonical_hash=plan_hash,
                    notes=normalized_notes,
                    created_at=now,
                    updated_at=now,
                )
            )
            prep_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="solution_preparation.create",
                entity_type="solution_preparation",
                entity_id=str(prep_id),
                details={"fabrication_batch_id": fabrication_batch_id},
                client_ip=client_ip,
            )
        return await self.get_solution_preparation(prep_id)

    async def get_solution_preparation(
        self, preparation_id: int
    ) -> SolutionPreparationRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(solution_preparations).where(
                        solution_preparations.c.id == preparation_id
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown solution preparation id: {preparation_id}")
        return _solution_preparation_record(row)

    async def list_solution_preparations(
        self, fabrication_batch_id: int
    ) -> list[SolutionPreparationRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(solution_preparations)
                    .where(
                        solution_preparations.c.fabrication_batch_id == fabrication_batch_id
                    )
                    .order_by(solution_preparations.c.id)
                )
            ).mappings().all()
        return [_solution_preparation_record(row) for row in rows]

    async def list_solution_preparation_uses(
        self, preparation_id: int
    ) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(solution_preparation_uses)
                    .where(
                        solution_preparation_uses.c.solution_preparation_id == preparation_id
                    )
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def split_solution_preparation(
        self,
        preparation_id: int,
        *,
        member_ids: Sequence[int],
        notes: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> SolutionPreparationRecord:
        selected_ids = sorted(set(int(value) for value in member_ids))
        if not selected_ids:
            raise ValueError("select at least one solution use to split")
        now = _utc_now()
        async with self.database.begin() as connection:
            source = (
                await connection.execute(
                    select(solution_preparations)
                    .where(solution_preparations.c.id == preparation_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if source is None:
                raise KeyError(f"unknown solution preparation id: {preparation_id}")
            batch_id = int(source["fabrication_batch_id"])
            await _batch_for_actor(
                connection,
                batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            uses = (
                await connection.execute(
                    select(solution_preparation_uses).where(
                        solution_preparation_uses.c.solution_preparation_id
                        == preparation_id
                    )
                )
            ).mappings().all()
            available_ids = {int(row["id"]) for row in uses}
            if not set(selected_ids).issubset(available_ids):
                raise ValueError("every selected solution use must belong to the source")
            if len(selected_ids) == len(available_ids):
                raise ValueError("a split must leave at least one use on the source")
            next_id = int(
                await connection.scalar(select(func.coalesce(func.max(solution_preparations.c.id), 0)))
                or 0
            ) + 1
            code = f"{str(source['preparation_code'])[:170]}-S{next_id}"
            result = await connection.execute(
                insert(solution_preparations).values(
                    fabrication_batch_id=batch_id,
                    preparation_code=code,
                    status=PreparationStatus.PLANNED.value,
                    planned_solution_snapshot=source["planned_solution_snapshot"],
                    planned_snapshot_schema_version=source[
                        "planned_snapshot_schema_version"
                    ],
                    planned_canonical_hash=source["planned_canonical_hash"],
                    notes=notes.strip()[:2000],
                    created_at=now,
                    updated_at=now,
                )
            )
            new_id = _inserted_id(result)
            await connection.execute(
                update(solution_preparation_uses)
                .where(solution_preparation_uses.c.id.in_(selected_ids))
                .values(solution_preparation_id=new_id)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="solution_preparation.split",
                entity_type="solution_preparation",
                entity_id=str(new_id),
                details={"source_id": preparation_id, "member_ids": selected_ids},
                client_ip=client_ip,
            )
        return await self.get_solution_preparation(new_id)

    async def merge_solution_preparations(
        self,
        target_id: int,
        *,
        source_id: int,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> SolutionPreparationRecord:
        if target_id == source_id:
            raise ValueError("source and target preparations must differ")
        async with self.database.begin() as connection:
            rows = (
                await connection.execute(
                    select(solution_preparations)
                    .where(solution_preparations.c.id.in_([target_id, source_id]))
                    .with_for_update()
                )
            ).mappings().all()
            by_id = {int(row["id"]): row for row in rows}
            if target_id not in by_id or source_id not in by_id:
                raise KeyError("unknown solution preparation")
            target = by_id[target_id]
            source = by_id[source_id]
            batch_id = int(target["fabrication_batch_id"])
            if int(source["fabrication_batch_id"]) != batch_id:
                raise ValueError("preparations must belong to the same batch")
            await _batch_for_actor(
                connection,
                batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            if (
                target["planned_snapshot_schema_version"]
                != source["planned_snapshot_schema_version"]
                or target["planned_canonical_hash"]
                != source["planned_canonical_hash"]
            ):
                raise ValueError("only preparations with identical planned hashes can merge")
            if target["status"] != "planned" or source["status"] != "planned":
                raise ValueError("only planned preparations can merge")
            referenced = await connection.scalar(
                select(func.count()).select_from(execution_deviations).where(
                    execution_deviations.c.solution_preparation_id == source_id
                )
            )
            if int(referenced or 0):
                raise ValueError("a preparation referenced by deviations cannot merge")
            target_keys = set(
                (
                    int(row.batch_condition_id),
                    int(row.layer_ordinal),
                )
                for row in (
                    await connection.execute(
                        select(
                            solution_preparation_uses.c.batch_condition_id,
                            solution_preparation_uses.c.layer_ordinal,
                        ).where(
                            solution_preparation_uses.c.solution_preparation_id
                            == target_id
                        )
                    )
                ).all()
            )
            source_keys = set(
                (
                    int(row.batch_condition_id),
                    int(row.layer_ordinal),
                )
                for row in (
                    await connection.execute(
                        select(
                            solution_preparation_uses.c.batch_condition_id,
                            solution_preparation_uses.c.layer_ordinal,
                        ).where(
                            solution_preparation_uses.c.solution_preparation_id
                            == source_id
                        )
                    )
                ).all()
            )
            if target_keys & source_keys:
                raise ValueError("preparation memberships overlap")
            await connection.execute(
                update(solution_preparation_uses)
                .where(solution_preparation_uses.c.solution_preparation_id == source_id)
                .values(solution_preparation_id=target_id)
            )
            await connection.execute(
                delete(solution_preparations).where(solution_preparations.c.id == source_id)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="solution_preparation.merge",
                entity_type="solution_preparation",
                entity_id=str(target_id),
                details={"source_id": source_id},
                client_ip=client_ip,
            )
        return await self.get_solution_preparation(target_id)

    async def update_solution_preparation(
        self,
        preparation_id: int,
        *,
        actual_solution_snapshot: dict[str, Any] | None = None,
        actual_matches_planned: bool = False,
        status: PreparationStatus | None = None,
        notes: str | None = None,
        fabrication_batch_id: int | None = None,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> SolutionPreparationRecord:
        if actual_solution_snapshot is not None and actual_matches_planned:
            raise ValueError(
                "provide an actual solution snapshot or copy the plan, not both"
            )
        now = _utc_now()
        values: dict[str, Any] = {"updated_at": now}
        if status is not None:
            values["status"] = status.value
            if status == PreparationStatus.CONSUMED:
                values["completed_at"] = now
        if notes is not None:
            values["notes"] = notes.strip()[:2000]
        async with self.database.begin() as connection:
            existing = (
                await connection.execute(
                    select(solution_preparations)
                    .where(solution_preparations.c.id == preparation_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if existing is None:
                raise KeyError(f"unknown solution preparation id: {preparation_id}")
            normalized_actual: dict[str, Any] | None = None
            actual_recording_mode: str | None = None
            if actual_matches_planned:
                normalized_actual = validate_solution_snapshot(
                    existing["planned_solution_snapshot"]
                )
                actual_recording_mode = "copied_from_plan"
            elif actual_solution_snapshot is not None:
                normalized_actual = validate_solution_snapshot(
                    actual_solution_snapshot
                )
                actual_recording_mode = "entered"
            if normalized_actual is not None:
                values.update(
                    actual_solution_snapshot=normalized_actual,
                    actual_snapshot_schema_version=SOLUTION_SNAPSHOT_SCHEMA_VERSION,
                    actual_canonical_hash=snapshot_hash(normalized_actual),
                    actual_recording_mode=actual_recording_mode,
                    prepared_by_id=actor_user_id,
                    prepared_at=now,
                )
            actual_batch_id = int(existing["fabrication_batch_id"])
            if (
                fabrication_batch_id is not None
                and actual_batch_id != fabrication_batch_id
            ):
                raise KeyError(f"unknown solution preparation id: {preparation_id}")
            await _batch_for_actor(
                connection,
                actual_batch_id,
                actor_user_id,
                allowed_statuses={
                    BatchStatus.DRAFT,
                    BatchStatus.READY,
                    BatchStatus.IN_PROGRESS,
                },
            )
            current_status = PreparationStatus(existing["status"])
            if status is not None and status != current_status:
                allowed = _preparation_status_transitions(current_status)
                if status not in allowed:
                    raise ValueError(
                        "preparation status cannot change from "
                        f"{current_status.value} to {status.value}"
                    )
            if (
                status == PreparationStatus.CONSUMED
                and normalized_actual is None
                and existing["actual_solution_snapshot"] is None
            ):
                raise ValueError(
                    "a consumed preparation requires an actual solution snapshot"
                )
            if current_status in {
                PreparationStatus.CONSUMED,
                PreparationStatus.DISCARDED,
            } and (
                status is not None
                or normalized_actual is not None
                or notes is not None
            ):
                raise ValueError("terminal solution preparations are immutable")
            result = await connection.execute(
                update(solution_preparations)
                .where(solution_preparations.c.id == preparation_id)
                .values(**values)
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown solution preparation id: {preparation_id}")
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="solution_preparation.update",
                entity_type="solution_preparation",
                entity_id=str(preparation_id),
                details={k: str(v) for k, v in values.items() if k != "updated_at"},
                client_ip=client_ip,
            )
        return await self.get_solution_preparation(preparation_id)

    # ------------------------------------------------------------------
    # Process Executions
    # ------------------------------------------------------------------
    async def create_process_execution(
        self,
        *,
        fabrication_batch_id: int,
        method: str,
        layer_role: str,
        layer_type: str,
        layer_name: str,
        planned_process_snapshot: dict[str, Any],
        is_shared: bool = False,
        notes: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> ProcessExecutionRecord:
        normalized_notes = notes.strip()[:2000]
        now = _utc_now()
        normalized_snapshot = validate_process_snapshot(
            planned_process_snapshot,
            expected_method=method,
        )
        plan_hash = snapshot_hash(normalized_snapshot)
        async with self.database.begin() as connection:
            await _batch_for_actor(
                connection,
                fabrication_batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            count = await connection.scalar(
                select(func.count())
                .select_from(process_executions)
                .where(process_executions.c.fabrication_batch_id == fabrication_batch_id)
            )
            exec_code = f"E{fabrication_batch_id}-{int(count or 0) + 1:02d}"
            result = await connection.execute(
                insert(process_executions).values(
                    fabrication_batch_id=fabrication_batch_id,
                    execution_code=exec_code,
                    method=method,
                    layer_role=layer_role,
                    layer_type=layer_type,
                    layer_name=layer_name,
                    status="planned",
                    is_shared=is_shared,
                    planned_process_snapshot=normalized_snapshot,
                    planned_snapshot_schema_version=PROCESS_SNAPSHOT_SCHEMA_VERSION,
                    planned_canonical_hash=plan_hash,
                    notes=normalized_notes,
                    created_at=now,
                    updated_at=now,
                )
            )
            exec_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="process_execution.create",
                entity_type="process_execution",
                entity_id=str(exec_id),
                details={"fabrication_batch_id": fabrication_batch_id},
                client_ip=client_ip,
            )
        return await self.get_process_execution(exec_id)

    async def get_process_execution(
        self, execution_id: int
    ) -> ProcessExecutionRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(process_executions).where(
                        process_executions.c.id == execution_id
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown process execution id: {execution_id}")
        return _process_execution_record(row)

    async def list_process_executions(
        self, fabrication_batch_id: int
    ) -> list[ProcessExecutionRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(process_executions)
                    .where(process_executions.c.fabrication_batch_id == fabrication_batch_id)
                    .order_by(process_executions.c.id)
                )
            ).mappings().all()
        return [_process_execution_record(row) for row in rows]

    async def list_process_execution_members(
        self, execution_id: int
    ) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(process_execution_members)
                    .where(
                        process_execution_members.c.process_execution_id == execution_id
                    )
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def split_process_execution(
        self,
        execution_id: int,
        *,
        member_ids: Sequence[int],
        notes: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> ProcessExecutionRecord:
        selected_ids = sorted(set(int(value) for value in member_ids))
        if not selected_ids:
            raise ValueError("select at least one execution member to split")
        now = _utc_now()
        async with self.database.begin() as connection:
            source = (
                await connection.execute(
                    select(process_executions)
                    .where(process_executions.c.id == execution_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if source is None:
                raise KeyError(f"unknown process execution id: {execution_id}")
            batch_id = int(source["fabrication_batch_id"])
            await _batch_for_actor(
                connection,
                batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            members = (
                await connection.execute(
                    select(process_execution_members).where(
                        process_execution_members.c.process_execution_id == execution_id
                    )
                )
            ).mappings().all()
            available_ids = {int(row["id"]) for row in members}
            if not set(selected_ids).issubset(available_ids):
                raise ValueError("every selected member must belong to the source")
            if len(selected_ids) == len(available_ids):
                raise ValueError("a split must leave at least one member on the source")
            selected_conditions = {
                int(row["batch_condition_id"])
                for row in members
                if int(row["id"]) in selected_ids
            }
            remaining_conditions = {
                int(row["batch_condition_id"])
                for row in members
                if int(row["id"]) not in selected_ids
            }
            next_id = int(
                await connection.scalar(select(func.coalesce(func.max(process_executions.c.id), 0)))
                or 0
            ) + 1
            code = f"{str(source['execution_code'])[:170]}-S{next_id}"
            result = await connection.execute(
                insert(process_executions).values(
                    fabrication_batch_id=batch_id,
                    execution_code=code,
                    method=source["method"],
                    layer_role=source["layer_role"],
                    layer_type=source["layer_type"],
                    layer_name=source["layer_name"],
                    status=ExecutionStatus.PLANNED.value,
                    is_shared=len(selected_conditions) > 1,
                    planned_process_snapshot=source["planned_process_snapshot"],
                    planned_snapshot_schema_version=source[
                        "planned_snapshot_schema_version"
                    ],
                    planned_canonical_hash=source["planned_canonical_hash"],
                    notes=notes.strip()[:2000],
                    created_at=now,
                    updated_at=now,
                )
            )
            new_id = _inserted_id(result)
            await connection.execute(
                update(process_execution_members)
                .where(process_execution_members.c.id.in_(selected_ids))
                .values(process_execution_id=new_id)
            )
            await connection.execute(
                update(process_executions)
                .where(process_executions.c.id == execution_id)
                .values(is_shared=len(remaining_conditions) > 1, updated_at=now)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="process_execution.split",
                entity_type="process_execution",
                entity_id=str(new_id),
                details={"source_id": execution_id, "member_ids": selected_ids},
                client_ip=client_ip,
            )
        return await self.get_process_execution(new_id)

    async def merge_process_executions(
        self,
        target_id: int,
        *,
        source_id: int,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> ProcessExecutionRecord:
        if target_id == source_id:
            raise ValueError("source and target executions must differ")
        now = _utc_now()
        async with self.database.begin() as connection:
            rows = (
                await connection.execute(
                    select(process_executions)
                    .where(process_executions.c.id.in_([target_id, source_id]))
                    .with_for_update()
                )
            ).mappings().all()
            by_id = {int(row["id"]): row for row in rows}
            if target_id not in by_id or source_id not in by_id:
                raise KeyError("unknown process execution")
            target = by_id[target_id]
            source = by_id[source_id]
            batch_id = int(target["fabrication_batch_id"])
            if int(source["fabrication_batch_id"]) != batch_id:
                raise ValueError("executions must belong to the same batch")
            await _batch_for_actor(
                connection,
                batch_id,
                actor_user_id,
                allowed_statuses={BatchStatus.DRAFT},
            )
            process_identity_fields = (
                "method",
                "layer_role",
                "layer_type",
                "layer_name",
                "planned_snapshot_schema_version",
                "planned_canonical_hash",
            )
            if any(target[field] != source[field] for field in process_identity_fields):
                raise ValueError(
                    "only executions with identical planned snapshots and layer "
                    "context can merge"
                )
            if target["status"] != "planned" or source["status"] != "planned":
                raise ValueError("only planned executions can merge")
            referenced = await connection.scalar(
                select(func.count()).select_from(execution_deviations).where(
                    execution_deviations.c.process_execution_id == source_id
                )
            )
            if int(referenced or 0):
                raise ValueError("an execution referenced by deviations cannot merge")
            target_keys = set(
                (int(row.substrate_id), int(row.layer_ordinal))
                for row in (
                    await connection.execute(
                        select(
                            process_execution_members.c.substrate_id,
                            process_execution_members.c.layer_ordinal,
                        ).where(
                            process_execution_members.c.process_execution_id == target_id
                        )
                    )
                ).all()
            )
            source_rows = (
                await connection.execute(
                    select(
                        process_execution_members.c.substrate_id,
                        process_execution_members.c.layer_ordinal,
                        process_execution_members.c.batch_condition_id,
                    ).where(
                        process_execution_members.c.process_execution_id == source_id
                    )
                )
            ).all()
            source_keys = {
                (int(row.substrate_id), int(row.layer_ordinal)) for row in source_rows
            }
            if target_keys & source_keys:
                raise ValueError("execution memberships overlap")
            await connection.execute(
                update(process_execution_members)
                .where(process_execution_members.c.process_execution_id == source_id)
                .values(process_execution_id=target_id)
            )
            condition_count = await connection.scalar(
                select(func.count(func.distinct(process_execution_members.c.batch_condition_id)))
                .where(process_execution_members.c.process_execution_id == target_id)
            )
            await connection.execute(
                update(process_executions)
                .where(process_executions.c.id == target_id)
                .values(is_shared=int(condition_count or 0) > 1, updated_at=now)
            )
            await connection.execute(
                delete(process_executions).where(process_executions.c.id == source_id)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="process_execution.merge",
                entity_type="process_execution",
                entity_id=str(target_id),
                details={"source_id": source_id},
                client_ip=client_ip,
            )
        return await self.get_process_execution(target_id)

    async def update_process_execution(
        self,
        execution_id: int,
        *,
        actual_process_snapshot: dict[str, Any] | None = None,
        actual_matches_planned: bool = False,
        status: ExecutionStatus | None = None,
        equipment_identifier: str | None = None,
        notes: str | None = None,
        fabrication_batch_id: int | None = None,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> ProcessExecutionRecord:
        if actual_process_snapshot is not None and actual_matches_planned:
            raise ValueError(
                "provide an actual process snapshot or copy the plan, not both"
            )
        now = _utc_now()
        values: dict[str, Any] = {"updated_at": now}
        if status is not None:
            values["status"] = status.value
            if status == ExecutionStatus.RUNNING:
                values["started_at"] = now
            elif status == ExecutionStatus.COMPLETED:
                values["completed_at"] = now
        if equipment_identifier is not None:
            values["equipment_identifier"] = equipment_identifier.strip()[:120]
        if notes is not None:
            values["notes"] = notes.strip()[:2000]
        async with self.database.begin() as connection:
            existing = (
                await connection.execute(
                    select(process_executions)
                    .where(process_executions.c.id == execution_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if existing is None:
                raise KeyError(f"unknown process execution id: {execution_id}")
            normalized_actual: dict[str, Any] | None = None
            actual_recording_mode: str | None = None
            if actual_matches_planned:
                normalized_actual = validate_process_snapshot(
                    existing["planned_process_snapshot"],
                    expected_method=str(existing["method"]),
                )
                actual_recording_mode = "copied_from_plan"
            elif actual_process_snapshot is not None:
                normalized_actual = validate_process_snapshot(
                    actual_process_snapshot,
                    expected_method=str(existing["method"]),
                )
                actual_recording_mode = "entered"
            if normalized_actual is not None:
                values.update(
                    actual_process_snapshot=normalized_actual,
                    actual_snapshot_schema_version=PROCESS_SNAPSHOT_SCHEMA_VERSION,
                    actual_canonical_hash=snapshot_hash(normalized_actual),
                    actual_recording_mode=actual_recording_mode,
                    executed_by_id=actor_user_id,
                )
            actual_batch_id = int(existing["fabrication_batch_id"])
            if (
                fabrication_batch_id is not None
                and actual_batch_id != fabrication_batch_id
            ):
                raise KeyError(f"unknown process execution id: {execution_id}")
            await _batch_for_actor(
                connection,
                actual_batch_id,
                actor_user_id,
                allowed_statuses={
                    BatchStatus.DRAFT,
                    BatchStatus.READY,
                    BatchStatus.IN_PROGRESS,
                },
            )
            current_status = ExecutionStatus(existing["status"])
            if status is not None and status != current_status:
                allowed = _execution_status_transitions(current_status)
                if status not in allowed:
                    raise ValueError(
                        "execution status cannot change from "
                        f"{current_status.value} to {status.value}"
                    )
            if (
                status == ExecutionStatus.COMPLETED
                and normalized_actual is None
                and existing["actual_process_snapshot"] is None
            ):
                raise ValueError(
                    "a completed execution requires an actual process snapshot"
                )
            if current_status in {
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            } and (
                status is not None
                or normalized_actual is not None
                or equipment_identifier is not None
                or notes is not None
            ):
                raise ValueError("terminal process executions are immutable")
            result = await connection.execute(
                update(process_executions)
                .where(process_executions.c.id == execution_id)
                .values(**values)
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown process execution id: {execution_id}")
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="process_execution.update",
                entity_type="process_execution",
                entity_id=str(execution_id),
                details={k: str(v) for k, v in values.items() if k != "updated_at"},
                client_ip=client_ip,
            )
        return await self.get_process_execution(execution_id)

    async def record_batch_as_planned(
        self,
        batch_id: int,
        *,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, int]:
        """Mark every unrecorded preparation/execution as matching the plan.

        Bulk convenience for the run sheet: each untouched row gets its actual
        snapshot copied from the frozen plan (recording mode
        ``copied_from_plan``), exactly as if the student had picked "Recorded
        as planned" per row. Already-recorded and terminal rows are left
        untouched, so repeated calls are safe.
        """
        now = _utc_now()
        counts = {"preparations": 0, "executions": 0}
        async with self.database.begin() as connection:
            await _batch_for_actor(
                connection,
                batch_id,
                actor_user_id,
                allowed_statuses={
                    BatchStatus.DRAFT,
                    BatchStatus.READY,
                    BatchStatus.IN_PROGRESS,
                },
            )
            pending_preparations = (
                await connection.execute(
                    select(
                        solution_preparations.c.id,
                        solution_preparations.c.planned_solution_snapshot,
                    )
                    .where(
                        solution_preparations.c.fabrication_batch_id == batch_id,
                        solution_preparations.c.actual_recording_mode.is_(None),
                        solution_preparations.c.status.in_(
                            [
                                PreparationStatus.PLANNED.value,
                                PreparationStatus.PREPARING.value,
                                PreparationStatus.READY.value,
                            ]
                        ),
                    )
                    .with_for_update()
                )
            ).mappings().all()
            for row in pending_preparations:
                normalized = validate_solution_snapshot(
                    row["planned_solution_snapshot"]
                )
                values: dict[str, Any] = dict(
                    actual_solution_snapshot=normalized,
                    actual_snapshot_schema_version=SOLUTION_SNAPSHOT_SCHEMA_VERSION,
                    actual_canonical_hash=snapshot_hash(normalized),
                    actual_recording_mode="copied_from_plan",
                    prepared_by_id=actor_user_id,
                    prepared_at=now,
                    updated_at=now,
                )
                await connection.execute(
                    update(solution_preparations)
                    .where(solution_preparations.c.id == row["id"])
                    .values(**values)
                )
                await _add_audit_event(
                    connection,
                    actor_user_id=actor_user_id,
                    action="solution_preparation.update",
                    entity_type="solution_preparation",
                    entity_id=str(row["id"]),
                    details={"actual_recording_mode": "copied_from_plan"},
                    client_ip=client_ip,
                )
                counts["preparations"] += 1
            pending_executions = (
                await connection.execute(
                    select(
                        process_executions.c.id,
                        process_executions.c.planned_process_snapshot,
                        process_executions.c.method,
                    )
                    .where(
                        process_executions.c.fabrication_batch_id == batch_id,
                        process_executions.c.actual_recording_mode.is_(None),
                        process_executions.c.status.in_(
                            [
                                ExecutionStatus.PLANNED.value,
                                ExecutionStatus.READY.value,
                                ExecutionStatus.RUNNING.value,
                            ]
                        ),
                    )
                    .with_for_update()
                )
            ).mappings().all()
            for row in pending_executions:
                normalized = validate_process_snapshot(
                    row["planned_process_snapshot"],
                    expected_method=str(row["method"]),
                )
                values = dict(
                    actual_process_snapshot=normalized,
                    actual_snapshot_schema_version=PROCESS_SNAPSHOT_SCHEMA_VERSION,
                    actual_canonical_hash=snapshot_hash(normalized),
                    actual_recording_mode="copied_from_plan",
                    executed_by_id=actor_user_id,
                    updated_at=now,
                )
                await connection.execute(
                    update(process_executions)
                    .where(process_executions.c.id == row["id"])
                    .values(**values)
                )
                await _add_audit_event(
                    connection,
                    actor_user_id=actor_user_id,
                    action="process_execution.update",
                    entity_type="process_execution",
                    entity_id=str(row["id"]),
                    details={"actual_recording_mode": "copied_from_plan"},
                    client_ip=client_ip,
                )
                counts["executions"] += 1
            if counts["preparations"] or counts["executions"]:
                await _add_audit_event(
                    connection,
                    actor_user_id=actor_user_id,
                    action="fabrication_batch.record_as_planned",
                    entity_type="fabrication_batch",
                    entity_id=str(batch_id),
                    details={k: str(v) for k, v in counts.items()},
                    client_ip=client_ip,
                )
        return counts

    # ------------------------------------------------------------------
    # Execution Deviations (append-only)
    # ------------------------------------------------------------------
    async def create_deviation(
        self,
        *,
        fabrication_batch_id: int,
        category: str,
        severity: str,
        description: str,
        planned_value: dict[str, Any] | None = None,
        actual_value: dict[str, Any] | None = None,
        supersedes_deviation_id: int | None = None,
        solution_preparation_id: int | None = None,
        process_execution_id: int | None = None,
        substrate_id: int | None = None,
        device_id: int | None = None,
        condition_id: int | None = None,
        deviation_type: str = "general",
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> ExecutionDeviationRecord:
        """Create a deviation, optionally targeting a whole batch condition."""
        normalized_description = description.strip()
        if not normalized_description:
            raise ValueError("deviation description must not be blank")
        allowed_categories = ("process", "material", "equipment", "substrate", "device", "operator", "other")
        if category not in allowed_categories:
            raise ValueError(f"category must be one of: {', '.join(allowed_categories)}")
        allowed_severities = ("info", "warning", "error", "critical")
        if severity not in allowed_severities:
            raise ValueError(f"severity must be one of: {', '.join(allowed_severities)}")
        if deviation_type not in DEVIATION_TYPES:
            raise ValueError(
                f"deviation type must be one of: {', '.join(DEVIATION_TYPES)}"
            )
        now = _utc_now()
        async with self.database.begin() as connection:
            await _batch_for_actor(
                connection,
                fabrication_batch_id,
                actor_user_id,
                # COMPLETED is allowed so a measurement_shortfall can be
                # declared when a result CSV covers fewer substrates than
                # were actually made (assignment happens post-completion).
                allowed_statuses={
                    BatchStatus.DRAFT,
                    BatchStatus.READY,
                    BatchStatus.IN_PROGRESS,
                    BatchStatus.COMPLETED,
                },
            )
            await _validate_deviation_links(
                connection,
                fabrication_batch_id=fabrication_batch_id,
                supersedes_deviation_id=supersedes_deviation_id,
                solution_preparation_id=solution_preparation_id,
                process_execution_id=process_execution_id,
                substrate_id=substrate_id,
                device_id=device_id,
                condition_id=condition_id,
            )
            result = await connection.execute(
                insert(execution_deviations).values(
                    fabrication_batch_id=fabrication_batch_id,
                    category=category,
                    severity=severity,
                    deviation_type=deviation_type,
                    description=normalized_description,
                    planned_value=planned_value,
                    actual_value=actual_value,
                    recorded_by_id=actor_user_id,
                    recorded_at=now,
                    supersedes_deviation_id=supersedes_deviation_id,
                    solution_preparation_id=solution_preparation_id,
                    process_execution_id=process_execution_id,
                    substrate_id=substrate_id,
                    device_id=device_id,
                    condition_id=condition_id,
                    created_at=now,
                )
            )
            deviation_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="deviation.create",
                entity_type="execution_deviation",
                entity_id=str(deviation_id),
                details={
                    "fabrication_batch_id": fabrication_batch_id,
                    "category": category,
                    "severity": severity,
                },
                client_ip=client_ip,
            )
        return await self.get_deviation(deviation_id)

    async def get_deviation(
        self, deviation_id: int
    ) -> ExecutionDeviationRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(execution_deviations).where(
                        execution_deviations.c.id == deviation_id
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown deviation id: {deviation_id}")
        return _execution_deviation_record(row)

    async def list_deviations(
        self, fabrication_batch_id: int
    ) -> list[ExecutionDeviationRecord]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(execution_deviations)
                    .where(
                        execution_deviations.c.fabrication_batch_id == fabrication_batch_id
                    )
                    .order_by(execution_deviations.c.id)
                )
            ).mappings().all()
        return [_execution_deviation_record(row) for row in rows]


async def apply_batch_status_update(
    connection: AsyncConnection,
    *,
    batch_id: int,
    status: BatchStatus,
    actor_user_id: int,
    client_ip: str | None = None,
    actual_substrate_counts: Mapping[int, int] | None = None,
    shortfall_deviations: Sequence[tuple[int, str]] | None = None,
) -> None:
    """Apply one fabrication-batch status transition inside the caller's
    transaction.

    Connection-level data function of the batch-lifecycle operation
    (see :mod:`web.operations.batch_lifecycle`, which owns the
    transaction, existence pre-checks, and error mapping). Locks the
    batch row, enforces the transition map and ownership, records
    actual substrate counts and shortfall deviations for completion,
    validates completion readiness, and writes the audit record.
    Raises KeyError/ValueError/PermissionError for referenced-record,
    validation, and authorization failures; the operation maps them to
    typed business errors.
    """
    now = _utc_now()
    row = (
        await connection.execute(
            select(fabrication_batches)
            .where(fabrication_batches.c.id == batch_id)
            .with_for_update()
        )
    ).mappings().one_or_none()
    if row is None:
        raise KeyError(f"unknown fabrication batch id: {batch_id}")

    current = BatchStatus(row["status"])
    allowed = _batch_status_transitions(current)
    if status not in allowed:
        raise ValueError(
            f"batch status cannot change from {current.value} to {status.value}"
        )

    # Check ownership for students
    actor_role = await _actor_role(connection, actor_user_id)
    if actor_role == UserRole.STUDENT:
        experiment_owner = await connection.scalar(
            select(experiments.c.created_by_id)
            .where(experiments.c.id == row["experiment_id"])
        )
        if experiment_owner != actor_user_id:
            raise PermissionError(
                "students can update batches only for their own plans"
            )
        if status == BatchStatus.CANCELLED:
            raise PermissionError(
                "only instructors and administrators can cancel a batch"
            )

    if status == BatchStatus.READY:
        await _validate_batch_ready(connection, batch_id)
    elif status == BatchStatus.COMPLETED:
        completion_summary = await _record_actual_substrate_counts(
            connection,
            batch_id,
            actual_substrate_counts,
            batch_code=str(row["batch_code"]),
            now=now,
            shortfall_deviations=shortfall_deviations,
            actor_user_id=actor_user_id,
        )
        await _validate_batch_complete(connection, batch_id)

    timestamps: dict[str, datetime] = {}
    if status == BatchStatus.IN_PROGRESS:
        timestamps["started_at"] = now
    elif status == BatchStatus.COMPLETED:
        timestamps["completed_at"] = now
    elif status == BatchStatus.CANCELLED:
        timestamps["cancelled_at"] = now

    values: dict[str, Any] = {
        "status": status.value,
        "updated_at": now,
        **timestamps,
    }

    await connection.execute(
        update(fabrication_batches)
        .where(fabrication_batches.c.id == batch_id)
        .values(**values)
    )

    audit_details: dict[str, Any] = {
        "from": current.value,
        "to": status.value,
    }
    if status == BatchStatus.COMPLETED and "completion_summary" in locals():
        audit_details.update(completion_summary)
    await _add_audit_event(
        connection,
        actor_user_id=actor_user_id,
        action="batch.status_change",
        entity_type="fabrication_batch",
        entity_id=str(batch_id),
        details=audit_details,
        client_ip=client_ip,
    )


