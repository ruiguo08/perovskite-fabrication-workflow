"""Shared support for the domain route modules.

Cross-domain access helpers (the fixed no-existence-leak 404 semantics),
response builders, HTTP-agnostic constants, and the OperationError-to-HTTP
mapper. Domain modules star-import this module; everything they reference is
listed in ``__all__``.
"""


from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from perovskite_bo import (
    MAX_SOLID_CHEMICALS,
    MAX_SOLVENTS,
    VCD_VALVES,
    DepositionRecipe,
    ExperimentRecord,
    validate_deposition_process,
    validate_device_recipe,
)

from ..jv_parser import (
    _flat_metrics_from_analysis,
    assign_substrates_to_groups,
    parse_jv_analysis,
)
from ..plan_export import (
    build_batch_export,
    build_plan_export,
    canonical_batch_json,
    canonical_plan_json,
    render_batch_pdf,
    render_plan_pdf,
)
from ..auth import AuthContext, require_csrf, require_role, require_user
from ..models import (
    CampaignCreatePayload,
    CampaignResponse,
    CampaignUpdatePayload,
    ConditionCreatePayload,
    ConditionResponse,
    ConditionUpdatePayload,
    ExperimentDetailResponse,
    ExperimentResponse,
    PlanStatusUpdatePayload,
    RecipePayload,
    BaselinePayload,
    BaselinePromotePayload,
    BaselineResponse,
    BaselineVersionResponse,
    LayerPresetPayload,
    LayerPresetResponse,
    LayerPresetVersionResponse,
    MaterialCreatePayload,
    MaterialProductCreatePayload,
    MaterialProductResponse,
    MaterialProductUpdatePayload,
    MaterialResponse,
    MaterialUpdatePayload,
    SubstrateExceptionCreatePayload,
    SubstrateExceptionDecisionPayload,
    SubstrateExceptionResponse,
    UploadedResultResponse,
    FabricationBatchCreatePayload,
    FabricationBatchStatusUpdatePayload,
    FabricationBatchResponse,
    FrozenBatchConditionResponse,
    FabricationSubstrateResponse,
    FabricationDeviceResponse,
    SolutionPreparationCreatePayload,
    SolutionPreparationUpdatePayload,
    SolutionPreparationResponse,
    SolutionPreparationUseResponse,
    MembershipSplitPayload,
    MembershipMergePayload,
    ProcessExecutionCreatePayload,
    ProcessExecutionUpdatePayload,
    ProcessExecutionResponse,
    ProcessExecutionMemberResponse,
    ResultSummaryResponse,
    DeviationCreatePayload,
    DeviationResponse,
    ResultDetailResponse,
    ResultAssignmentGroupResponse,
    ResultAssignmentRowResponse,
    ResultAssignmentItem,
    ResultAssignmentsPayload,
    FabricationBatchListItemResponse,
    ResultListItemResponse,
    DeviceLayoutCreatePayload,
    EditorConfigResponse,
    RecordAsPlannedResponse,
    RunSheetPreparationResponse,
    RunSheetExecutionResponse,
    RunSheetResponse,
)
from ..operations.errors import (
    AccessDenied,
    InvalidInput,
    OperationError,
    RecordNotFound,
    StateConflict,
)
from ..operations.batch_lifecycle import update_batch_status
from ..operations.result_assignment import (
    ResultAssignmentInput,
    ResultExclusionInput,
    save_result_analysis,
)
from ..repository import (
    BatchStatus,
    CampaignStatus,
    ConditionRole,
    DeviationSeverity,
    ExceptionDecision,
    ExecutionStatus,
    PlanStatus,
    PreparationStatus,
    UserRole,
    WebRepository,
)
from ..services.catalog_service import create_device_layout, list_device_layouts

MAX_RESULT_FILE_BYTES = 10 * 1024 * 1024
_RESULT_READ_CHUNK_BYTES = 1024 * 1024
_ALLOWED_RESULT_CONTENT_TYPES = frozenset(
    {
        "application/csv",
        "application/octet-stream",
        "application/vnd.ms-excel",
        "text/csv",
        "text/plain",
    }
)

async def _condition_for_actor(
    repository: WebRepository,
    condition_id: int,
    auth_context: AuthContext,
) -> Any:
    try:
        condition = await repository.get_condition(condition_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    await _get_record_or_404(
        repository, condition.experiment_id, auth_context
    )
    return condition


async def _batch_for_actor_or_404(
    repository: WebRepository,
    batch_id: int,
    auth_context: AuthContext,
) -> Any:
    # A nonexistent batch and a batch the actor cannot access return the
    # same fixed 404 body: the KeyError texts differ ("unknown fabrication
    # batch id: N" vs "unknown experiment id: N") and would let a client
    # probe for batch existence.
    try:
        batch = await repository.get_fabrication_batch(batch_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="fabrication batch not found",
        ) from error
    try:
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
    except HTTPException as error:
        if error.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="fabrication batch not found",
            ) from error
        raise
    return batch


async def _result_for_actor_or_404(
    repository: WebRepository,
    file_id: int,
    auth_context: AuthContext,
) -> dict[str, Any]:
    try:
        result = await repository.get_result(file_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    await _get_record_or_404(repository, int(result["experiment_id"]), auth_context)
    return result


async def _result_detail_response(
    repository: WebRepository,
    result: dict[str, Any],
) -> ResultDetailResponse:
    groups = _batch_result_groups(
        await repository.get_fabrication_batch_conditions(
            int(result["fabrication_batch_id"])
        )
    )
    assignments = await repository.list_result_device_assignments(int(result["id"]))
    return ResultDetailResponse(
        id=result["id"],
        experiment_id=result["experiment_id"],
        fabrication_batch_id=result["fabrication_batch_id"],
        filename=result["filename"],
        content_type=result["content_type"],
        size_bytes=result["size_bytes"],
        sha256=result["sha256"],
        group_assignment=result["group_assignment"],
        metrics=result["metrics"],
        analysis=result["analysis"],
        analysis_schema_version=result["analysis_schema_version"],
        created_by_id=result["created_by_id"],
        created_at=result["created_at"],
        groups=[ResultAssignmentGroupResponse(**group) for group in groups],
        assignments=[
            _result_assignment_row_response(row) for row in assignments
        ],
    )


def _result_assignment_row_response(
    record: dict[str, Any],
) -> ResultAssignmentRowResponse:
    return ResultAssignmentRowResponse(
        id=int(record["id"]),
        result_file_id=int(record["result_file_id"]),
        analysis_device_id=str(record["analysis_device_id"]),
        analysis_substrate_id=str(record["analysis_substrate_id"]),
        instrument_label=str(record["instrument_label"]),
        fabrication_device_id=(
            int(record["fabrication_device_id"])
            if record["fabrication_device_id"] is not None
            else None
        ),
        device_code=record["device_code"],
        device_mark=record["device_mark"],
        substrate_id=record["substrate_id"],
        substrate_code=record["substrate_code"],
        substrate_mark=record["substrate_mark"],
        batch_condition_id=int(record["batch_condition_id"]),
        source_condition_id=int(record["source_condition_id"]),
        condition_code=str(record["condition_code"]),
        condition_name=str(record["condition_name"]),
        created_at=record["created_at"].isoformat(),
    )


def _result_list_item_response(record: dict[str, Any]) -> ResultListItemResponse:
    return ResultListItemResponse(
        id=record["id"],
        experiment_id=record["experiment_id"],
        experiment_code=record["experiment_code"],
        fabrication_batch_id=record["fabrication_batch_id"],
        batch_code=record["batch_code"],
        filename=record["filename"],
        content_type=record["content_type"],
        size_bytes=record["size_bytes"],
        sha256=record["sha256"],
        group_assignment=record["group_assignment"],
        metrics=record["metrics"],
        analysis_schema_version=record["analysis_schema_version"],
        created_at=record["created_at"],
    )


def _fabrication_batch_list_item_response(
    record: dict[str, Any],
) -> FabricationBatchListItemResponse:
    return FabricationBatchListItemResponse(
        id=record["id"],
        experiment_id=record["experiment_id"],
        experiment_code=record["experiment_code"],
        batch_number=record["batch_number"],
        batch_code=record["batch_code"],
        status=record["status"],
        condition_set_hash=record["condition_set_hash"],
        notes=record["notes"],
        created_by_id=record["created_by_id"],
        created_at=record["created_at"],
        updated_at=record["updated_at"],
        started_at=record["started_at"],
        completed_at=record["completed_at"],
        cancelled_at=record["cancelled_at"],
    )


async def _build_batch_export_payload(
    repository: WebRepository,
    batch: Any,
) -> dict[str, Any]:
    # One single-snapshot read model shared with the run sheet: all rows come
    # from one transaction, so the export cannot stitch together different
    # committed states, and memberships are fetched in bulk.
    model = await repository.get_batch_read_model(batch.id, include_results=True)
    return build_batch_export(
        model["batch"],
        model["conditions"],
        model["substrates"],
        model["devices"],
        model["preparations"],
        [
            item
            for uses in model["preparation_uses"].values()
            for item in uses
        ],
        model["executions"],
        [
            item
            for members in model["execution_members"].values()
            for item in members
        ],
        model["deviations"],
        model["results"],
        model["result_assignments"],
    )


def _condition_response(record: Any) -> ConditionResponse:
    return ConditionResponse(
        id=record.id,
        experiment_id=record.experiment_id,
        role=record.role.value,
        condition_code=record.condition_code,
        condition_name=record.condition_name,
        recipe_snapshot=record.recipe_snapshot,
        recipe_schema_version=record.recipe_schema_version,
        canonical_hash=record.canonical_hash,
        source_baseline_version_id=record.source_baseline_version_id,
        device_layout_code=record.device_layout_code,
        device_layout_snapshot=record.device_layout_snapshot,
        planned_substrate_count=record.planned_substrate_count,
        expected_device_count=record.expected_device_count,
        requires_manual_review=record.requires_manual_review,
        created_at=record.created_at.isoformat(),
    )


def _substrate_exception_response(record: Any) -> SubstrateExceptionResponse:
    return SubstrateExceptionResponse(
        id=record.id,
        condition_id=record.condition_id,
        requested_count=record.requested_count,
        reason=record.reason,
        requested_by_id=record.requested_by_id,
        requested_at=record.requested_at.isoformat(),
        decision=record.decision.value,
        decided_by_id=record.decided_by_id,
        decided_at=record.decided_at.isoformat() if record.decided_at else None,
        decision_note=record.decision_note,
        approved_condition_hash=record.approved_condition_hash,
    )


def _campaign_response(record: Any) -> CampaignResponse:
    return CampaignResponse(
        id=record.id,
        code=record.code,
        display_name=record.display_name,
        description=record.description,
        status=record.status.value,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        closed_at=record.closed_at.isoformat() if record.closed_at else None,
    )


def _control_only_baseline_recipe(device_recipe: dict[str, Any]) -> dict[str, Any]:
    """Strip a device recipe down to its control setup for baseline storage.

    A baseline captures only the control group's substrate and layer stack, so
    saved baselines never carry target-group modifications into new experiments.
    """

    recipe = deepcopy(device_recipe)
    control = next(
        (
            group
            for group in recipe.get("experimental_groups", [])
            if group.get("kind") == "control"
        ),
        {},
    )
    recipe["experimental_groups"] = [
        {
            "group_id": "control",
            "kind": "control",
            "name": control.get("name") or "Control",
            "change_from_control": control.get("change_from_control")
            or "Baseline fabrication procedure",
            "inherits_control": False,
            "adjustments": [],
            "substrate_count": None,
        },
        {
            "group_id": "target-1",
            "kind": "target",
            "name": "Target 1",
            "change_from_control": "",
            "inherits_control": True,
            "adjustments": [],
            "layers": None,
            "substrate_count": None,
        },
    ]
    return recipe


def _baseline_values(
    payload: BaselinePayload,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Return a normalized, complete control baseline from an API payload."""

    name = payload.name.strip()
    if not name:
        raise ValueError("baseline name must not be blank")
    control_only = _control_only_baseline_recipe(
        payload.device_recipe.model_dump(mode="python")
    )
    normalized = validate_device_recipe(control_only)
    deposition_process = validate_deposition_process(
        payload.deposition_process.model_dump(mode="python")
    )
    return name, normalized, deposition_process


async def _create_experiment(
    repository: WebRepository,
    recipe_values: dict[str, Any],
    *,
    campaign_id: str | None,
    source_baseline_version_id: int | None,
    condition_plans: list[dict[str, Any]] | None = None,
    actor_user_id: int,
    client_ip: str | None,
) -> ExperimentRecord:
    complete_values = dict(recipe_values)
    if complete_values.get("device_recipe") is None:
        raise ValueError(
            "a complete device_recipe is required; baselines and presets must be "
            "expanded before an experiment is saved"
        )
    recipe = DepositionRecipe.from_mapping(complete_values)
    return await repository.add_experiment(
        recipe,
        campaign_id=campaign_id,
        source_baseline_version_id=source_baseline_version_id,
        condition_plans=condition_plans,
        actor_user_id=actor_user_id,
        client_ip=client_ip,
    )


async def _read_result_file(result_file: UploadFile) -> bytes:
    """Read one result upload with a strict memory and storage bound."""

    chunks: list[bytes] = []
    size_bytes = 0
    while True:
        chunk = await result_file.read(_RESULT_READ_CHUNK_BYTES)
        if not chunk:
            break
        size_bytes += len(chunk)
        if size_bytes > MAX_RESULT_FILE_BYTES:
            maximum_mb = MAX_RESULT_FILE_BYTES // (1024 * 1024)
            raise ValueError(f"result file must not exceed {maximum_mb} MB")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_result_upload_metadata(
    result_file: UploadFile,
    content: bytes,
) -> tuple[str, str]:
    """Allow only bounded, non-empty CSV-like text uploads with safe names."""

    if not content:
        raise ValueError("result file must not be empty")
    if b"\x00" in content:
        raise ValueError("result file must be text CSV data")
    supplied_name = result_file.filename or "jv_results.csv"
    filename = Path(supplied_name.replace("\\", "/")).name.strip()
    if not filename or len(filename) > 255:
        raise ValueError("result filename must contain 1-255 characters")
    if any(ord(character) < 32 for character in filename):
        raise ValueError("result filename contains unsupported control characters")
    if Path(filename).suffix.lower() != ".csv":
        raise ValueError("result file must use the .csv extension")
    supplied_content_type = (result_file.content_type or "text/csv").split(";", 1)[0].lower()
    if supplied_content_type not in _ALLOWED_RESULT_CONTENT_TYPES:
        raise ValueError("result file content type must be CSV or plain text")
    return filename, "text/csv"


def _batch_result_groups(conditions: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "group_id": str(condition.id),
            "batch_condition_id": condition.id,
            "condition_code": condition.condition_code,
            "kind": condition.role,
            "name": condition.condition_name,
        }
        for condition in conditions
    ]


async def _get_record_or_404(
    repository: WebRepository,
    experiment_id: int,
    auth_context: AuthContext,
) -> ExperimentRecord:
    try:
        return await repository.get_experiment(
            experiment_id,
            owner_user_id=_student_owner_id(auth_context),
        )
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


def _operation_error_to_http(error: OperationError) -> HTTPException:
    """Map typed application-operation failures onto the HTTP boundary.

    Message texts pass through unchanged so existing clients see the same
    response bodies. Unexpected (non-operation) exceptions are never mapped
    here and keep normal 500 handling.
    """

    if isinstance(error, RecordNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        )
    if isinstance(error, AccessDenied):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(error)
        )
    if isinstance(error, StateConflict):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        )
    if isinstance(error, InvalidInput):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="unexpected operation failure",
    )


def _student_owner_id(auth_context: AuthContext) -> int | None:
    """Restrict students to their own records; elevated roles retain lab-wide access."""

    if auth_context.user.role == UserRole.STUDENT:
        return auth_context.user.id
    return None


def _record_response(record: ExperimentRecord) -> ExperimentResponse:
    return ExperimentResponse(
        id=record.id,
        recipe=record.recipe.to_dict(),
        status=record.status.value,
        metrics=record.metrics,
        failure_reason=record.failure_reason,
        created_at=record.created_at,
        updated_at=record.updated_at,
        campaign_id=record.campaign_id,
        experiment_code=record.experiment_code,
        series_version=record.series_version,
        plan_type=record.plan_type,
        plan_status=record.plan_status,
        device_summary=record.device_summary,
    )


def _result_summary_response(record: dict[str, Any]) -> ResultSummaryResponse:
    return ResultSummaryResponse(
        id=record["id"],
        experiment_id=record["experiment_id"],
        fabrication_batch_id=record["fabrication_batch_id"],
        filename=record["filename"],
        content_type=record["content_type"],
        size_bytes=record["size_bytes"],
        sha256=record["sha256"],
        group_assignment=record["group_assignment"],
        metrics=record["metrics"],
        analysis_schema_version=record["analysis_schema_version"],
        created_at=record["created_at"],
    )


def _fabrication_batch_response(record: Any) -> FabricationBatchResponse:
    return FabricationBatchResponse(
        id=record.id,
        experiment_id=record.experiment_id,
        batch_number=record.batch_number,
        batch_code=record.batch_code,
        status=record.status.value,
        condition_set_hash=record.condition_set_hash,
        notes=record.notes,
        created_by_id=record.created_by_id,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        cancelled_at=record.cancelled_at.isoformat() if record.cancelled_at else None,
    )


def _frozen_batch_condition_response(record: Any) -> FrozenBatchConditionResponse:
    return FrozenBatchConditionResponse(
        id=record.id,
        fabrication_batch_id=record.fabrication_batch_id,
        source_condition_id=record.source_condition_id,
        condition_code=record.condition_code,
        condition_name=record.condition_name,
        role=record.role,
        source_condition_hash=record.source_condition_hash,
        recipe_snapshot=record.recipe_snapshot,
        recipe_schema_version=record.recipe_schema_version,
        device_layout_code=record.device_layout_code,
        device_layout_snapshot=record.device_layout_snapshot,
        planned_substrate_count=record.planned_substrate_count,
        expected_device_count=record.expected_device_count,
        actual_substrate_count=record.actual_substrate_count,
    )


def _fabrication_substrate_response(record: Any) -> FabricationSubstrateResponse:
    return FabricationSubstrateResponse(
        id=record.id,
        batch_condition_id=record.batch_condition_id,
        substrate_ordinal=record.substrate_ordinal,
        substrate_code=record.substrate_code,
        substrate_mark=record.substrate_mark,
        status=record.status.value,
        notes=record.notes,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _fabrication_device_response(record: Any) -> FabricationDeviceResponse:
    return FabricationDeviceResponse(
        id=record.id,
        substrate_id=record.substrate_id,
        device_ordinal=record.device_ordinal,
        device_code=record.device_code,
        device_mark=record.device_mark,
        device_active_area_cm2=record.device_active_area_cm2,
        status=record.status.value,
        notes=record.notes,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _solution_preparation_response(record: Any) -> SolutionPreparationResponse:
    return SolutionPreparationResponse(
        id=record.id,
        fabrication_batch_id=record.fabrication_batch_id,
        preparation_code=record.preparation_code,
        status=record.status.value,
        planned_solution_snapshot=record.planned_solution_snapshot,
        planned_snapshot_schema_version=record.planned_snapshot_schema_version,
        planned_canonical_hash=record.planned_canonical_hash,
        actual_solution_snapshot=record.actual_solution_snapshot,
        actual_snapshot_schema_version=record.actual_snapshot_schema_version,
        actual_canonical_hash=record.actual_canonical_hash,
        actual_recording_mode=record.actual_recording_mode,
        prepared_by_id=record.prepared_by_id,
        prepared_at=record.prepared_at.isoformat() if record.prepared_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        notes=record.notes,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _process_execution_response(record: Any) -> ProcessExecutionResponse:
    return ProcessExecutionResponse(
        id=record.id,
        fabrication_batch_id=record.fabrication_batch_id,
        execution_code=record.execution_code,
        method=record.method,
        layer_role=record.layer_role,
        layer_type=record.layer_type,
        layer_name=record.layer_name,
        status=record.status.value,
        is_shared=record.is_shared,
        planned_process_snapshot=record.planned_process_snapshot,
        planned_snapshot_schema_version=record.planned_snapshot_schema_version,
        planned_canonical_hash=record.planned_canonical_hash,
        actual_process_snapshot=record.actual_process_snapshot,
        actual_snapshot_schema_version=record.actual_snapshot_schema_version,
        actual_canonical_hash=record.actual_canonical_hash,
        actual_recording_mode=record.actual_recording_mode,
        equipment_identifier=record.equipment_identifier,
        executed_by_id=record.executed_by_id,
        started_at=record.started_at.isoformat() if record.started_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        notes=record.notes,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _deviation_response(record: Any) -> DeviationResponse:
    return DeviationResponse(
        id=record.id,
        fabrication_batch_id=record.fabrication_batch_id,
        category=record.category,
        severity=record.severity,
        deviation_type=record.deviation_type,
        description=record.description,
        planned_value=record.planned_value,
        actual_value=record.actual_value,
        recorded_by_id=record.recorded_by_id,
        recorded_at=record.recorded_at.isoformat(),
        supersedes_deviation_id=record.supersedes_deviation_id,
        solution_preparation_id=record.solution_preparation_id,
        process_execution_id=record.process_execution_id,
        substrate_id=record.substrate_id,
        device_id=record.device_id,
        condition_id=record.condition_id,
        created_at=record.created_at.isoformat(),
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None

__all__ = [
    "annotations",
    "csv",
    "deepcopy",
    "Path",
    "Annotated",
    "Any",
    "APIRouter",
    "Depends",
    "File",
    "Form",
    "HTTPException",
    "Request",
    "UploadFile",
    "status",
    "Response",
    "IntegrityError",
    "run_in_threadpool",
    "MAX_SOLID_CHEMICALS",
    "MAX_SOLVENTS",
    "VCD_VALVES",
    "DepositionRecipe",
    "ExperimentRecord",
    "validate_deposition_process",
    "validate_device_recipe",
    "assign_substrates_to_groups",
    "parse_jv_analysis",
    "build_batch_export",
    "build_plan_export",
    "canonical_batch_json",
    "canonical_plan_json",
    "render_batch_pdf",
    "render_plan_pdf",
    "AuthContext",
    "require_csrf",
    "require_role",
    "require_user",
    "CampaignCreatePayload",
    "CampaignResponse",
    "CampaignUpdatePayload",
    "ConditionCreatePayload",
    "ConditionResponse",
    "ConditionUpdatePayload",
    "ExperimentDetailResponse",
    "ExperimentResponse",
    "PlanStatusUpdatePayload",
    "RecipePayload",
    "BaselinePayload",
    "BaselinePromotePayload",
    "BaselineResponse",
    "BaselineVersionResponse",
    "LayerPresetPayload",
    "LayerPresetResponse",
    "LayerPresetVersionResponse",
    "MaterialCreatePayload",
    "MaterialProductCreatePayload",
    "MaterialProductResponse",
    "MaterialProductUpdatePayload",
    "MaterialResponse",
    "MaterialUpdatePayload",
    "SubstrateExceptionCreatePayload",
    "SubstrateExceptionDecisionPayload",
    "SubstrateExceptionResponse",
    "UploadedResultResponse",
    "FabricationBatchCreatePayload",
    "FabricationBatchStatusUpdatePayload",
    "FabricationBatchResponse",
    "FrozenBatchConditionResponse",
    "FabricationSubstrateResponse",
    "FabricationDeviceResponse",
    "SolutionPreparationCreatePayload",
    "SolutionPreparationUpdatePayload",
    "SolutionPreparationResponse",
    "SolutionPreparationUseResponse",
    "MembershipSplitPayload",
    "MembershipMergePayload",
    "ProcessExecutionCreatePayload",
    "ProcessExecutionUpdatePayload",
    "ProcessExecutionResponse",
    "ProcessExecutionMemberResponse",
    "ResultSummaryResponse",
    "DeviationCreatePayload",
    "DeviationResponse",
    "ResultDetailResponse",
    "ResultAssignmentGroupResponse",
    "ResultAssignmentRowResponse",
    "ResultAssignmentItem",
    "ResultAssignmentsPayload",
    "FabricationBatchListItemResponse",
    "ResultListItemResponse",
    "DeviceLayoutCreatePayload",
    "EditorConfigResponse",
    "RecordAsPlannedResponse",
    "RunSheetPreparationResponse",
    "RunSheetExecutionResponse",
    "RunSheetResponse",
    "AccessDenied",
    "InvalidInput",
    "OperationError",
    "RecordNotFound",
    "StateConflict",
    "update_batch_status",
    "ResultAssignmentInput",
    "ResultExclusionInput",
    "save_result_analysis",
    "BatchStatus",
    "CampaignStatus",
    "ConditionRole",
    "DeviationSeverity",
    "ExceptionDecision",
    "ExecutionStatus",
    "PlanStatus",
    "PreparationStatus",
    "UserRole",
    "WebRepository",
    "create_device_layout",
    "list_device_layouts",
    "MAX_RESULT_FILE_BYTES",
    "_RESULT_READ_CHUNK_BYTES",
    "_ALLOWED_RESULT_CONTENT_TYPES",
    "_condition_for_actor",
    "_batch_for_actor_or_404",
    "_result_for_actor_or_404",
    "_result_detail_response",
    "_result_assignment_row_response",
    "_result_list_item_response",
    "_fabrication_batch_list_item_response",
    "_build_batch_export_payload",
    "_condition_response",
    "_substrate_exception_response",
    "_campaign_response",
    "_control_only_baseline_recipe",
    "_baseline_values",
    "_create_experiment",
    "_read_result_file",
    "validate_result_upload_metadata",
    "_batch_result_groups",
    "_get_record_or_404",
    "_operation_error_to_http",
    "_student_owner_id",
    "_record_response",
    "_result_summary_response",
    "_fabrication_batch_response",
    "_frozen_batch_condition_response",
    "_fabrication_substrate_response",
    "_fabrication_device_response",
    "_solution_preparation_response",
    "_process_execution_response",
    "_deviation_response",
    "_client_ip",
]
