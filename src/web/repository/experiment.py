"""Experiment-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from perovskite_bo.device_recipe import deposition_recipe_from_process

from typing import Any, Iterable, Mapping, Sequence
from perovskite_bo import DepositionRecipe, ExperimentRecord, ExperimentStatus
from sqlalchemy import exists, func, insert, select, text

from ..condition_snapshot import (
    canonical_hash as condition_canonical_hash,
    validate_condition_snapshot,
)
from ..database import (
    CAMPAIGN_ID_MAX_LENGTH,
    EXPERIMENT_CODE_MAX_LENGTH,
    campaigns,
    experiment_conditions,
    experiments,
)
from ..device_layouts import DeviceLayout, expected_device_count, layout_snapshot
from ..services.catalog_service import list_device_layouts
from ..services.legacy_adapter import materialize_legacy_conditions
from .helpers import (
    _actor_role,
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _normalize_metrics,
    _transition_experiment,
    _utc_now,
    _validate_baseline_version_for_condition,
)
from .records import CampaignStatus, ConditionRole, PlanStatus

def _control_recipe_snapshot_subquery() -> Any:
    """Correlated subquery yielding the hash-verified control snapshot.

    ``ExperimentRecord.recipe`` is derived from the experiment's control (or
    standalone) condition snapshot instead of a parent-column copy, so every
    reader sees exactly the configuration that passed the workflow gates.
    """

    return (
        select(experiment_conditions.c.recipe_snapshot)
        .where(
            experiment_conditions.c.experiment_id == experiments.c.id,
            experiment_conditions.c.role.in_(
                [ConditionRole.CONTROL.value, ConditionRole.STANDALONE.value]
            ),
        )
        .order_by(experiment_conditions.c.id)
        .limit(1)
        .scalar_subquery()
        .label("control_recipe_snapshot")
    )

def _experiment_record(row: Mapping[str, Any]) -> ExperimentRecord:
    snapshot = row.get("control_recipe_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError(
            f"experiment {row['id']} has no control or standalone condition "
            "snapshot; the record cannot be reconstructed"
        )
    if not isinstance(snapshot.get("deposition_process"), Mapping):
        raise ValueError(
            f"experiment {row['id']} has an incomplete control condition "
            "snapshot; the record cannot be reconstructed"
        )
    # The recipe is derived from the hash-verified control snapshot. The
    # flattened deposition fields cover every consumer (API responses, plan
    # export, BO strategy history); the group-scoped stack detail lives in
    # the condition snapshots, where it is authoritative.
    recipe_fields = deposition_recipe_from_process(snapshot["deposition_process"])
    device = snapshot.get("device")
    device_summary = None
    if isinstance(device, Mapping):
        substrate = device.get("substrate")
        material = (
            str(substrate.get("material"))
            if isinstance(substrate, Mapping) and substrate.get("material")
            else None
        )
        layer_names = [
            str(layer.get("name"))
            for layer in device.get("layers", [])
            if isinstance(layer, Mapping) and layer.get("name")
        ]
        device_summary = " / ".join(
            [name for name in [material] if name] + layer_names
        ) or None
    return ExperimentRecord(
        device_summary=device_summary,
        id=int(row["id"]),
        recipe=DepositionRecipe.from_mapping(recipe_fields),
        status=ExperimentStatus(row["status"]),
        metrics={str(key): float(value) for key, value in row["metrics"].items()},
        failure_reason=row["failure_reason"],
        created_at=_as_utc(row["created_at"]).isoformat(),
        updated_at=_as_utc(row["updated_at"]).isoformat(),
        campaign_id=row["campaign_id"],
        experiment_code=row["experiment_code"],
        series_version=int(row["series_version"]),
        plan_type=row.get("plan_type"),
        plan_status=row.get("plan_status"),
    )

def _has_reconstructable_recipe_predicate() -> Any:
    """True when the experiment owns a control/standalone condition.

    Plans are always created with at least one materialized condition, so
    only pre-conditions legacy rows (or raw manual inserts) can violate
    this; such rows have no recipe representation in the current model and
    are excluded from list reads instead of failing the whole listing.
    """

    return exists(
        select(experiment_conditions.c.id).where(
            experiment_conditions.c.experiment_id == experiments.c.id,
            experiment_conditions.c.role.in_(
                [ConditionRole.CONTROL.value, ConditionRole.STANDALONE.value]
            ),
        )
    )

def _normalize_campaign_id(campaign_id: str | None) -> str | None:
    if campaign_id is None:
        return None
    if not isinstance(campaign_id, str):
        raise TypeError("campaign_id must be a string or None")
    normalized = campaign_id.strip()
    if not normalized:
        raise ValueError("campaign_id must be a non-blank string")
    if len(normalized) > CAMPAIGN_ID_MAX_LENGTH:
        raise ValueError(
            f"campaign_id must not exceed {CAMPAIGN_ID_MAX_LENGTH} characters"
        )
    return normalized

class ExperimentsMixin:
    """Experiment creation, listing, and completion."""

    async def add_experiment(
        self,
        recipe: DepositionRecipe,
        *,
        campaign_id: str | None,
        source_baseline_version_id: int | None = None,
        condition_plans: Sequence[Mapping[str, Any]] | None = None,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> ExperimentRecord:
        normalized_campaign_id = _normalize_campaign_id(campaign_id)
        if normalized_campaign_id is None:
            raise ValueError("an active instructor-created campaign is required")
        recipe_values = recipe.to_dict()
        if not isinstance(recipe_values.get("device_recipe"), Mapping):
            raise ValueError(
                "a complete device_recipe is required; baselines and presets must be "
                "expanded before an experiment is saved"
            )
        now = _utc_now()
        async with self.database.begin() as connection:
            campaign_status = await connection.scalar(
                select(campaigns.c.status).where(
                    campaigns.c.code == normalized_campaign_id
                )
            )
            if campaign_status is None:
                raise ValueError(
                    f"campaign {normalized_campaign_id!r} does not exist; "
                    "an instructor must create it first"
                )
            if campaign_status != CampaignStatus.ACTIVE.value:
                raise ValueError(
                    f"campaign {normalized_campaign_id!r} is not active"
                )
            actor_role = await _actor_role(connection, actor_user_id)
            # source_baseline_version_id is provenance only — every condition
            # stores its own complete recipe snapshot, so a student may plan
            # from scratch without referencing any baseline.
            await _validate_baseline_version_for_condition(
                connection, source_baseline_version_id,
                actor_user_id=actor_user_id,
            )
            if connection.dialect.name == "postgresql":
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:series_id, 0))"),
                    {"series_id": normalized_campaign_id or "<unassigned>"},
                )
            condition = (
                experiments.c.campaign_id.is_(None)
                if normalized_campaign_id is None
                else experiments.c.campaign_id == normalized_campaign_id
            )
            next_version = int(
                await connection.scalar(
                    select(func.coalesce(func.max(experiments.c.series_version), 0) + 1)
                    .where(condition)
                )
                or 1
            )
            experiment_code = (
                f"{normalized_campaign_id or 'experiment'}-v{next_version}"
            )
            if len(experiment_code) > EXPERIMENT_CODE_MAX_LENGTH:
                raise ValueError(
                    f"experiment code must not exceed {EXPERIMENT_CODE_MAX_LENGTH} characters"
                )
            from ..services.catalog_service import list_device_layouts
            from ..services.legacy_adapter import materialize_legacy_conditions

            # The device-layout catalog is database-authoritative: an empty
            # catalog blocks experiment creation until an administrator
            # creates the layouts.
            db_layouts: list[DeviceLayout] = await list_device_layouts(connection)
            condition_specs = materialize_legacy_conditions(
                recipe_values,
                experiment_code,
                layouts=db_layouts,
                condition_plans=condition_plans,
            )
            if not condition_specs:
                raise ValueError(
                    "a complete device_recipe must materialize at least one condition"
                )
            roles = {ConditionRole(spec["role"]) for spec in condition_specs}
            plan_type = (
                "standalone"
                if roles == {ConditionRole.STANDALONE}
                else "comparative"
            )
            plan_status = PlanStatus.DRAFT.value
            result = await connection.execute(
                insert(experiments).values(
                    status=ExperimentStatus.SUGGESTED.value,
                    metrics={},
                    created_at=now,
                    updated_at=now,
                    campaign_id=normalized_campaign_id,
                    experiment_code=experiment_code,
                    series_version=next_version,
                    created_by_id=actor_user_id,
                    plan_type=plan_type,
                    plan_status=plan_status,
                )
            )
            experiment_id = _inserted_id(result)
            for spec in condition_specs:
                snapshot = validate_condition_snapshot(spec["recipe_snapshot"])
                layout = next(
                    (
                        item
                        for item in db_layouts
                        if item.code == spec["device_layout_code"]
                    ),
                    None,
                )
                if layout is None:
                    raise ValueError(
                        f"unknown device layout code: {spec['device_layout_code']!r}"
                    )
                count = int(spec["planned_substrate_count"])
                await connection.execute(
                    insert(experiment_conditions).values(
                        experiment_id=experiment_id,
                        role=ConditionRole(spec["role"]).value,
                        condition_code=str(spec["condition_code"]).strip(),
                        condition_name=str(spec["condition_name"]).strip(),
                        recipe_snapshot=snapshot,
                        recipe_schema_version=int(snapshot["schema_version"]),
                        canonical_hash=condition_canonical_hash(snapshot),
                        source_baseline_version_id=spec.get(
                            "source_baseline_version_id"
                        ) or source_baseline_version_id,
                        device_layout_code=layout.code,
                        device_layout_snapshot=layout_snapshot(layout),
                        planned_substrate_count=count,
                        expected_device_count=expected_device_count(count, layout),
                        requires_manual_review=bool(
                            spec.get("requires_manual_review", False)
                        ),
                        created_at=now,
                        created_by_id=actor_user_id,
                    )
                )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="experiment.create",
                entity_type="experiment",
                entity_id=str(experiment_id),
                details={"experiment_code": experiment_code},
                client_ip=client_ip,
            )
        return await self.get_experiment(experiment_id)

    async def get_experiment(
        self,
        experiment_id: int | None,
        *,
        owner_user_id: int | None = None,
    ) -> ExperimentRecord:
        if experiment_id is None:
            raise ValueError("experiment id is required")
        statement = (
            select(experiments)
            .where(experiments.c.id == experiment_id)
            .add_columns(_control_recipe_snapshot_subquery())
        )
        if owner_user_id is not None:
            statement = statement.where(experiments.c.created_by_id == owner_user_id)
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(statement)
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown experiment id: {experiment_id}")
        return _experiment_record(row)

    async def list_experiments(
        self,
        statuses: Iterable[ExperimentStatus] | None = None,
        *,
        owner_user_id: int | None = None,
    ) -> list[ExperimentRecord]:
        statement = (
            select(experiments)
            .where(_has_reconstructable_recipe_predicate())
            .order_by(experiments.c.id)
            .add_columns(_control_recipe_snapshot_subquery())
        )
        if owner_user_id is not None:
            statement = statement.where(experiments.c.created_by_id == owner_user_id)
        if statuses is not None:
            values = [item.value for item in statuses]
            if not values:
                return []
            statement = statement.where(experiments.c.status.in_(values))
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_experiment_record(row) for row in rows]

    async def list_experiments_for_campaign(
        self,
        campaign_id: str | None,
        statuses: Iterable[ExperimentStatus] | None = None,
    ) -> list[ExperimentRecord]:
        normalized = _normalize_campaign_id(campaign_id)
        condition = (
            experiments.c.campaign_id.is_(None)
            if normalized is None
            else experiments.c.campaign_id == normalized
        )
        statement = (
            select(experiments)
            .where(condition, _has_reconstructable_recipe_predicate())
            .order_by(experiments.c.id)
            .add_columns(_control_recipe_snapshot_subquery())
        )
        if statuses is not None:
            values = [item.value for item in statuses]
            if not values:
                return []
            statement = statement.where(experiments.c.status.in_(values))
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_experiment_record(row) for row in rows]

    async def next_series_versions(self) -> dict[str, int]:
        statement = (
            select(
                experiments.c.campaign_id,
                (func.coalesce(func.max(experiments.c.series_version), 0) + 1).label(
                    "next_version"
                ),
            )
            .where(experiments.c.campaign_id.is_not(None))
            .group_by(experiments.c.campaign_id)
        )
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return {str(row["campaign_id"]): int(row["next_version"]) for row in rows}

    async def complete_experiment(
        self,
        experiment_id: int,
        metrics: Mapping[str, float],
        *,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> ExperimentRecord:
        normalized_metrics = _normalize_metrics(metrics)
        if "pce" not in normalized_metrics:
            raise ValueError("completed experiments must include the primary 'pce' metric")
        async with self.database.begin() as connection:
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
                action="experiment.complete",
                entity_type="experiment",
                entity_id=str(experiment_id),
                details={"metrics": normalized_metrics},
                client_ip=client_ip,
            )
        return await self.get_experiment(experiment_id)
