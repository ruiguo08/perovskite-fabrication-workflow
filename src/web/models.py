"""Web-layer request and response models."""

from __future__ import annotations

import math
from typing import Any, Literal

from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from perovskite_bo.device_recipe import (
    DeviceLayer,
    DeviceRecipe,
    PerovskiteDepositionProcess,
)

from .database import (
    BASELINE_NAME_MAX_LENGTH,
    CAMPAIGN_CODE_MAX_LENGTH,
    CAMPAIGN_ID_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    LAYER_PRESET_NAME_MAX_LENGTH,
    MATERIAL_CAS_NUMBER_MAX_LENGTH,
    MATERIAL_CATALOG_NUMBER_MAX_LENGTH,
    MATERIAL_FORMULA_MAX_LENGTH,
    MATERIAL_NAME_MAX_LENGTH,
    MATERIAL_VENDOR_MAX_LENGTH,
)
from .condition_snapshot import ConditionRecipeSnapshot
from .device_layouts import LAYOUT_CODE_MAX_LENGTH


class ApiModel(BaseModel):
    """Strict base model for documented REST request and response schemas."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_non_finite_numbers(cls, values: Any) -> Any:
        """JSON documents must remain valid for PostgreSQL JSONB and exports."""

        def visit(value: Any) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("numeric values must be finite")
            if isinstance(value, dict):
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    visit(nested)

        visit(values)
        return values


class LoginRequest(ApiModel):
    """JSON login payload using the existing login-CSRF mechanism."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    login_csrf: str = Field(..., min_length=1, max_length=128)


class SessionInfoResponse(ApiModel):
    """Current authenticated session and CSRF availability for the SPA."""

    id: int
    username: str
    display_name: str
    role: str
    csrf_available: bool


class UserCreatePayload(ApiModel):
    """Administrator request for a new local account."""

    username: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(
        ..., min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH
    )
    password: str = Field(..., min_length=1, max_length=128)
    role: Literal["student", "instructor", "administrator"]


class UserUpdatePayload(ApiModel):
    """Administrator replacement of one account's access settings."""

    role: Literal["student", "instructor", "administrator"]
    is_active: bool


class UserPasswordResetPayload(ApiModel):
    """Administrator request to replace one account password."""

    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(ApiModel):
    """Non-secret account metadata returned to administrators."""

    id: int
    username: str
    display_name: str
    role: Literal["student", "instructor", "administrator"]
    is_active: bool
    locked_until: str | None
    last_login_at: str | None
    password_changed_at: str
    created_at: str
    updated_at: str


class DepositionRecipePayload(ApiModel):
    """Typed REST representation of the canonical deposition recipe."""

    spin_cast_rpm: int
    spin_cast_seconds: int
    spin_cast_acceleration_rpm_per_s: int
    spin_spread_rpm: int | None = None
    spin_spread_seconds: int | None = None
    spin_spread_acceleration_rpm_per_s: int | None = None
    spin_thin_rpm: int | None = None
    spin_thin_seconds: int | None = None
    spin_thin_acceleration_rpm_per_s: int | None = None
    spin_stage4_rpm: int | None = None
    spin_stage4_seconds: int | None = None
    spin_stage4_acceleration_rpm_per_s: int | None = None
    vcd_stage1_valve: str
    vcd_stage1_pressure_pa: int | None = None
    vcd_stage1_seconds: int
    vcd_stage2_valve: str | None = None
    vcd_stage2_pressure_pa: int | None = None
    vcd_stage2_seconds: int | None = None
    vcd_stage3_valve: str | None = None
    vcd_stage3_pressure_pa: int | None = None
    vcd_stage3_seconds: int | None = None
    vcd_stage4_valve: str | None = None
    vcd_stage4_pressure_pa: int | None = None
    vcd_stage4_seconds: int | None = None
    vcd_stage5_valve: str | None = None
    vcd_stage5_pressure_pa: int | None = None
    vcd_stage5_seconds: int | None = None
    gas_backfill_stage1_gas: str | None = None
    gas_backfill_stage1_flow_sccm: float | None = None
    gas_backfill_stage1_target_pressure_pa: int | None = None
    gas_backfill_stage1_hold_seconds: int | None = None
    gas_backfill_stage2_gas: str | None = None
    gas_backfill_stage2_flow_sccm: float | None = None
    gas_backfill_stage2_target_pressure_pa: int | None = None
    gas_backfill_stage2_hold_seconds: int | None = None
    gas_backfill_stage3_gas: str | None = None
    gas_backfill_stage3_flow_sccm: float | None = None
    gas_backfill_stage3_target_pressure_pa: int | None = None
    gas_backfill_stage3_hold_seconds: int | None = None
    gas_backfill_stage4_gas: str | None = None
    gas_backfill_stage4_flow_sccm: float | None = None
    gas_backfill_stage4_target_pressure_pa: int | None = None
    gas_backfill_stage4_hold_seconds: int | None = None
    gas_backfill_stage5_gas: str | None = None
    gas_backfill_stage5_flow_sccm: float | None = None
    gas_backfill_stage5_target_pressure_pa: int | None = None
    gas_backfill_stage5_hold_seconds: int | None = None
    vcd_step_sequence: list[str] | None = None
    anneal_stage1_temperature_c: int
    anneal_stage1_seconds: int
    anneal_stage2_temperature_c: int | None = None
    anneal_stage2_seconds: int | None = None
    device_stack: str | None = None
    fabrication_context: None = None
    # Derived from the control condition snapshot, which deliberately carries
    # no group metadata; the authoritative stack detail lives in the
    # condition snapshots exposed alongside this payload.
    device_recipe: DeviceRecipe | None = None


class DeviceLayoutCreatePayload(ApiModel):
    """One new immutable device-layout version (administrator-managed)."""

    code: str = Field(min_length=1, max_length=LAYOUT_CODE_MAX_LENGTH)
    version: int = Field(ge=1)
    substrate_width_mm: Decimal = Field(gt=0)
    substrate_length_mm: Decimal = Field(gt=0)
    devices_per_substrate: int = Field(ge=1)
    device_active_area_cm2: Decimal = Field(gt=0)
    total_active_area_cm2: Decimal = Field(gt=0)
    description: str = Field(min_length=1, max_length=500)


class ConditionPlanPayload(ApiModel):
    """Explicit layout and replicate planning for one recipe group."""

    group_id: str = Field(..., min_length=1, max_length=80)
    role: Literal["control", "target", "standalone"]
    device_layout_code: str = Field(..., min_length=1, max_length=40)
    planned_substrate_count: int = Field(..., ge=1)


class RecipePayload(ApiModel):
    """REST payload for creating a reconstructible fabrication experiment."""

    recipe: DepositionRecipePayload = Field(
        ...,
        description="Canonical deposition recipe with the complete device configuration.",
    )

    @model_validator(mode="after")
    def _require_complete_device(self) -> "RecipePayload":
        # Response representations tolerate a derived recipe without the
        # group-scoped device block; creation requests never may.
        if self.recipe.device_recipe is None:
            raise ValueError(
                "a complete device_recipe is required; baselines and presets must be "
                "expanded before an experiment is saved"
            )
        return self
    campaign_id: str | None = Field(
        default=None,
        max_length=CAMPAIGN_ID_MAX_LENGTH,
        description="Independent optimization campaign; defaults to the app campaign.",
    )
    source_baseline_version_id: int | None = Field(
        default=None,
        gt=0,
        description="Immutable baseline revision used as the plan baseline.",
    )
    condition_plans: list[ConditionPlanPayload] | None = Field(
        default=None,
        min_length=1,
        max_length=21,
        description=(
            "Explicit device layout and substrate count for every condition. "
            "Legacy clients may omit this field and use conservative inference."
        ),
    )


class ExperimentResponse(ApiModel):
    """REST representation of a persisted experiment."""

    id: int
    recipe: DepositionRecipePayload
    status: str
    metrics: dict[str, float]
    failure_reason: str | None
    created_at: str
    updated_at: str
    campaign_id: str | None = None
    experiment_code: str | None = None
    series_version: int | None = None
    plan_type: str | None = None
    plan_status: str | None = None
    device_summary: str | None = None


class ResultSummaryResponse(ApiModel):
    """Audit metadata for one characterization result in a plan detail."""

    id: int
    experiment_id: int
    fabrication_batch_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    group_assignment: str
    metrics: dict[str, float]
    analysis_schema_version: int
    created_at: str


class UploadedResultResponse(ApiModel):
    """REST representation of an uploaded characterization result file."""

    id: int
    experiment_id: int
    fabrication_batch_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    analysis_schema_version: int
    created_at: str
    metrics: dict[str, float]


class ResultAssignmentGroupResponse(ApiModel):
    """One frozen batch condition offered as a result-assignment target."""

    group_id: str
    batch_condition_id: int
    condition_code: str
    kind: str
    name: str


class ResultAssignmentRowResponse(ApiModel):
    """One per-device result assignment row (provenance/detail read model)."""

    id: int
    result_file_id: int
    analysis_device_id: str
    analysis_substrate_id: str
    instrument_label: str
    fabrication_device_id: int | None
    device_code: str | None
    device_mark: str | None
    substrate_id: int | None
    substrate_code: str | None
    substrate_mark: str | None
    batch_condition_id: int
    source_condition_id: int
    condition_code: str
    condition_name: str
    created_at: str


class DeviceScanRecord(ApiModel):
    """One stored scan of a physical device (a single trace, verbatim)."""

    result_file_id: int
    filename: str
    uploaded_at: str
    trace_id: str
    direction: str
    valid: bool
    measured_at: str | None
    metrics: dict[str, float] | None
    metric_source: str | None
    error: str | None
    points: list[list[float]]


class RepresentativeScan(ApiModel):
    """The scan a device's direction currently displays, with provenance."""

    result_file_id: int
    trace_id: str
    measured_at: str | None
    metrics: dict[str, float]
    metric_source: str | None
    from_user_selection: bool


class DeviceJvScansResponse(ApiModel):
    """Complete scan history and per-direction representatives of one device."""

    fabrication_device_id: int
    device_code: str
    device_mark: str | None
    device_ordinal: int
    substrate_id: int
    substrate_code: str
    scans: list[DeviceScanRecord]
    representative: dict[str, RepresentativeScan | None]
    scan_counts: dict[str, int]


class RepresentativeScanPayload(ApiModel):
    direction: Literal["forward", "reverse"]
    result_file_id: int = Field(..., gt=0)
    trace_id: str = Field(..., min_length=1, max_length=80)


class ResultDetailResponse(ApiModel):
    """Complete provenance, analysis, and assignment state for one result file."""

    id: int
    experiment_id: int
    fabrication_batch_id: int
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    group_assignment: str
    metrics: dict[str, float]
    analysis: dict[str, Any]
    analysis_schema_version: int
    created_by_id: int | None
    created_at: str
    groups: list[ResultAssignmentGroupResponse]
    assignments: list[ResultAssignmentRowResponse]


class ResultAssignmentItem(ApiModel):
    """Mapping of one parsed analysis substrate to one frozen batch condition.

    ``analysis_substrate_id`` comes from the parsed JV analysis (the instrument
    label) and is stored in a Text column, so no fixed length limit applies.
    """

    analysis_substrate_id: str = Field(..., min_length=1)
    batch_condition_id: int = Field(..., gt=0)


class ResultDeviceExclusion(ApiModel):
    """One parsed analysis device excluded from statistics with a reason.

    Exclusion never deletes the device, its traces, or its assignment; it only
    flags the analysis JSON so group statistics and comparisons skip it.
    """

    analysis_device_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=200)


class ResultAssignmentsPayload(ApiModel):
    """Complete assignment mapping for every parsed analysis substrate."""

    assignments: list[ResultAssignmentItem] = Field(..., min_length=1)
    exclusions: list[ResultDeviceExclusion] = Field(default_factory=list)
    correction_reason: str | None = Field(default=None, max_length=500)


class BaselinePayload(ApiModel):
    """REST payload for saving a named baseline."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=BASELINE_NAME_MAX_LENGTH,
        description="Name for the baseline",
    )
    device_recipe: DeviceRecipe = Field(
        ..., description="Complete device recipe to save as a baseline"
    )
    deposition_process: PerovskiteDepositionProcess = Field(
        ...,
        description="Control perovskite spin/VCD/annealing process to store with the baseline",
    )


class BaselineResponse(ApiModel):
    """REST representation of a saved baseline."""

    id: int
    name: str
    status: str = "active"
    scope: Literal["personal", "shared"] = "personal"
    owner_user_id: int | None = None
    owner_display_name: str | None = None
    promoted_by_user_id: int | None = None
    promoted_by_display_name: str | None = None
    promoted_at: str | None = None
    promotion_note: str | None = None
    promoted_version_id: int | None = None
    device_recipe: DeviceRecipe
    deposition_process: PerovskiteDepositionProcess | None = None
    current_revision_number: int | None = None
    current_version_id: int | None = None
    canonical_hash: str | None = None
    created_at: str
    updated_at: str


class BaselinePromotePayload(ApiModel):
    """Instructor or administrator request to promote a Personal baseline."""

    note: str | None = Field(
        default=None,
        max_length=500,
        description="Optional promotion note recorded in promotion provenance",
    )


class LayerPresetPayload(ApiModel):
    """Complete editable values for one user-owned layer preset."""

    name: str = Field(..., min_length=1, max_length=LAYER_PRESET_NAME_MAX_LENGTH)
    layer: DeviceLayer
    deposition_process: PerovskiteDepositionProcess | None = None
    scope: Literal["personal", "shared"] = "personal"

    @model_validator(mode="after")
    def validate_perovskite_process(self) -> LayerPresetPayload:
        if self.layer.layer_type == "perovskite" and self.deposition_process is None:
            raise ValueError("a perovskite layer preset requires a deposition process")
        if self.layer.layer_type != "perovskite" and self.deposition_process is not None:
            raise ValueError(
                "only a perovskite layer preset may include a deposition process"
            )
        return self


class LayerPresetResponse(ApiModel):
    """Current immutable revision of one user-owned layer preset."""

    id: int
    preset_key: str
    name: str
    status: str
    scope: Literal["personal", "shared"]
    layer: DeviceLayer
    deposition_process: PerovskiteDepositionProcess | None = None
    current_revision_number: int
    current_version_id: int
    canonical_hash: str
    created_at: str
    updated_at: str


class BaselineVersionResponse(ApiModel):
    """One immutable revision of a visible baseline."""

    id: int
    baseline_id: int
    revision_number: int
    recipe_schema_version: int
    device_recipe: DeviceRecipe
    deposition_process: PerovskiteDepositionProcess
    canonical_hash: str
    change_note: str
    created_by_id: int | None
    created_at: str


class LayerPresetVersionResponse(ApiModel):
    """One immutable revision of a visible layer preset."""

    id: int
    layer_preset_id: int
    revision_number: int
    preset_schema_version: int
    layer: DeviceLayer
    deposition_process: PerovskiteDepositionProcess | None = None
    canonical_hash: str
    created_by_id: int | None
    created_at: str


class MaterialCreatePayload(ApiModel):
    """Material proposal submitted to the shared reusable directory."""

    category: Literal["substrate", "chemical", "solvent", "gas", "other"]
    name: str = Field(..., min_length=1, max_length=MATERIAL_NAME_MAX_LENGTH)
    formula: str = Field(default="", max_length=MATERIAL_FORMULA_MAX_LENGTH)
    cas_number: str = Field(default="", max_length=MATERIAL_CAS_NUMBER_MAX_LENGTH)
    specification: dict[str, Any] = Field(default_factory=dict)


class MaterialUpdatePayload(ApiModel):
    """Instructor or administrator maintenance for a shared material."""

    name: str | None = Field(default=None, min_length=1, max_length=MATERIAL_NAME_MAX_LENGTH)
    formula: str | None = Field(default=None, max_length=MATERIAL_FORMULA_MAX_LENGTH)
    cas_number: str | None = Field(default=None, max_length=MATERIAL_CAS_NUMBER_MAX_LENGTH)
    specification: dict[str, Any] | None = None
    status: Literal["pending", "active", "inactive"] | None = None


class MaterialProductCreatePayload(ApiModel):
    """Supplier product proposal for a material in the shared directory."""

    vendor: str = Field(..., min_length=1, max_length=MATERIAL_VENDOR_MAX_LENGTH)
    catalog_number: str = Field(
        ..., min_length=1, max_length=MATERIAL_CATALOG_NUMBER_MAX_LENGTH
    )
    specification: dict[str, Any] = Field(default_factory=dict)


class MaterialProductUpdatePayload(ApiModel):
    """Instructor or administrator maintenance for a supplier product."""

    vendor: str | None = Field(default=None, min_length=1, max_length=MATERIAL_VENDOR_MAX_LENGTH)
    catalog_number: str | None = Field(
        default=None, min_length=1, max_length=MATERIAL_CATALOG_NUMBER_MAX_LENGTH
    )
    specification: dict[str, Any] | None = None
    status: Literal["pending", "active", "inactive"] | None = None


class MaterialProductResponse(ApiModel):
    """One reusable supplier product linked to a material."""

    id: int
    vendor: str
    catalog_number: str
    specification: dict[str, Any]
    status: str
    created_at: str
    updated_at: str


class MaterialResponse(ApiModel):
    """One material and its visible supplier-product records."""

    id: int
    category: str
    name: str
    formula: str
    cas_number: str
    specification: dict[str, Any]
    status: str
    products: list[MaterialProductResponse]
    created_at: str
    updated_at: str


class CampaignCreatePayload(ApiModel):
    """REST payload for creating a campaign (instructor/administrator only)."""

    code: str = Field(..., min_length=1, max_length=CAMPAIGN_CODE_MAX_LENGTH)
    display_name: str = Field(..., min_length=1, max_length=120)
    description: str = ""


class CampaignUpdatePayload(ApiModel):
    """REST payload for updating campaign description and status."""

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    status: str | None = Field(
        default=None,
        description="One of: active, closed, archived",
    )


class CampaignResponse(ApiModel):
    """REST representation of a campaign."""

    id: int
    code: str
    display_name: str
    description: str
    status: str
    created_at: str
    updated_at: str
    closed_at: str | None = None


class ConditionCreatePayload(ApiModel):
    role: Literal["control", "target", "standalone"]
    condition_name: str = Field(..., min_length=1, max_length=120)
    recipe_snapshot: ConditionRecipeSnapshot
    source_baseline_version_id: int | None = Field(default=None, gt=0)
    device_layout_code: str = Field(..., min_length=1, max_length=40)
    planned_substrate_count: int = Field(..., ge=1)


class ConditionUpdatePayload(ApiModel):
    condition_name: str = Field(..., min_length=1, max_length=120)
    recipe_snapshot: ConditionRecipeSnapshot
    source_baseline_version_id: int | None = Field(default=None, gt=0)
    device_layout_code: str = Field(..., min_length=1, max_length=40)
    planned_substrate_count: int = Field(..., ge=1)


class ConditionResponse(ApiModel):
    id: int
    experiment_id: int
    role: str
    condition_code: str
    condition_name: str
    recipe_snapshot: dict[str, Any]
    recipe_schema_version: int
    canonical_hash: str
    source_baseline_version_id: int | None
    device_layout_code: str
    device_layout_snapshot: dict[str, Any]
    planned_substrate_count: int
    expected_device_count: int
    requires_manual_review: bool
    created_at: str


class SubstrateExceptionCreatePayload(ApiModel):
    requested_count: int = Field(..., ge=1, le=2)
    reason: str = Field(..., min_length=1, max_length=2000)


class SubstrateExceptionDecisionPayload(ApiModel):
    decision: Literal["approved", "rejected"]
    decision_note: str = Field(default="", max_length=2000)


class SubstrateExceptionResponse(ApiModel):
    id: int
    condition_id: int
    requested_count: int
    reason: str
    requested_by_id: int | None
    requested_at: str
    decision: str
    decided_by_id: int | None
    decided_at: str | None
    decision_note: str
    approved_condition_hash: str | None


class PlanStatusUpdatePayload(ApiModel):
    status: Literal[
        "pending_approval",
        "approved",
        "released",
        "in_progress",
        "completed",
        "cancelled",
    ]


# ------------------------------------------------------------------
# Fabrication Batch models
# ------------------------------------------------------------------

class FabricationBatchCreatePayload(ApiModel):
    notes: str = Field(default="", max_length=2000)


class CompletionShortfallDeviationPayload(ApiModel):
    """Narrow completion-only deviation: just the condition and the reason.

    Category, severity, planned/actual values, and the recording user are set
    by the server from authoritative batch data inside the completion
    transaction.
    """

    condition_id: int
    description: str = Field(min_length=1, max_length=5000)


class FabricationBatchStatusUpdatePayload(ApiModel):
    status: Literal["ready", "in_progress", "completed", "cancelled"]
    actual_substrate_counts: dict[str, int] | None = None
    shortfall_deviations: list[CompletionShortfallDeviationPayload] | None = None


class FabricationBatchResponse(ApiModel):
    id: int
    experiment_id: int
    batch_number: int
    batch_code: str
    status: str
    condition_set_hash: str
    notes: str
    created_by_id: int | None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None


class ExperimentDetailResponse(ApiModel):
    """Complete planning view for one authorized experiment."""

    experiment: ExperimentResponse
    conditions: list[ConditionResponse]
    substrate_exceptions: list[SubstrateExceptionResponse]
    fabrication_batches: list[FabricationBatchResponse]
    results: list[ResultSummaryResponse]


class FrozenBatchConditionResponse(ApiModel):
    id: int
    fabrication_batch_id: int
    source_condition_id: int
    condition_code: str
    condition_name: str
    role: str
    source_condition_hash: str
    recipe_snapshot: dict[str, Any]
    recipe_schema_version: int
    device_layout_code: str
    device_layout_snapshot: dict[str, Any]
    planned_substrate_count: int
    expected_device_count: int
    actual_substrate_count: int | None


class FabricationSubstrateResponse(ApiModel):
    id: int
    batch_condition_id: int
    substrate_ordinal: int
    substrate_code: str
    substrate_mark: str | None
    status: str
    notes: str
    created_at: str
    updated_at: str


class FabricationDeviceResponse(ApiModel):
    id: int
    substrate_id: int
    device_ordinal: int
    device_code: str
    device_mark: str | None
    device_active_area_cm2: str
    status: str
    notes: str
    created_at: str
    updated_at: str


class SolutionPreparationCreatePayload(ApiModel):
    planned_solution_snapshot: dict[str, Any]
    notes: str = Field(default="", max_length=2000)


class SolutionPreparationUpdatePayload(ApiModel):
    status: Literal["preparing", "ready", "consumed", "discarded"] | None = None
    actual_solution_snapshot: dict[str, Any] | None = None
    actual_matches_planned: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class SolutionPreparationResponse(ApiModel):
    id: int
    fabrication_batch_id: int
    preparation_code: str
    status: str
    planned_solution_snapshot: dict[str, Any]
    planned_snapshot_schema_version: int
    planned_canonical_hash: str
    actual_solution_snapshot: dict[str, Any] | None
    actual_snapshot_schema_version: int | None
    actual_canonical_hash: str | None
    actual_recording_mode: str | None
    prepared_by_id: int | None
    prepared_at: str | None
    completed_at: str | None
    notes: str
    created_at: str
    updated_at: str


class MembershipSplitPayload(ApiModel):
    member_ids: list[int] = Field(..., min_length=1)
    notes: str = Field(default="", max_length=2000)


class MembershipMergePayload(ApiModel):
    source_id: int = Field(..., gt=0)


class SolutionPreparationUseResponse(ApiModel):
    id: int
    solution_preparation_id: int
    batch_condition_id: int
    layer_ordinal: int
    layer_role: str
    layer_type: str
    layer_snapshot_hash: str


class ProcessExecutionCreatePayload(ApiModel):
    method: Literal["spin_coating", "annealing", "vcd", "thermal_evaporation", "ald", "sputtering"]
    layer_role: str = Field(..., min_length=1, max_length=80)
    layer_type: str = Field(..., min_length=1, max_length=80)
    layer_name: str = Field(..., min_length=1, max_length=120)
    planned_process_snapshot: dict[str, Any]
    is_shared: bool = False
    notes: str = Field(default="", max_length=2000)


class ProcessExecutionUpdatePayload(ApiModel):
    status: Literal["ready", "running", "completed", "failed", "cancelled"] | None = None
    actual_process_snapshot: dict[str, Any] | None = None
    actual_matches_planned: bool = False
    equipment_identifier: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class ProcessExecutionResponse(ApiModel):
    id: int
    fabrication_batch_id: int
    execution_code: str
    method: str
    layer_role: str
    layer_type: str
    layer_name: str
    status: str
    is_shared: bool
    planned_process_snapshot: dict[str, Any]
    planned_snapshot_schema_version: int
    planned_canonical_hash: str
    actual_process_snapshot: dict[str, Any] | None
    actual_snapshot_schema_version: int | None
    actual_canonical_hash: str | None
    actual_recording_mode: str | None
    equipment_identifier: str | None
    executed_by_id: int | None
    started_at: str | None
    completed_at: str | None
    notes: str
    created_at: str
    updated_at: str


class ProcessExecutionMemberResponse(ApiModel):
    id: int
    process_execution_id: int
    substrate_id: int
    batch_condition_id: int
    layer_ordinal: int
    layer_snapshot_hash: str


class DeviationCreatePayload(ApiModel):
    category: Literal["process", "material", "equipment", "substrate", "device", "operator", "other"]
    severity: Literal["info", "warning", "error", "critical"]
    deviation_type: Literal["general", "fabrication_shortfall", "measurement_shortfall"] = "general"
    description: str = Field(..., min_length=1, max_length=5000)
    planned_value: dict[str, Any] | None = None
    actual_value: dict[str, Any] | None = None
    supersedes_deviation_id: int | None = None
    solution_preparation_id: int | None = None
    process_execution_id: int | None = None
    substrate_id: int | None = None
    device_id: int | None = None
    condition_id: int | None = None

    @model_validator(mode="after")
    def require_at_most_one_specific_target(self) -> "DeviationCreatePayload":
        targets = (
            self.solution_preparation_id,
            self.process_execution_id,
            self.substrate_id,
            self.device_id,
            self.condition_id,
        )
        if sum(value is not None for value in targets) > 1:
            raise ValueError(
                "a deviation may target the batch or one specific execution entity"
            )
        return self


class DeviationResponse(ApiModel):
    id: int
    fabrication_batch_id: int
    category: str
    severity: str
    deviation_type: str
    description: str
    planned_value: dict[str, Any] | None
    actual_value: dict[str, Any] | None
    recorded_by_id: int | None
    recorded_at: str
    supersedes_deviation_id: int | None
    solution_preparation_id: int | None
    process_execution_id: int | None
    substrate_id: int | None
    device_id: int | None
    condition_id: int | None
    created_at: str


class FabricationBatchListItemResponse(ApiModel):
    """One role-scoped fabrication batch summary with its experiment code."""

    id: int
    experiment_id: int
    experiment_code: str | None
    batch_number: int
    batch_code: str
    status: str
    condition_set_hash: str
    notes: str
    created_by_id: int | None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None


class ResultListItemResponse(ApiModel):
    """One role-scoped result summary with experiment and batch codes."""

    id: int
    experiment_id: int
    experiment_code: str | None
    fabrication_batch_id: int
    batch_code: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    group_assignment: str
    metrics: dict[str, float]
    analysis_schema_version: int
    created_at: str


class EditorConfigResponse(ApiModel):
    """Server-authoritative editor bounds for snapshot forms."""

    vcd_valves: list[str]
    max_solid_chemicals: int
    max_solvents: int


class RunSheetPreparationResponse(ApiModel):
    """One solution preparation with its membership uses."""

    preparation: SolutionPreparationResponse
    uses: list[SolutionPreparationUseResponse]


class RunSheetExecutionResponse(ApiModel):
    """One process execution with its membership members."""

    execution: ProcessExecutionResponse
    members: list[ProcessExecutionMemberResponse]


class RunSheetResponse(ApiModel):
    """Complete aggregated read model for the fabrication batch run sheet."""

    batch: FabricationBatchResponse
    conditions: list[FrozenBatchConditionResponse]
    substrates: list[FabricationSubstrateResponse]
    devices: list[FabricationDeviceResponse]
    preparations: list[RunSheetPreparationResponse]
    executions: list[RunSheetExecutionResponse]
    deviations: list[DeviationResponse]
    editor_config: EditorConfigResponse


class RecordAsPlannedResponse(ApiModel):
    """Counts of run-sheet rows marked as matching the plan by a bulk record."""

    preparations: int
    executions: int
