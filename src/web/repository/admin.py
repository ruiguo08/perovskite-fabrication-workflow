"""Admin-domain (audit/maintenance/training) methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

import hashlib
import json
from perovskite_bo.web_adapter import (
    extract_actual_process_features,
    extract_condition_features,
    extract_result_metrics,
    recorded_actual_methods,
    training_parameter_methods,
)

from typing import Any, Mapping
from sqlalchemy import and_, func, select
from datetime import datetime, timedelta

from ..database import (
    audit_events,
    experiments,
    fabrication_batch_conditions,
    fabrication_batches,
    process_execution_members,
    process_executions,
    result_device_assignments,
    result_files,
    sessions,
    users,
)
from .helpers import _as_utc
from .records import AuditEventRecord, BatchStatus

class AdminMixin:
    """Audit export, maintenance counters, and training-data export."""

    async def list_audit_events(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        actor_user_id: int | None = None,
        action_prefix: str | None = None,
        limit: int = 10_000,
    ) -> list[AuditEventRecord]:
        conditions = []
        if since is not None:
            conditions.append(audit_events.c.created_at >= since)
        if until is not None:
            conditions.append(audit_events.c.created_at <= until)
        if actor_user_id is not None:
            conditions.append(audit_events.c.actor_user_id == actor_user_id)
        if action_prefix:
            escaped = (
                action_prefix.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                audit_events.c.action.like(f"{escaped}%", escape="\\")
            )
        statement = (
            select(
                audit_events, users.c.username.label("actor_username")
            )
            .select_from(audit_events)
            .outerjoin(users, users.c.id == audit_events.c.actor_user_id)
            .order_by(audit_events.c.id.asc())
            .limit(limit)
        )
        if conditions:
            statement = statement.where(and_(*conditions))
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [
            AuditEventRecord(
                id=int(row["id"]),
                created_at=_as_utc(row["created_at"]),
                actor_user_id=(
                    int(row["actor_user_id"])
                    if row["actor_user_id"] is not None
                    else None
                ),
                actor_username=(
                    str(row["actor_username"])
                    if row["actor_username"] is not None
                    else None
                ),
                action=str(row["action"]),
                entity_type=str(row["entity_type"]),
                entity_id=(
                    str(row["entity_id"])
                    if row["entity_id"] is not None
                    else None
                ),
                client_ip=(
                    str(row["client_ip"])
                    if row["client_ip"] is not None
                    else None
                ),
                details=dict(row["details"] or {}),
            )
            for row in rows
        ]

    async def maintenance_status(self, *, now: datetime) -> dict[str, int]:
        async with self.database.engine.connect() as connection:

            async def _count(statement: Any) -> int:
                return int(await connection.scalar(statement) or 0)

            return {
                "users": await _count(select(func.count()).select_from(users)),
                "active_sessions": await _count(
                    select(func.count())
                    .select_from(sessions)
                    .where(sessions.c.expires_at > now)
                ),
                "experiments": await _count(
                    select(func.count()).select_from(experiments)
                ),
                "fabrication_batches": await _count(
                    select(func.count()).select_from(fabrication_batches)
                ),
                "result_files": await _count(
                    select(func.count()).select_from(result_files)
                ),
                "audit_events_last_24h": await _count(
                    select(func.count())
                    .select_from(audit_events)
                    .where(audit_events.c.created_at >= now - timedelta(hours=24))
                ),
            }

    async def build_training_dataset(
        self,
        *,
        experiment_id: int | None = None,
        batch_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Extract read-only (X, y) training rows from recorded executions.

        Without an explicit ``batch_id`` only completed batches are included,
        because their process and result data are terminal. Features come from
        the **actual** perovskite process snapshots recorded per substrate
        (feature_source ``"actual"``); parameters missing from a recorded
        snapshot fall back to the frozen plan (``"mixed"``), and conditions
        without recorded actuals keep the planned snapshot (``"planned"``).
        A condition executed under more than one actual parameter variant is
        split into one row per variant, each carrying the substrate ids
        measured under that variant so the metrics join to the right X.
        Rows combine the ``perovskite_bo.web_adapter`` feature/metric
        extraction with batch provenance; conditions without measured devices
        keep ``metrics=None`` instead of fabricated values.
        """
        condition_filters = []
        if batch_id is not None:
            condition_filters.append(
                fabrication_batches.c.id == batch_id
            )
        else:
            condition_filters.append(
                fabrication_batches.c.status == BatchStatus.COMPLETED.value
            )
        if experiment_id is not None:
            condition_filters.append(
                fabrication_batches.c.experiment_id == experiment_id
            )
        condition_statement = (
            select(
                fabrication_batch_conditions.c.id,
                fabrication_batch_conditions.c.condition_code,
                fabrication_batch_conditions.c.condition_name,
                fabrication_batch_conditions.c.role,
                fabrication_batch_conditions.c.source_condition_hash,
                fabrication_batch_conditions.c.recipe_snapshot,
                fabrication_batches.c.id.label("batch_id"),
                fabrication_batches.c.batch_code,
                fabrication_batches.c.status.label("batch_status"),
                fabrication_batches.c.experiment_id,
            )
            .select_from(fabrication_batch_conditions)
            .join(
                fabrication_batches,
                fabrication_batches.c.id
                == fabrication_batch_conditions.c.fabrication_batch_id,
            )
            .where(and_(*condition_filters))
            .order_by(
                fabrication_batches.c.id.asc(),
                fabrication_batch_conditions.c.id.asc(),
            )
        )
        async with self.database.engine.connect() as connection:
            condition_rows = (
                (await connection.execute(condition_statement)).mappings().all()
            )
            condition_ids = [int(row["id"]) for row in condition_rows]
            batch_ids = sorted({int(row["batch_id"]) for row in condition_rows})
            assignments = []
            analyses: dict[int, Any] = {}
            execution_rows: list[Mapping[str, Any]] = []
            if batch_ids:
                assignments = (
                    (
                        await connection.execute(
                            select(
                                result_device_assignments.c.analysis_device_id,
                                result_device_assignments.c.batch_condition_id,
                                result_device_assignments.c.result_file_id,
                                result_files.c.analysis,
                            )
                            .select_from(result_device_assignments)
                            .join(
                                result_files,
                                result_files.c.id
                                == result_device_assignments.c.result_file_id,
                            )
                            .where(
                                result_files.c.fabrication_batch_id.in_(batch_ids)
                            )
                            .order_by(result_device_assignments.c.id.asc())
                        )
                    )
                    .mappings()
                    .all()
                )
                analyses = {
                    int(row["id"]): row["analysis"]
                    for row in (
                        (
                            await connection.execute(
                                select(
                                    result_files.c.id, result_files.c.analysis
                                ).where(
                                    result_files.c.fabrication_batch_id.in_(
                                        batch_ids
                                    )
                                )
                            )
                        )
                        .mappings()
                        .all()
                    )
                }
            if condition_ids:
                execution_rows = (
                    (
                        await connection.execute(
                            select(
                                process_execution_members.c.batch_condition_id,
                                process_execution_members.c.substrate_id,
                                process_executions.c.method,
                                process_executions.c.actual_process_snapshot,
                            )
                            .select_from(process_execution_members)
                            .join(
                                process_executions,
                                process_executions.c.id
                                == process_execution_members.c.process_execution_id,
                            )
                            .where(
                                process_execution_members.c.batch_condition_id.in_(
                                    condition_ids
                                ),
                                process_executions.c.layer_type == "perovskite",
                                process_executions.c.method.in_(
                                    ("spin_coating", "vcd", "annealing")
                                ),
                                process_executions.c.actual_process_snapshot.isnot(
                                    None
                                ),
                            )
                        )
                    )
                    .mappings()
                    .all()
                )
            device_metrics_by_condition: dict[int, list[dict[str, Any]]] = {}
            substrate_metrics_by_condition: dict[int, dict[int, list[dict[str, Any]]]] = {}
            unmatched_metrics_by_condition: dict[int, list[dict[str, Any]]] = {}
            result_files_by_condition: dict[int, list[int]] = {}
            excluded_devices_by_condition: dict[int, int] = {}
            for assignment in assignments:
                condition_id = int(assignment["batch_condition_id"])
                file_id = int(assignment["result_file_id"])
                analysis = analyses.get(file_id) or {}
                devices_by_id = {
                    str(device.get("device_id")): device
                    for device in analysis.get("devices", [])
                    if isinstance(device, Mapping)
                }
                device = devices_by_id.get(str(assignment["analysis_device_id"]))
                metrics = device.get("metrics") if device is not None else None
                # Excluded devices stay in the stored analysis for provenance
                # but must never seed a training target; the analyst-facing
                # statistics already honor the same flag.
                if device is not None and device.get("excluded"):
                    excluded_devices_by_condition[condition_id] = (
                        excluded_devices_by_condition.get(condition_id, 0) + 1
                    )
                elif isinstance(metrics, Mapping):
                    # Schema 6 stores metrics per scan direction (forward /
                    # reverse are separate physical measurements); each
                    # direction seeds its own training sample, exactly like
                    # the pooled statistics. The legacy flat shape and the
                    # migrated "combined" tier are single-entry records.
                    if "forward" in metrics or "reverse" in metrics:
                        metric_entries = [
                            dict(tier)
                            for direction in ("forward", "reverse")
                            if isinstance(
                                tier := metrics.get(direction), Mapping
                            )
                        ]
                    else:
                        metric_entries = [dict(metrics)]
                    if not metric_entries:
                        metric_entries = []
                    hysteresis_index = device.get("hysteresis_index")
                    for entry in metric_entries:
                        if isinstance(hysteresis_index, (int, float)):
                            entry["hysteresis_index"] = float(hysteresis_index)
                        device_metrics_by_condition.setdefault(condition_id, []).append(
                            entry
                        )
                        substrate_id = device.get("fabrication_substrate_id")
                        if substrate_id is not None:
                            substrate_metrics_by_condition.setdefault(
                                condition_id, {}
                            ).setdefault(int(substrate_id), []).append(entry)
                        else:
                            # Historical analyses predating substrate attribution
                            # cannot be mapped onto a variant; keep them aside so
                            # they still surface in a row.
                            unmatched_metrics_by_condition.setdefault(
                                condition_id, []
                            ).append(entry)
                file_list = result_files_by_condition.setdefault(condition_id, [])
                if file_id not in file_list:
                    file_list.append(file_id)
            # Group substrates by the actual snapshots of their perovskite
            # executions: substrates sharing one (method, snapshot) combination
            # were fabricated under the same actual parameter variant.
            substrate_variants: dict[int, dict[int, dict[str, str]]] = {}
            snapshots_by_hash: dict[int, dict[tuple[str, str], Any]] = {}
            for row in execution_rows:
                condition_id = int(row["batch_condition_id"])
                substrate_id = int(row["substrate_id"])
                method = str(row["method"])
                snapshot = row["actual_process_snapshot"]
                digest = hashlib.sha256(
                    json.dumps(snapshot, sort_keys=True).encode("utf-8")
                ).hexdigest()
                substrate_variants.setdefault(condition_id, {}).setdefault(
                    substrate_id, {}
                )[method] = digest
                snapshots_by_hash.setdefault(condition_id, {})[
                    (method, digest)
                ] = snapshot
            variants_by_condition: dict[int, dict[tuple, dict[str, Any]]] = {}
            for condition_id, per_substrate in substrate_variants.items():
                for substrate_id, method_hashes in per_substrate.items():
                    key = tuple(sorted(method_hashes.items()))
                    variant = variants_by_condition.setdefault(
                        condition_id, {}
                    ).setdefault(
                        key, {"methods": {}, "substrate_ids": set()}
                    )
                    variant["substrate_ids"].add(substrate_id)
                    for method, digest in method_hashes.items():
                        variant["methods"][method] = snapshots_by_hash[condition_id][
                            (method, digest)
                        ]
        rows: list[dict[str, Any]] = []
        for source in condition_rows:
            condition_id = int(source["id"])
            base = {
                "batch_condition_id": condition_id,
                "condition_code": str(source["condition_code"]),
                "condition_name": str(source["condition_name"]),
                "role": str(source["role"]),
                "source_condition_hash": str(source["source_condition_hash"]),
                "experiment_id": int(source["experiment_id"]),
                "batch_id": int(source["batch_id"]),
                "batch_code": str(source["batch_code"]),
                "batch_status": str(source["batch_status"]),
                "result_file_ids": result_files_by_condition.get(condition_id, []),
                "excluded_device_count": excluded_devices_by_condition.get(
                    condition_id, 0
                ),
            }
            planned_features = extract_condition_features(
                source["recipe_snapshot"]
            )
            variants = variants_by_condition.get(condition_id) or {}
            if not variants:
                rows.append(
                    {
                        **base,
                        "substrate_ids": [],
                        "variant_index": 0,
                        "feature_source": "planned",
                        "features": planned_features,
                        "metrics": extract_result_metrics(
                            device_metrics_by_condition.get(condition_id, [])
                        ),
                    }
                )
                continue
            metrics_map = substrate_metrics_by_condition.get(condition_id) or {}
            parameter_methods = training_parameter_methods()
            for variant_index, variant in enumerate(variants.values()):
                # Per variant: which methods this variant's substrates actually
                # recorded. Computing this outside the loop would reuse the
                # grouping loop's leftover variable — another condition's or
                # variant's method set — and misdecide the fallback.
                recorded_methods = recorded_actual_methods(variant["methods"])
                actual_features = extract_actual_process_features(
                    variant["methods"]
                )
                if actual_features is None:
                    features = planned_features
                    feature_source = "planned"
                else:
                    features = dict(actual_features)
                    feature_source = "actual"
                    for name, value in features.items():
                        if value is not None or planned_features.get(name) is None:
                            continue
                        if parameter_methods[name] in recorded_methods:
                            # The method ran and its actual snapshot was
                            # recorded, but it does not contain this step
                            # (e.g. a two-spin actual against a three-spin
                            # plan): the step was not executed, so it must
                            # stay None rather than being restored from the
                            # plan.
                            continue
                        # The whole method lacks an actual record; fall back
                        # to the frozen plan and say so.
                        features[name] = planned_features[name]
                        feature_source = "mixed"
                substrate_ids = sorted(variant["substrate_ids"])
                variant_metrics = [
                    metric_entry
                    for substrate_id in substrate_ids
                    for metric_entry in metrics_map.get(substrate_id, [])
                ]
                rows.append(
                    {
                        **base,
                        "substrate_ids": substrate_ids,
                        "variant_index": variant_index,
                        "feature_source": feature_source,
                        "features": features,
                        "metrics": extract_result_metrics(variant_metrics),
                    }
                )
            # Measured substrates whose perovskite executions carried no
            # actual snapshot (cancelled without recording, or analyses that
            # predate substrate attribution) must not silently lose their
            # metrics: park them on one synthetic planned row.
            covered_substrate_ids = {
                substrate_id
                for variant in variants.values()
                for substrate_id in variant["substrate_ids"]
            }
            leftover_substrate_ids = sorted(
                set(metrics_map) - covered_substrate_ids
            )
            leftover_metrics = [
                metric_entry
                for substrate_id in leftover_substrate_ids
                for metric_entry in metrics_map[substrate_id]
            ] + unmatched_metrics_by_condition.get(condition_id, [])
            if leftover_substrate_ids or leftover_metrics:
                rows.append(
                    {
                        **base,
                        "substrate_ids": leftover_substrate_ids,
                        "variant_index": len(variants),
                        "feature_source": "planned",
                        "features": planned_features,
                        "metrics": extract_result_metrics(leftover_metrics),
                    }
                )
        return rows
