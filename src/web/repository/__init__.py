"""Typed asynchronous persistence for the networked web application.

The public surface is unchanged from the original single-module
``repository.py``: importers continue to use ``from web.repository import ...``.
The implementation is split into :mod:`.records` (frozen record types,
enumerations, and constants), :mod:`.helpers` (shared cross-domain SQL helpers),
and :mod:`.repository` (the :class:`WebRepository` transactional boundary).
"""

from __future__ import annotations

# Back-compat re-exports: the original single module re-exported these
# SQLAlchemy tables and private helpers, and admin_cli/tests import them via
# ``web.repository``. Keep them reachable so no importer changes. Private
# helpers now live beside their domain mixin; only cross-domain ones remain
# in :mod:`.helpers`.
from ..database import experiment_conditions, experiments
from .helpers import _add_audit_event
from .baseline import _baseline_record, _baseline_statement
from .preset import _layer_preset_record, _layer_preset_statement
from .material import _material_record
from .result import _result_summary_statement
from .batch import _batch_status_transitions
from .records import (
    DEVIATION_TYPES,
    MATERIAL_CATEGORIES,
    MATERIAL_STATUSES,
    ROLE_RANK,
    AuditEventRecord,
    BatchStatus,
    CampaignRecord,
    CampaignStatus,
    ConditionRecord,
    ConditionRole,
    DeviationSeverity,
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
    SessionRecord,
    SolutionPreparationRecord,
    SubstrateDeviceStatus,
    SubstrateExceptionRecord,
    UserRecord,
    UserRole,
)
from .repository import WebRepository

__all__ = [
    "DEVIATION_TYPES",
    "MATERIAL_CATEGORIES",
    "MATERIAL_STATUSES",
    "ROLE_RANK",
    "_add_audit_event",
    "_baseline_record",
    "_baseline_statement",
    "_batch_status_transitions",
    "_layer_preset_record",
    "_layer_preset_statement",
    "_material_record",
    "_result_summary_statement",
    "experiment_conditions",
    "experiments",
    "AuditEventRecord",
    "BatchStatus",
    "CampaignRecord",
    "CampaignStatus",
    "ConditionRecord",
    "ConditionRole",
    "DeviationSeverity",
    "ExceptionDecision",
    "ExecutionDeviationRecord",
    "ExecutionStatus",
    "FabricationBatchRecord",
    "FabricationDeviceRecord",
    "FabricationSubstrateRecord",
    "FrozenBatchConditionRecord",
    "PlanStatus",
    "PreparationStatus",
    "ProcessExecutionRecord",
    "SessionRecord",
    "SolutionPreparationRecord",
    "SubstrateDeviceStatus",
    "SubstrateExceptionRecord",
    "UserRecord",
    "UserRole",
    "WebRepository",
]
