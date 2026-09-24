"""Canonical, condition-owned fabrication snapshots.

A condition snapshot deliberately excludes ``experimental_groups``.  It is one
complete substrate/layer/process configuration and can therefore be exported,
hashed, compared, and reconstructed without consulting a control condition.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from perovskite_bo.device_recipe import (
    DEVICE_RECIPE_SCHEMA_VERSION,
    DeviceLayer,
    PerovskiteDepositionProcess,
    SubstrateRecipe,
    validate_deposition_process,
    validate_device_recipe,
)

CONDITION_RECIPE_SCHEMA_VERSION = 3


class ConditionDeviceConfiguration(BaseModel):
    """The device fields shared by all conditions except group metadata."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = DEVICE_RECIPE_SCHEMA_VERSION
    setup_mode: str
    legacy_baseline_seed_id: str | None = None
    junction_type: str = "single_junction"
    perovskite_bandgap: str | None = "normal_bandgap"
    tandem_type: str | None = None
    architecture: Literal["pin", "nip"] = "pin"
    substrate: SubstrateRecipe
    layers: list[DeviceLayer] = Field(min_length=5, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy(cls, values: Any) -> Any:
        """Convert old ``"reference"`` setup_mode and ``stack_reference_id``."""
        if not isinstance(values, dict):
            return values
        if values.get("setup_mode") == "reference":
            values["setup_mode"] = "baseline"
        if "stack_reference_id" in values and "legacy_baseline_seed_id" not in values:
            values["legacy_baseline_seed_id"] = values.pop("stack_reference_id")
        if values.get("architecture") is None:
            values["architecture"] = "pin"
        return values


class ConditionRecipeSnapshot(BaseModel):
    """Versioned immutable recipe shape stored by one experiment condition."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = CONDITION_RECIPE_SCHEMA_VERSION
    device: ConditionDeviceConfiguration
    deposition_process: PerovskiteDepositionProcess


def build_condition_snapshot(
    device_recipe: Mapping[str, Any],
    *,
    layers: list[dict[str, Any]] | None = None,
    deposition_process: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate one complete condition from a guided device recipe."""

    device = {
        key: deepcopy(device_recipe.get(key))
        for key in (
            "schema_version",
            "setup_mode",
            "junction_type",
            "perovskite_bandgap",
            "tandem_type",
            "architecture",
            "substrate",
        )
    }
    device["layers"] = deepcopy(
        layers if layers is not None else device_recipe.get("layers", [])
    )
    return validate_condition_snapshot(
        {
            "schema_version": CONDITION_RECIPE_SCHEMA_VERSION,
            "device": device,
            "deposition_process": deepcopy(dict(deposition_process)),
        }
    )


def validate_condition_snapshot(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized, complete and reconstruction-safe snapshot."""

    if not isinstance(values, Mapping):
        raise TypeError("condition recipe snapshot must be a mapping")
    migrated = deepcopy(dict(values))
    if migrated.get("schema_version") in (None, 1, 2):
        migrated["schema_version"] = CONDITION_RECIPE_SCHEMA_VERSION
    device = migrated.get("device")
    if isinstance(device, dict) and device.get("schema_version") in (None, 1):
        device["schema_version"] = DEVICE_RECIPE_SCHEMA_VERSION
    parsed = ConditionRecipeSnapshot.model_validate(migrated)
    if parsed.schema_version != CONDITION_RECIPE_SCHEMA_VERSION:
        raise ValueError(
            f"condition schema_version must equal {CONDITION_RECIPE_SCHEMA_VERSION}"
        )
    device = parsed.device.model_dump(mode="python")
    if device["schema_version"] != DEVICE_RECIPE_SCHEMA_VERSION:
        raise ValueError(
            f"device schema_version must equal {DEVICE_RECIPE_SCHEMA_VERSION}"
        )

    # Reuse the canonical full-device completeness checks with temporary group
    # metadata, then discard those groups from the persisted condition shape.
    validation_recipe = deepcopy(device)
    validation_recipe.pop("legacy_baseline_seed_id", None)
    validation_recipe["experimental_groups"] = [
        {
            "group_id": "control",
            "kind": "control",
            "name": "Condition validation control",
            "inherits_control": False,
            "adjustments": [],
        },
        {
            "group_id": "target-1",
            "kind": "target",
            "name": "Condition validation target",
            "inherits_control": True,
            "adjustments": [],
            "layers": None,
        },
    ]
    normalized_device = validate_device_recipe(validation_recipe)
    normalized_process = validate_deposition_process(
        parsed.deposition_process.model_dump(mode="python")
    )
    normalized_device.pop("experimental_groups", None)
    normalized_device.pop("legacy_baseline_seed_id", None)
    return {
        "schema_version": CONDITION_RECIPE_SCHEMA_VERSION,
        "device": normalized_device,
        "deposition_process": normalized_process,
    }


def canonical_hash(snapshot: Mapping[str, Any]) -> str:
    """Return the deterministic SHA-256 of a normalized condition snapshot."""

    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()
