"""Frozen record types, enumerations, and shared constants for the repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from ..device_layouts import expected_device_count

# Semantic deviation types consumed by the workflow gates (mirrors the
# ck_execution_deviations_valid_deviation_type database check).
DEVIATION_TYPES = (
    "general",
    "fabrication_shortfall",
    "measurement_shortfall",
)


class UserRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMINISTRATOR = "administrator"


ROLE_RANK = {
    UserRole.STUDENT: 1,
    UserRole.INSTRUCTOR: 2,
    UserRole.ADMINISTRATOR: 3,
}

MATERIAL_CATEGORIES = frozenset({"substrate", "chemical", "solvent", "gas", "other"})
MATERIAL_STATUSES = frozenset({"pending", "active", "inactive"})


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ConditionRole(StrEnum):
    CONTROL = "control"
    TARGET = "target"
    STANDALONE = "standalone"


class ExceptionDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RELEASED = "released"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CampaignRecord:
    id: int
    code: str
    display_name: str
    description: str
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    created_by_id: int | None


@dataclass(frozen=True)
class ConditionRecord:
    id: int
    experiment_id: int
    role: ConditionRole
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
    created_at: datetime
    created_by_id: int | None


@dataclass(frozen=True)
class SubstrateExceptionRecord:
    id: int
    condition_id: int
    requested_count: int
    reason: str
    requested_by_id: int | None
    requested_at: datetime
    decision: ExceptionDecision
    decided_by_id: int | None
    decided_at: datetime | None
    decision_note: str
    approved_condition_hash: str | None


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    display_name: str
    password_hash: str
    role: UserRole
    is_active: bool
    failed_login_count: int
    locked_until: datetime | None
    last_login_at: datetime | None
    password_changed_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    token_hash: str
    csrf_token_hash: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user: UserRecord


@dataclass(frozen=True)
class AuditEventRecord:
    id: int
    created_at: datetime
    actor_user_id: int | None
    actor_username: str | None
    action: str
    entity_type: str
    entity_id: str | None
    client_ip: str | None
    details: dict[str, Any]


class BatchStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PreparationStatus(StrEnum):
    PLANNED = "planned"
    PREPARING = "preparing"
    READY = "ready"
    CONSUMED = "consumed"
    DISCARDED = "discarded"


class ExecutionStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubstrateDeviceStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXCLUDED = "excluded"


class DeviationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class FabricationBatchRecord:
    id: int
    experiment_id: int
    batch_number: int
    batch_code: str
    status: BatchStatus
    condition_set_hash: str
    notes: str
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


@dataclass(frozen=True)
class FrozenBatchConditionRecord:
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


@dataclass(frozen=True)
class FabricationSubstrateRecord:
    id: int
    batch_condition_id: int
    substrate_ordinal: int
    substrate_code: str
    substrate_mark: str | None
    status: SubstrateDeviceStatus
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FabricationDeviceRecord:
    id: int
    substrate_id: int
    device_ordinal: int
    device_code: str
    device_mark: str | None
    device_active_area_cm2: str
    status: SubstrateDeviceStatus
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SolutionPreparationRecord:
    id: int
    fabrication_batch_id: int
    preparation_code: str
    status: PreparationStatus
    planned_solution_snapshot: dict[str, Any]
    planned_snapshot_schema_version: int
    planned_canonical_hash: str
    actual_solution_snapshot: dict[str, Any] | None
    actual_snapshot_schema_version: int | None
    actual_canonical_hash: str | None
    actual_recording_mode: str | None
    prepared_by_id: int | None
    prepared_at: datetime | None
    completed_at: datetime | None
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProcessExecutionRecord:
    id: int
    fabrication_batch_id: int
    execution_code: str
    method: str
    layer_role: str
    layer_type: str
    layer_name: str
    status: ExecutionStatus
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
    started_at: datetime | None
    completed_at: datetime | None
    notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ExecutionDeviationRecord:
    id: int
    fabrication_batch_id: int
    category: str
    severity: str
    deviation_type: str
    description: str
    planned_value: dict[str, Any] | None
    actual_value: dict[str, Any] | None
    recorded_by_id: int | None
    recorded_at: datetime
    supersedes_deviation_id: int | None
    solution_preparation_id: int | None
    process_execution_id: int | None
    substrate_id: int | None
    device_id: int | None
    condition_id: int | None
    created_at: datetime
