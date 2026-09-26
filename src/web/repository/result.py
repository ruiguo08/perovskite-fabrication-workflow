"""Result-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncConnection
from perovskite_bo import ExperimentStatus
from copy import deepcopy
from sqlalchemy import delete, func, insert, select, update

from ..database import (
    device_representative_scans,
    device_scan_stats,
    execution_deviations,
    experiments,
    fabrication_batch_conditions,
    fabrication_batches,
    fabrication_devices,
    fabrication_substrates,
    result_device_assignments,
    result_files,
)
from ..jv_parser import (
    LASER_MARK_PATTERN,
    _flat_metrics_from_analysis,
    _has_higher_pce,
    _normalize_legacy_analysis,
    normalize_laser_mark,
)
from .helpers import (
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _locked_experiment,
    _normalize_metrics,
    _transition_experiment,
    _utc_now,
)
from .records import BatchStatus

import hashlib

async def _has_qualifying_condition_deviation(
    connection: AsyncConnection,
    condition_id: int,
    deviation_type: str,
) -> bool:
    """Whether a current deviation of the exact type targets the condition.

    A deviation qualifies only when no later deviation supersedes it; a
    general/process/material/operator deviation never satisfies a shortfall
    gate because the type must match exactly.
    """

    superseded = (
        select(execution_deviations.c.supersedes_deviation_id).where(
            execution_deviations.c.supersedes_deviation_id.isnot(None)
        )
    ).scalar_subquery()
    qualifying = await connection.scalar(
        select(func.count())
        .select_from(execution_deviations)
        .where(
            execution_deviations.c.condition_id == condition_id,
            execution_deviations.c.deviation_type == deviation_type,
            execution_deviations.c.id.not_in(superseded),
        )
    )
    return int(qualifying or 0) > 0

_SCAN_DIRECTIONS = ("forward", "reverse")

def _device_scan_entries(
    file_analyses: list[tuple[Mapping[str, Any], Any, int, str]],
    *,
    fabrication_device_id: int,
) -> list[dict[str, Any]]:
    """Every scan trace assigned to one physical device, in file order.

    ``file_analyses`` are ``(analysis, uploaded_at, result_file_id, filename)``
    tuples of the result files whose assignments point at the device (at most
    one analysis device per file matches, by the assignment uniqueness
    constraint). Trace order is the stored order; file order is by
    (uploaded_at, file id), the deterministic tie-break for the
    representative rule. Invalid scans are included (flagged) so the UI can
    show every measurement; only valid scans carry metrics and can become a
    direction's representative.
    """

    entries: list[dict[str, Any]] = []
    for analysis, uploaded_at, result_file_id, filename in file_analyses:
        for device in (analysis or {}).get("devices") or []:
            if not isinstance(device, Mapping):
                continue
            if device.get("fabrication_device_id") != fabrication_device_id:
                continue
            for trace in device.get("traces") or []:
                if not isinstance(trace, Mapping):
                    continue
                direction = str(trace.get("direction") or "")
                if direction not in _SCAN_DIRECTIONS:
                    continue
                metrics = trace.get("metrics")
                entries.append(
                    {
                        "result_file_id": int(result_file_id),
                        "filename": str(filename),
                        "uploaded_at": uploaded_at,
                        "trace_id": str(trace.get("trace_id") or ""),
                        "direction": direction,
                        "valid": bool(trace.get("valid")),
                        "measured_at": trace.get("measured_at"),
                        "metrics": dict(metrics) if isinstance(metrics, Mapping) else None,
                        "metric_source": trace.get("metric_source"),
                        "error": trace.get("error"),
                        "points": trace.get("points") or [],
                    }
                )
    return entries

def _best_scan_entry(
    entries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Highest-PCE valid scan of one direction (first wins ties)."""

    best: dict[str, Any] | None = None
    for entry in entries:
        if not entry["valid"] or not entry["metrics"]:
            continue
        if best is None or _has_higher_pce(entry["metrics"], best["metrics"]):
            best = entry
    return best

def _parse_trace_measured_at(value: Any) -> Any:
    """Parse a trace's ISO measured_at string for the stats cache column."""

    if not isinstance(value, str) or not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None

async def _refresh_device_scan_stats(
    connection: AsyncConnection,
    fabrication_device_ids: set[int] | list[int],
) -> None:
    """Rebuild the per-device directional scan cache from stored traces.

    The cache is fully derived data: for every scan assigned to the physical
    device (across all uploads), the highest-PCE valid scan per direction is
    the representative unless the user picked one explicitly; a selection
    whose trace is no longer assigned to the device is dropped. Rewritten in
    the caller's transaction so cache and assignments never diverge.
    """

    now = _utc_now()
    for device_id in sorted(set(fabrication_device_ids)):
        file_rows = (
            await connection.execute(
                select(
                    result_device_assignments.c.result_file_id,
                    result_files.c.filename,
                    result_files.c.analysis,
                    result_files.c.created_at,
                )
                .select_from(result_device_assignments)
                .join(
                    result_files,
                    result_files.c.id == result_device_assignments.c.result_file_id,
                )
                .where(result_device_assignments.c.fabrication_device_id == device_id)
                .order_by(result_files.c.created_at, result_files.c.id)
            )
        ).mappings().all()
        file_analyses = [
            (
                row["analysis"],
                _as_utc(row["created_at"]),
                int(row["result_file_id"]),
                str(row["filename"]),
            )
            for row in file_rows
        ]
        entries = _device_scan_entries(file_analyses, fabrication_device_id=device_id)
        entries_by_direction: dict[str, list[dict[str, Any]]] = {
            direction: [] for direction in _SCAN_DIRECTIONS
        }
        for entry in entries:
            entries_by_direction[entry["direction"]].append(entry)
        selection_rows = (
            await connection.execute(
                select(device_representative_scans).where(
                    device_representative_scans.c.fabrication_device_id == device_id
                )
            )
        ).mappings().all()
        selections = {
            str(row["direction"]): row for row in selection_rows
        }
        for direction in _SCAN_DIRECTIONS:
            # The cache counts and ranks valid scans only; invalid scans
            # remain visible through the scan-history endpoint.
            pool = [
                entry
                for entry in entries_by_direction[direction]
                if entry["valid"] and entry["metrics"]
            ]
            representative = _best_scan_entry(pool)
            selection = selections.get(direction)
            if selection is not None:
                match = next(
                    (
                        entry
                        for entry in pool
                        if entry["result_file_id"] == int(selection["result_file_id"])
                        and entry["trace_id"] == str(selection["trace_id"])
                    ),
                    None,
                )
                if match is not None:
                    representative = match
                else:
                    # The selected scan is no longer assigned to this device
                    # (the file was reassigned); the choice is stale.
                    await connection.execute(
                        delete(device_representative_scans).where(
                            device_representative_scans.c.id == int(selection["id"])
                        )
                    )
            await connection.execute(
                delete(device_scan_stats).where(
                    device_scan_stats.c.fabrication_device_id == device_id,
                    device_scan_stats.c.direction == direction,
                )
            )
            if representative is None:
                continue
            await connection.execute(
                insert(device_scan_stats).values(
                    fabrication_device_id=device_id,
                    direction=direction,
                    best_result_file_id=representative["result_file_id"],
                    best_trace_id=representative["trace_id"],
                    best_measured_at=_parse_trace_measured_at(
                        representative["measured_at"]
                    ),
                    best_metrics=dict(representative["metrics"]),
                    scan_count=len(pool),
                    updated_at=now,
                )
            )

def _analysis_schema_version(analysis: Mapping[str, Any]) -> int:
    value = analysis.get("schema_version")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("result analysis schema_version must be a positive integer")
    return value

def _result_record(row: Mapping[str, Any]) -> dict[str, Any]:
    analysis = _normalize_legacy_analysis(dict(row["analysis"]))
    return {
        "id": int(row["id"]),
        "experiment_id": int(row["experiment_id"]),
        "fabrication_batch_id": int(row["fabrication_batch_id"]),
        "filename": str(row["filename"]),
        "content_type": str(row["content_type"]),
        "size_bytes": int(row["size_bytes"]),
        "sha256": str(row["sha256"]),
        "group_assignment": str(row["group_assignment"]),
        "metrics": dict(row["metrics"]),
        "analysis": analysis,
        "analysis_schema_version": _analysis_schema_version(analysis),
        "created_at": _as_utc(row["created_at"]).isoformat(),
        "created_by_id": (
            int(row["created_by_id"]) if row["created_by_id"] is not None else None
        ),
    }

def _result_summary_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Lightweight list-summary mapper that never materializes the analysis JSON."""

    return {
        "id": int(row["id"]),
        "experiment_id": int(row["experiment_id"]),
        "experiment_code": row["experiment_code"],
        "fabrication_batch_id": int(row["fabrication_batch_id"]),
        "batch_code": row["batch_code"],
        "filename": str(row["filename"]),
        "content_type": str(row["content_type"]),
        "size_bytes": int(row["size_bytes"]),
        "sha256": str(row["sha256"]),
        "group_assignment": str(row["group_assignment"]),
        "metrics": dict(row["metrics"]),
        "analysis_schema_version": int(row["analysis_schema_version"]),
        "created_at": _as_utc(row["created_at"]).isoformat(),
    }

def _result_summary_statement(
    *,
    owner_user_id: int | None,
    experiment_id: int | None = None,
    fabrication_batch_id: int | None = None,
) -> Any:
    """SELECT for lightweight role-scoped result summaries.

    Projects only the fields rendered by the result list response plus the
    joined experiment and batch codes. The large ``analysis`` JSON document
    and the ``created_by_id`` provenance column are deliberately not selected.
    """

    conditions = []
    if owner_user_id is not None:
        conditions.append(experiments.c.created_by_id == owner_user_id)
    if experiment_id is not None:
        conditions.append(result_files.c.experiment_id == experiment_id)
    if fabrication_batch_id is not None:
        conditions.append(
            result_files.c.fabrication_batch_id == fabrication_batch_id
        )
    return (
        select(
            result_files.c.id,
            result_files.c.experiment_id,
            experiments.c.experiment_code,
            result_files.c.fabrication_batch_id,
            fabrication_batches.c.batch_code,
            result_files.c.filename,
            result_files.c.content_type,
            result_files.c.size_bytes,
            result_files.c.sha256,
            result_files.c.group_assignment,
            result_files.c.metrics,
            result_files.c.analysis_schema_version,
            result_files.c.created_at,
        )
        .select_from(result_files)
        .join(experiments, experiments.c.id == result_files.c.experiment_id)
        .join(
            fabrication_batches,
            fabrication_batches.c.id == result_files.c.fabrication_batch_id,
        )
        .where(*conditions)
        .order_by(result_files.c.created_at.desc(), result_files.c.id.desc())
    )

def _result_assignment_statement(
    *,
    result_file_id: int | None = None,
    result_ids: list[int] | None = None,
) -> Any:
    """SELECT joining assignments with device/substrate/condition context.

    Exactly one of ``result_file_id`` (single result) or ``result_ids``
    (bulk, for single-snapshot export read models) must be provided.
    """

    if result_ids is not None:
        condition = result_device_assignments.c.result_file_id.in_(result_ids)
        ordering = (
            result_device_assignments.c.result_file_id,
            result_device_assignments.c.analysis_device_id,
        )
    else:
        condition = result_device_assignments.c.result_file_id == result_file_id
        ordering = (result_device_assignments.c.analysis_device_id,)
    return (
        select(
            result_device_assignments.c.id,
            result_device_assignments.c.result_file_id,
            result_device_assignments.c.analysis_device_id,
            result_device_assignments.c.analysis_substrate_id,
            result_device_assignments.c.instrument_label,
            result_device_assignments.c.fabrication_device_id,
            fabrication_devices.c.device_code,
            fabrication_devices.c.device_mark,
            fabrication_substrates.c.id.label("substrate_id"),
            fabrication_substrates.c.substrate_code,
            fabrication_substrates.c.substrate_mark,
            fabrication_batch_conditions.c.id.label("batch_condition_id"),
            fabrication_batch_conditions.c.source_condition_id,
            fabrication_batch_conditions.c.condition_code,
            fabrication_batch_conditions.c.condition_name,
            fabrication_batch_conditions.c.role,
            result_device_assignments.c.created_at,
        )
        .select_from(result_device_assignments)
        .join(
            fabrication_batch_conditions,
            fabrication_batch_conditions.c.id
            == result_device_assignments.c.batch_condition_id,
        )
        .outerjoin(
            fabrication_devices,
            fabrication_devices.c.id
            == result_device_assignments.c.fabrication_device_id,
        )
        .outerjoin(
            fabrication_substrates,
            fabrication_substrates.c.id == fabrication_devices.c.substrate_id,
        )
        .where(condition)
        .order_by(*ordering)
    )

class ResultsMixin:
    """Result-file upload, listing, and analysis completion."""

    async def add_result(
        self,
        experiment_id: int,
        *,
        fabrication_batch_id: int,
        filename: str,
        content_type: str,
        content: bytes,
        metrics: dict[str, float],
        analysis: dict[str, Any],
        group_assignment: str = "",
        actor_user_id: int,
        client_ip: str | None = None,
        complete_experiment: bool = False,
    ) -> dict[str, Any]:
        normalized_metrics = _normalize_metrics(metrics)
        analysis_schema_version = _analysis_schema_version(analysis)
        content_hash = hashlib.sha256(content).hexdigest()
        async with self.database.begin() as connection:
            experiment_row = await _locked_experiment(connection, experiment_id)
            current_status = ExperimentStatus(experiment_row["status"])
            if current_status not in {
                ExperimentStatus.SUGGESTED,
                ExperimentStatus.RUNNING,
                ExperimentStatus.COMPLETED,
            }:
                raise ValueError(
                    f"cannot upload a result for experiment {experiment_id} in "
                    f"{current_status.value} state"
                )
            batch_row = (
                await connection.execute(
                    select(
                        fabrication_batches.c.experiment_id,
                        fabrication_batches.c.status,
                    )
                    .where(fabrication_batches.c.id == fabrication_batch_id)
                    .with_for_update()
                )
            ).one_or_none()
            if batch_row is None or int(batch_row.experiment_id) != experiment_id:
                raise ValueError("result fabrication batch must belong to the experiment")
            if BatchStatus(batch_row.status) not in {
                BatchStatus.IN_PROGRESS,
                BatchStatus.COMPLETED,
            }:
                raise ValueError(
                    "results can be uploaded only for an in-progress or completed batch"
                )
            duplicate_id = await connection.scalar(
                select(result_files.c.id).where(
                    result_files.c.fabrication_batch_id == fabrication_batch_id,
                    result_files.c.sha256 == content_hash,
                )
            )
            if duplicate_id is not None:
                raise ValueError("this result file has already been uploaded for the batch")
            result = await connection.execute(
                insert(result_files).values(
                    experiment_id=experiment_id,
                    fabrication_batch_id=fabrication_batch_id,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=len(content),
                    sha256=content_hash,
                    content=content,
                    group_assignment=group_assignment.strip(),
                    metrics=normalized_metrics,
                    analysis=analysis,
                    analysis_schema_version=analysis_schema_version,
                    created_at=_utc_now(),
                    created_by_id=actor_user_id,
                )
            )
            file_id = _inserted_id(result)
            if complete_experiment:
                await _transition_experiment(
                    connection,
                    experiment_id,
                    allowed={ExperimentStatus.SUGGESTED, ExperimentStatus.RUNNING},
                    target=ExperimentStatus.COMPLETED,
                    metrics=normalized_metrics,
                )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="result.upload",
                entity_type="result_file",
                entity_id=str(file_id),
                details={
                    "experiment_id": experiment_id,
                    "filename": filename,
                    "fabrication_batch_id": fabrication_batch_id,
                    "sha256": content_hash,
                    "size_bytes": len(content),
                },
                client_ip=client_ip,
            )
        return await self.get_result(file_id)

    async def get_result(self, file_id: int) -> dict[str, Any]:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        result_files.c.id,
                        result_files.c.experiment_id,
                        result_files.c.fabrication_batch_id,
                        result_files.c.filename,
                        result_files.c.content_type,
                        result_files.c.size_bytes,
                        result_files.c.sha256,
                        result_files.c.group_assignment,
                        result_files.c.metrics,
                        result_files.c.analysis,
                        result_files.c.analysis_schema_version,
                        result_files.c.created_at,
                        result_files.c.created_by_id,
                    ).where(result_files.c.id == file_id)
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown result file id: {file_id}")
        return _result_record(row)

    async def get_fabrication_device_context(self, device_id: int) -> dict[str, Any]:
        """One fabrication device plus its owning experiment, for auth checks."""

        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(
                        fabrication_devices.c.id,
                        fabrication_devices.c.device_code,
                        fabrication_devices.c.device_mark,
                        fabrication_devices.c.device_ordinal,
                        fabrication_substrates.c.id.label("substrate_id"),
                        fabrication_substrates.c.substrate_code,
                        fabrication_batches.c.experiment_id,
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
                    .join(
                        fabrication_batches,
                        fabrication_batches.c.id
                        == fabrication_batch_conditions.c.fabrication_batch_id,
                    )
                    .where(fabrication_devices.c.id == device_id)
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown fabrication device id: {device_id}")
        return dict(row)

    async def get_device_jv_scans(self, device_id: int) -> dict[str, Any]:
        """Scan history of one physical device across all uploads.

        Every assigned scan is listed (valid or not) with its per-trace
        instrument metrics and provenance. The representative per direction
        is the user's explicit choice when present and valid, otherwise the
        cached highest-PCE scan; when the cache row is missing the value is
        recomputed from the traces.
        """

        context = await self.get_fabrication_device_context(device_id)
        async with self.database.engine.connect() as connection:
            file_rows = (
                await connection.execute(
                    select(
                        result_device_assignments.c.result_file_id,
                        result_files.c.filename,
                        result_files.c.analysis,
                        result_files.c.created_at,
                    )
                    .select_from(result_device_assignments)
                    .join(
                        result_files,
                        result_files.c.id
                        == result_device_assignments.c.result_file_id,
                    )
                    .where(result_device_assignments.c.fabrication_device_id == device_id)
                    .order_by(result_files.c.created_at, result_files.c.id)
                )
            ).mappings().all()
            file_analyses = [
                (
                    row["analysis"],
                    _as_utc(row["created_at"]),
                    int(row["result_file_id"]),
                    str(row["filename"]),
                )
                for row in file_rows
            ]
            entries = _device_scan_entries(
                file_analyses, fabrication_device_id=device_id
            )
            stats_rows = (
                await connection.execute(
                    select(device_scan_stats).where(
                        device_scan_stats.c.fabrication_device_id == device_id
                    )
                )
            ).mappings().all()
            selection_rows = (
                await connection.execute(
                    select(device_representative_scans).where(
                        device_representative_scans.c.fabrication_device_id == device_id
                    )
                )
            ).mappings().all()
        pool_by_direction: dict[str, list[dict[str, Any]]] = {
            direction: [] for direction in _SCAN_DIRECTIONS
        }
        for entry in entries:
            if entry["valid"] and entry["metrics"]:
                pool_by_direction[entry["direction"]].append(entry)
        stats_by_direction = {str(row["direction"]): row for row in stats_rows}
        selections = {str(row["direction"]): row for row in selection_rows}
        representatives: dict[str, dict[str, Any] | None] = {}
        explicit: dict[str, dict[str, Any] | None] = {}
        for direction in _SCAN_DIRECTIONS:
            pool = pool_by_direction[direction]
            selection = selections.get(direction)
            chosen: dict[str, Any] | None = None
            if selection is not None:
                chosen = next(
                    (
                        entry
                        for entry in pool
                        if entry["result_file_id"] == int(selection["result_file_id"])
                        and entry["trace_id"] == str(selection["trace_id"])
                    ),
                    None,
                )
                explicit[direction] = (
                    {
                        "result_file_id": int(selection["result_file_id"]),
                        "trace_id": str(selection["trace_id"]),
                    }
                    if chosen is not None
                    else None
                )
            else:
                explicit[direction] = None
            if chosen is None:
                stats = stats_by_direction.get(direction)
                if stats is not None:
                    chosen = next(
                        (
                            entry
                            for entry in pool
                            if entry["result_file_id"] == int(stats["best_result_file_id"])
                            and entry["trace_id"] == str(stats["best_trace_id"])
                        ),
                        None,
                    )
            if chosen is None:
                # Cache row missing or stale: recompute from the traces.
                chosen = _best_scan_entry(pool)
            representatives[direction] = chosen
        return {
            "fabrication_device_id": device_id,
            "device_code": context["device_code"],
            "device_mark": context["device_mark"],
            "device_ordinal": context["device_ordinal"],
            "substrate_id": context["substrate_id"],
            "substrate_code": context["substrate_code"],
            "scans": [
                {
                    "result_file_id": entry["result_file_id"],
                    "filename": entry["filename"],
                    "uploaded_at": entry["uploaded_at"].isoformat(),
                    "trace_id": entry["trace_id"],
                    "direction": entry["direction"],
                    "valid": entry["valid"],
                    "measured_at": entry["measured_at"],
                    "metrics": entry["metrics"],
                    "metric_source": entry["metric_source"],
                    "error": entry["error"],
                    "points": entry["points"],
                }
                for entry in entries
            ],
            "representative": {
                direction: (
                    {
                        "result_file_id": chosen["result_file_id"],
                        "trace_id": chosen["trace_id"],
                        "measured_at": chosen["measured_at"],
                        "metrics": chosen["metrics"],
                        "metric_source": chosen["metric_source"],
                        "from_user_selection": explicit[direction] is not None,
                    }
                    if chosen is not None
                    else None
                )
                for direction, chosen in representatives.items()
            },
            "scan_counts": {
                direction: len(pool_by_direction[direction])
                for direction in _SCAN_DIRECTIONS
            },
        }

    async def set_representative_scan(
        self,
        device_id: int,
        *,
        direction: str,
        result_file_id: int,
        trace_id: str,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Store the user's representative-scan choice for one direction."""

        if direction not in _SCAN_DIRECTIONS:
            raise ValueError(f"unknown scan direction: {direction!r}")
        async with self.database.begin() as connection:
            device_row = (
                await connection.execute(
                    select(
                        fabrication_devices.c.id,
                        fabrication_devices.c.device_code,
                    ).where(fabrication_devices.c.id == device_id)
                )
            ).mappings().one_or_none()
            if device_row is None:
                raise KeyError(f"unknown fabrication device id: {device_id}")
            file_rows = (
                await connection.execute(
                    select(
                        result_device_assignments.c.result_file_id,
                        result_files.c.analysis,
                        result_files.c.created_at,
                        result_files.c.filename,
                    )
                    .select_from(result_device_assignments)
                    .join(
                        result_files,
                        result_files.c.id
                        == result_device_assignments.c.result_file_id,
                    )
                    .where(result_device_assignments.c.fabrication_device_id == device_id)
                    .order_by(result_files.c.created_at, result_files.c.id)
                )
            ).mappings().all()
            entries = _device_scan_entries(
                [
                    (
                        row["analysis"],
                        _as_utc(row["created_at"]),
                        int(row["result_file_id"]),
                        str(row["filename"]),
                    )
                    for row in file_rows
                ],
                fabrication_device_id=device_id,
            )
            chosen = next(
                (
                    entry
                    for entry in entries
                    if entry["result_file_id"] == int(result_file_id)
                    and entry["trace_id"] == trace_id
                    and entry["direction"] == direction
                    and entry["valid"]
                    and entry["metrics"]
                ),
                None,
            )
            if chosen is None:
                raise ValueError(
                    f"scan {trace_id!r} of file {result_file_id} is not a valid "
                    f"{direction} scan of device {device_id}"
                )
            now = _utc_now()
            await connection.execute(
                delete(device_representative_scans).where(
                    device_representative_scans.c.fabrication_device_id == device_id,
                    device_representative_scans.c.direction == direction,
                )
            )
            await connection.execute(
                insert(device_representative_scans).values(
                    fabrication_device_id=device_id,
                    direction=direction,
                    result_file_id=int(result_file_id),
                    trace_id=trace_id,
                    selected_by_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            await _refresh_device_scan_stats(connection, [device_id])
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="device.set_representative_scan",
                entity_type="fabrication_device",
                entity_id=str(device_id),
                details={
                    "device_code": str(device_row["device_code"]),
                    "direction": direction,
                    "result_file_id": int(result_file_id),
                    "trace_id": trace_id,
                },
                client_ip=client_ip,
            )
        return await self.get_device_jv_scans(device_id)

    async def clear_representative_scan(
        self,
        device_id: int,
        *,
        direction: str,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Drop the explicit choice; the device falls back to best PCE."""

        if direction not in _SCAN_DIRECTIONS:
            raise ValueError(f"unknown scan direction: {direction!r}")
        async with self.database.begin() as connection:
            device_row = (
                await connection.execute(
                    select(fabrication_devices.c.device_code).where(
                        fabrication_devices.c.id == device_id
                    )
                )
            ).mappings().one_or_none()
            if device_row is None:
                raise KeyError(f"unknown fabrication device id: {device_id}")
            result = await connection.execute(
                delete(device_representative_scans).where(
                    device_representative_scans.c.fabrication_device_id == device_id,
                    device_representative_scans.c.direction == direction,
                )
            )
            await _refresh_device_scan_stats(connection, [device_id])
            if result.rowcount:
                await _add_audit_event(
                    connection,
                    actor_user_id=actor_user_id,
                    action="device.clear_representative_scan",
                    entity_type="fabrication_device",
                    entity_id=str(device_id),
                    details={
                        "device_code": str(device_row["device_code"]),
                        "direction": direction,
                    },
                    client_ip=client_ip,
                )
        return await self.get_device_jv_scans(device_id)


    async def list_results_for_experiment(self, experiment_id: int) -> list[dict[str, Any]]:
        statement = (
            select(
                result_files.c.id,
                result_files.c.experiment_id,
                result_files.c.fabrication_batch_id,
                result_files.c.filename,
                result_files.c.content_type,
                result_files.c.size_bytes,
                result_files.c.sha256,
                result_files.c.group_assignment,
                result_files.c.metrics,
                result_files.c.analysis,
                result_files.c.analysis_schema_version,
                result_files.c.created_at,
                result_files.c.created_by_id,
            )
            .where(result_files.c.experiment_id == experiment_id)
            .order_by(result_files.c.id)
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_result_record(row) for row in rows]

    async def list_results_for_batch(self, batch_id: int) -> list[dict[str, Any]]:
        statement = (
            select(
                result_files.c.id,
                result_files.c.experiment_id,
                result_files.c.fabrication_batch_id,
                result_files.c.filename,
                result_files.c.content_type,
                result_files.c.size_bytes,
                result_files.c.sha256,
                result_files.c.group_assignment,
                result_files.c.metrics,
                result_files.c.analysis,
                result_files.c.analysis_schema_version,
                result_files.c.created_at,
                result_files.c.created_by_id,
            )
            .where(result_files.c.fabrication_batch_id == batch_id)
            .order_by(result_files.c.id)
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_result_record(row) for row in rows]

    async def list_results_for_actor(
        self,
        owner_user_id: int | None,
        *,
        experiment_id: int | None = None,
        fabrication_batch_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Role-scoped result summaries with experiment and batch codes.

        Students are restricted to results of their own experiments; instructors
        and administrators receive every result. Optional experiment and batch
        filters narrow the result set. The statement builder deliberately omits
        the large ``analysis`` JSON document.
        """

        statement = _result_summary_statement(
            owner_user_id=owner_user_id,
            experiment_id=experiment_id,
            fabrication_batch_id=fabrication_batch_id,
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_result_summary_record(row) for row in rows]

    async def list_result_device_assignments(
        self, file_id: int
    ) -> list[dict[str, Any]]:
        async with self.database.engine.connect() as connection:
            rows = (
                await connection.execute(
                    _result_assignment_statement(result_file_id=file_id)
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def update_result_analysis_and_complete(
        self,
        file_id: int,
        analysis: dict[str, Any],
        *,
        substrate_assignments: Mapping[str, int],
        group_assignment: str,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Deprecated compatibility delegate for the assignment operation.

        New code calls :func:`web.operations.result_assignment.save_result_analysis`,
        which adds authorization, payload validation, regrouping, and typed
        error translation on top of :func:`apply_result_assignment`. This shim
        keeps the historical repository entry point **with its original
        exception contract**: KeyError for unknown ids, ValueError/TypeError
        for validation failures — no typed-error translation happens here.
        """
        async with self.database.begin() as connection:
            await apply_result_assignment(
                connection,
                file_id=file_id,
                analysis=analysis,
                substrate_assignments=substrate_assignments,
                group_assignment=group_assignment,
                actor_user_id=actor_user_id,
                client_ip=client_ip,
            )
        return await self.get_result(file_id)


async def apply_result_assignment(
    connection: AsyncConnection,
    *,
    file_id: int,
    analysis: dict[str, Any],
    substrate_assignments: Mapping[str, int],
    group_assignment: str,
    correction_reason: str | None = None,
    actor_user_id: int,
    client_ip: str | None = None,
) -> None:
    """Apply one result assignment inside the caller's transaction.

    Connection-level data function of the result-assignment operation
    (see :mod:`web.operations.result_assignment`, which owns the
    transaction, authorization, and validation). Locks experiment ->
    batch -> result file, associates parsed substrates/devices with the
    frozen batch layout, persists the exclusion-aware analysis, and
    writes the audit record. Raises KeyError/ValueError/TypeError for
    referenced-record and validation failures; the operation maps them
    to typed business errors.
    """
    # Lock order — experiment, then batch, then result file — matches
    # add_result so concurrent upload and assignment for one batch
    # serialize in the same order and can never deadlock (AB/BA).
    identified = (
        await connection.execute(
            select(
                result_files.c.experiment_id,
                result_files.c.fabrication_batch_id,
            ).where(result_files.c.id == file_id)
        )
    ).one_or_none()
    if identified is None:
        raise KeyError(f"unknown result file id: {file_id}")
    experiment_row = await _locked_experiment(
        connection, int(identified.experiment_id)
    )
    # Serialize laser-mark association on the parent batch row so two
    # concurrent uploads cannot bind the same physical glass mark to
    # two database substrates within one batch.
    batch_row = (
        await connection.execute(
            select(fabrication_batches.c.id)
            .where(
                fabrication_batches.c.id
                == int(identified.fabrication_batch_id),
                fabrication_batches.c.experiment_id
                == int(identified.experiment_id),
            )
            .with_for_update()
        )
    ).one_or_none()
    if batch_row is None:
        raise KeyError(
            "unknown fabrication batch id: "
            f"{identified.fabrication_batch_id}"
        )
    result_row = (
        await connection.execute(
            select(result_files)
            .where(result_files.c.id == file_id)
            .with_for_update()
        )
    ).mappings().one_or_none()
    if result_row is None:
        raise KeyError(f"unknown result file id: {file_id}")
    analysis_devices = analysis.get("devices")
    if not isinstance(analysis_devices, list) or not analysis_devices:
        raise ValueError("result analysis must contain at least one device")
    analysis_substrates = analysis.get("substrates")
    if not isinstance(analysis_substrates, list) or not analysis_substrates:
        raise ValueError("result analysis must contain at least one substrate")
    analysis_substrate_ids = [
        str(substrate.get("substrate_id", "")).strip()
        for substrate in analysis_substrates
    ]
    if any(not substrate_id for substrate_id in analysis_substrate_ids):
        raise ValueError("every result substrate must have an analysis substrate id")
    normalized_assignments = {
        str(substrate_id).strip(): int(batch_condition_id)
        for substrate_id, batch_condition_id in substrate_assignments.items()
    }
    if set(normalized_assignments) != set(analysis_substrate_ids):
        raise ValueError("every result substrate must be assigned to a batch condition")
    previous_analysis = result_row["analysis"] or {}
    previous_assignments = {
        str(substrate["substrate_id"]): int(substrate["batch_condition_id"])
        for substrate in previous_analysis.get("substrates", [])
        if substrate.get("batch_condition_id") is not None
    }
    assignment_changes = [
        {
            "analysis_substrate_id": substrate_id,
            "from_batch_condition_id": previous_assignments.get(substrate_id),
            "to_batch_condition_id": condition_id,
        }
        for substrate_id, condition_id in normalized_assignments.items()
        if previous_assignments.get(substrate_id) != condition_id
    ]
    if previous_assignments and assignment_changes and not (correction_reason or "").strip():
        raise ValueError("a correction reason is required when saved assignments change")
    previous_exclusions = {
        str(device["device_id"]): str(device.get("exclusion_reason", ""))
        for device in previous_analysis.get("devices", [])
        if device.get("excluded")
    }
    new_exclusions = {
        str(device["device_id"]): str(device.get("exclusion_reason", ""))
        for device in analysis_devices if device.get("excluded")
    }
    exclusion_changes = [
        {"analysis_device_id": device_id,
         "from_reason": previous_exclusions.get(device_id),
         "to_reason": new_exclusions.get(device_id)}
        for device_id in sorted(previous_exclusions.keys() | new_exclusions.keys())
        if previous_exclusions.get(device_id) != new_exclusions.get(device_id)
    ]
    condition_rows = (
        await connection.execute(
            select(fabrication_batch_conditions).where(
                fabrication_batch_conditions.c.fabrication_batch_id
                == int(result_row["fabrication_batch_id"])
            )
        )
    ).mappings().all()
    conditions = {int(row["id"]): row for row in condition_rows}
    if set(normalized_assignments.values()) - set(conditions):
        raise ValueError("assigned conditions must belong to the result batch")
    # DB substrates of this batch, grouped by their batch_condition.
    db_substrates = (
        await connection.execute(
            select(
                fabrication_substrates.c.id.label("substrate_id"),
                fabrication_substrates.c.substrate_code,
                fabrication_substrates.c.substrate_mark,
                fabrication_substrates.c.batch_condition_id,
            )
            .select_from(fabrication_substrates)
            .join(
                fabrication_batch_conditions,
                fabrication_batch_conditions.c.id
                == fabrication_substrates.c.batch_condition_id,
            )
            .where(
                fabrication_batch_conditions.c.fabrication_batch_id
                == int(result_row["fabrication_batch_id"])
            )
            .order_by(fabrication_substrates.c.substrate_ordinal)
        )
    ).mappings().all()
    # Substrates already laser-marked (earlier upload) vs still blank.
    marked_by_mark: dict[str, Any] = {}
    blank_by_condition: dict[int, list[Any]] = {}
    for row in db_substrates:
        mark = row["substrate_mark"]
        if mark:
            marked_by_mark[str(mark)] = row
        else:
            blank_by_condition.setdefault(
                int(row["batch_condition_id"]), []
            ).append(row)

    normalized_analysis = deepcopy(analysis)
    normalized_substrates = {
        str(substrate["substrate_id"]): substrate
        for substrate in normalized_analysis["substrates"]
    }
    now = _utc_now()
    # Devices the file was previously assigned to (before the delete below)
    # so their caches are rebuilt even when the file moves away from them.
    previous_device_ids = set(
        await connection.scalars(
            select(result_device_assignments.c.fabrication_device_id).where(
                result_device_assignments.c.result_file_id == file_id,
                result_device_assignments.c.fabrication_device_id.isnot(None),
            )
        )
    )
    await connection.execute(
        delete(result_device_assignments).where(
            result_device_assignments.c.result_file_id == file_id
        )
    )
    # Per-condition CSV substrate counts for shortfall validation.
    csv_counts_by_condition: dict[int, int] = {}
    for analysis_substrate_id, batch_condition_id in normalized_assignments.items():
        condition = conditions[batch_condition_id]
        csv_counts_by_condition[int(batch_condition_id)] = (
            csv_counts_by_condition.get(int(batch_condition_id), 0) + 1
        )
        normalized_substrates[analysis_substrate_id].update(
            {
                "group_id": str(batch_condition_id),
                "batch_condition_id": batch_condition_id,
                "condition_code": str(condition["condition_code"]),
                "condition_name": str(condition["condition_name"]),
            }
        )

    # Enforce per-condition actual count and associate laser marks.
    for condition_id, count in csv_counts_by_condition.items():
        condition = conditions[condition_id]
        actual_count = condition["actual_substrate_count"]
        if actual_count is None:
            raise ValueError(
                f"condition {condition['condition_name']} has no recorded "
                "actual substrate count; complete the batch first"
            )
        if count > int(actual_count):
            raise ValueError(
                f"CSV substrate count {count} for condition "
                f"{condition['condition_name']} exceeds the recorded "
                f"actual substrate count {actual_count}"
            )
        if count < int(actual_count):
            # Made-but-not-measured substrates require a typed
            # measurement_shortfall deviation on this condition; any
            # other deviation does not unlock the gate.
            if not await _has_qualifying_condition_deviation(
                connection, condition_id, "measurement_shortfall"
            ):
                raise ValueError(
                    f"condition {condition['condition_name']} measured "
                    f"{count} substrates but {actual_count} were made; "
                    "record a measurement_shortfall deviation for the "
                    "unmeasured substrate(s)"
                )

    # A saved assignment may have bound a CSV laser mark to the wrong
    # condition. A correction can release that binding only when this file
    # owns it and no other uploaded result still references the substrate.
    # The batch lock above serializes this with assignments from other files.
    for analysis_substrate_id, condition_id in normalized_assignments.items():
        if not LASER_MARK_PATTERN.fullmatch(analysis_substrate_id.upper()):
            continue
        laser_mark = normalize_laser_mark(analysis_substrate_id)
        marked_row = marked_by_mark.get(laser_mark)
        if marked_row is None or int(marked_row["batch_condition_id"]) == condition_id:
            continue
        if previous_assignments.get(analysis_substrate_id) != int(marked_row["batch_condition_id"]):
            continue
        physical_device_ids = set((await connection.execute(
            select(fabrication_devices.c.id).where(
                fabrication_devices.c.substrate_id == int(marked_row["substrate_id"])
            )
        )).scalars().all())
        if not (physical_device_ids & previous_device_ids):
            continue
        other_file_reference = await connection.scalar(
            select(result_device_assignments.c.id).where(
                result_device_assignments.c.fabrication_device_id.in_(physical_device_ids)
            ).limit(1)
        )
        if other_file_reference is not None:
            raise ValueError(
                f"laser mark {laser_mark} is used by another result file; "
                "correct that file's assignment before changing this one"
            )
        await connection.execute(
            update(fabrication_substrates)
            .where(fabrication_substrates.c.id == int(marked_row["substrate_id"]))
            .values(substrate_mark=None, updated_at=now)
        )
        marked_by_mark.pop(laser_mark)
        blank_by_condition.setdefault(int(marked_row["batch_condition_id"]), []).append(marked_row)

    # Associate substrates with known physical marks. Instrument-only names
    # still receive a manually chosen condition, but cannot safely identify
    # one of the fabricated substrates within that condition.
    associated: dict[str, Any] = {}
    substrate_devices: dict[int, dict[int, Any]] = {}
    for analysis_substrate_id, batch_condition_id in normalized_assignments.items():
        if not LASER_MARK_PATTERN.fullmatch(analysis_substrate_id.upper()):
            continue
        laser_mark = normalize_laser_mark(analysis_substrate_id)
        row = marked_by_mark.get(laser_mark)
        if row is not None and int(row["batch_condition_id"]) != int(
            batch_condition_id
        ):
            raise ValueError(
                f"laser mark {laser_mark} is already associated with "
                f"condition {conditions[int(row['batch_condition_id'])]['condition_name']}, "
                "not "
                f"{conditions[int(batch_condition_id)]['condition_name']}"
            )
        if row is None:
            blanks = blank_by_condition.get(int(batch_condition_id), [])
            if not blanks:
                raise ValueError(
                    f"no blank substrate remains in condition "
                    f"{conditions[int(batch_condition_id)]['condition_name']} "
                    f"for laser mark {laser_mark}"
                )
            row = blanks.pop(0)
            await connection.execute(
                update(fabrication_substrates)
                .where(fabrication_substrates.c.id == row["substrate_id"])
                .values(substrate_mark=laser_mark, updated_at=now)
            )
            marked_by_mark[laser_mark] = row
        associated[analysis_substrate_id] = row
        substrate_id = int(row["substrate_id"])
        if substrate_id not in substrate_devices:
            db_devices = (
                await connection.execute(
                    select(
                        fabrication_devices.c.id.label("device_id"),
                        fabrication_devices.c.device_code,
                        fabrication_devices.c.device_ordinal,
                    )
                    .where(
                        fabrication_devices.c.substrate_id == substrate_id
                    )
                    .order_by(fabrication_devices.c.device_ordinal)
                )
            ).mappings().all()
            substrate_devices[substrate_id] = {
                int(device_row["device_ordinal"]): device_row
                for device_row in db_devices
            }

    # Bind each parsed device to the database device whose
    # device_ordinal equals the physical channel number in the
    # instrument label (e.g. "A001 Channel 2" -> ordinal 2). Labels
    # without exactly one positive channel token are ambiguous and
    # rejected; trace order never decides physical identity.
    seen_ordinals_by_substrate: dict[str, set[int]] = {}
    for device in normalized_analysis["devices"]:
        analysis_device_id = str(device["device_id"])
        analysis_substrate_id = str(device["substrate_id"])
        batch_condition_id = normalized_assignments[analysis_substrate_id]
        condition = conditions[batch_condition_id]
        option = associated.get(analysis_substrate_id)
        if option is None:
            # An instrument name such as "Control-1" is sufficient for
            # condition-level statistics and figures. Leave physical-device
            # provenance unresolved rather than linking to an arbitrary
            # fabricated substrate with the same condition.
            device.update(
                {
                    "group_id": str(batch_condition_id),
                    "batch_condition_id": batch_condition_id,
                    "condition_code": str(condition["condition_code"]),
                    "condition_name": str(condition["condition_name"]),
                }
            )
            for key in (
                "fabrication_device_id", "fabrication_substrate_id",
                "fabrication_substrate_code", "fabrication_device_code",
            ):
                device.pop(key, None)
            await connection.execute(
                insert(result_device_assignments).values(
                    result_file_id=file_id,
                    analysis_device_id=analysis_device_id,
                    analysis_substrate_id=analysis_substrate_id,
                    instrument_label=str(device.get("label", "")),
                    batch_condition_id=batch_condition_id,
                    fabrication_device_id=None,
                    created_at=now,
                )
            )
            continue
        substrate_id = int(option["substrate_id"])
        device_ordinal = device.get("device_ordinal")
        if (
            isinstance(device_ordinal, bool)
            or not isinstance(device_ordinal, int)
            or device_ordinal < 1
        ):
            raise ValueError(
                f"instrument label {device.get('label', '')!r} for "
                f"substrate {analysis_substrate_id} does not identify "
                "a physical device channel; save J-V data with labels "
                "like 'A001 Channel 2'"
            )
        seen_ordinals = seen_ordinals_by_substrate.setdefault(
            analysis_substrate_id, set()
        )
        if device_ordinal in seen_ordinals:
            raise ValueError(
                f"substrate {analysis_substrate_id} has duplicate "
                f"parsed devices for channel {device_ordinal}"
            )
        seen_ordinals.add(device_ordinal)
        devices_by_ordinal = substrate_devices.get(substrate_id, {})
        db_device = devices_by_ordinal.get(device_ordinal)
        if db_device is None:
            raise ValueError(
                f"substrate {analysis_substrate_id} has no recorded "
                f"device with channel {device_ordinal} in its layout"
            )
        fabrication_device_id = int(db_device["device_id"])
        # device_mark is a derived display artifact; the substrate
        # laser mark (written above) plus the device ordinal fully
        # identify the physical device, so no separate write is needed.
        device.update(
            {
                "group_id": str(batch_condition_id),
                "fabrication_device_id": fabrication_device_id,
                "batch_condition_id": batch_condition_id,
                "condition_code": str(condition["condition_code"]),
                "condition_name": str(condition["condition_name"]),
                "fabrication_substrate_id": substrate_id,
                "fabrication_substrate_code": str(option["substrate_code"]),
                "fabrication_device_code": str(db_device["device_code"]),
            }
        )
        await connection.execute(
            insert(result_device_assignments).values(
                result_file_id=file_id,
                analysis_device_id=analysis_device_id,
                analysis_substrate_id=analysis_substrate_id,
                instrument_label=str(device.get("label", "")),
                batch_condition_id=batch_condition_id,
                fabrication_device_id=fabrication_device_id,
                created_at=now,
            )
        )
    new_fabrication_device_ids = {
        int(device["fabrication_device_id"])
        for device in normalized_analysis["devices"]
        if device.get("fabrication_device_id") is not None
    }
    await connection.execute(
        update(result_files)
        .where(result_files.c.id == file_id)
        .values(
            analysis=normalized_analysis,
            analysis_schema_version=_analysis_schema_version(normalized_analysis),
            group_assignment=group_assignment.strip(),
            # Legacy flat cache retained for training export compatibility.
            # It pools scan directions and must not be used for scientific
            # statistics or displayed as a direction-specific result.
            metrics=_normalize_metrics(_flat_metrics_from_analysis(normalized_analysis)),
        )
    )
    # The per-device directional stats cache reads the persisted analysis
    # (devices carry their fabrication_device_id only in the stored JSON),
    # so it is rebuilt after the UPDATE above, for every affected device
    # (previous and new).
    await _refresh_device_scan_stats(
        connection, previous_device_ids | new_fabrication_device_ids
    )
    experiment_id = int(result_row["experiment_id"])
    current_status = ExperimentStatus(experiment_row["status"])
    if current_status in {ExperimentStatus.SUGGESTED, ExperimentStatus.RUNNING}:
        await _transition_experiment(
            connection,
            experiment_id,
            allowed={ExperimentStatus.SUGGESTED, ExperimentStatus.RUNNING},
            target=ExperimentStatus.COMPLETED,
            metrics=_normalize_metrics(_flat_metrics_from_analysis(normalized_analysis)),
        )
    await _add_audit_event(
        connection,
        actor_user_id=actor_user_id,
        action="result.assign_groups",
        entity_type="result_file",
        entity_id=str(file_id),
        details={
            "experiment_id": experiment_id,
            "fabrication_batch_id": int(result_row["fabrication_batch_id"]),
            "assigned_substrate_count": len(normalized_assignments),
            "excluded_device_count": sum(
                1
                for device in normalized_analysis["devices"]
                if device.get("excluded")
            ),
            "assignment_changes": assignment_changes,
            "manual_exclusion_changes": exclusion_changes,
            "correction_reason": (correction_reason or "").strip() or None,
        },
        client_ip=client_ip,
    )
