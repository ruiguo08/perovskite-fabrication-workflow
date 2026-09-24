"""Experiment record types shared by the web registry and BO consumers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .recipe import DepositionRecipe


class ExperimentStatus(str, Enum):
    SUGGESTED = "suggested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ExperimentRecord:
    id: int
    recipe: DepositionRecipe
    status: ExperimentStatus
    metrics: dict[str, float]
    failure_reason: str | None
    created_at: str
    updated_at: str
    campaign_id: str | None = None
    experiment_code: str | None = None
    series_version: int | None = None
    plan_type: str | None = None
    plan_status: str | None = None
    # Derived from the control (or standalone) condition snapshot: substrate
    # material plus layer names, for list views and human-readable summaries.
    device_summary: str | None = None
