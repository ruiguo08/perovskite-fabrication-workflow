"""Versioned, complete snapshots for batch preparation and execution records."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from perovskite_bo.device_recipe import (
    MAX_SOLID_CHEMICALS,
    MAX_SOLVENTS,
    VCD_VALVES,
    AldProcess,
    AnnealStep,
    SolutionRecipe,
    SpinStep,
    SputteringProcess,
    ThermalEvaporationProcess,
    VcdGasBackfillStage,
    VcdStage,
)

SOLUTION_SNAPSHOT_SCHEMA_VERSION = 1
PROCESS_SNAPSHOT_SCHEMA_VERSION = 1


class _OperationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SpinCoatingOperation(_OperationModel):
    method: Literal["spin_coating"] = "spin_coating"
    spin_steps: list[SpinStep] = Field(min_length=1, max_length=4)


class AnnealingOperation(_OperationModel):
    method: Literal["annealing"] = "annealing"
    anneal_steps: list[AnnealStep] = Field(min_length=1, max_length=2)


class VcdOperation(_OperationModel):
    method: Literal["vcd"] = "vcd"
    vcd_stages: list[VcdStage] = Field(min_length=1, max_length=5)
    gas_backfill_stages: list[VcdGasBackfillStage] = Field(
        default_factory=list,
        max_length=5,
    )
    vcd_step_sequence: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_sequence(self) -> VcdOperation:
        expected = {
            *(f"vcd_stage{index}" for index in range(1, len(self.vcd_stages) + 1)),
            *(
                f"gas_backfill_stage{index}"
                for index in range(1, len(self.gas_backfill_stages) + 1)
            ),
        }
        if len(self.vcd_step_sequence) != len(expected) or set(
            self.vcd_step_sequence
        ) != expected:
            raise ValueError(
                "vcd_step_sequence must contain every evacuation and gas "
                "backfill stage exactly once"
            )
        return self


ProcessOperation = Annotated[
    SpinCoatingOperation
    | AnnealingOperation
    | VcdOperation
    | SputteringProcess
    | ThermalEvaporationProcess
    | AldProcess,
    Field(discriminator="method"),
]
_PROCESS_OPERATION_ADAPTER = TypeAdapter(ProcessOperation)


def validate_solution_snapshot(values: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a complete solution recipe suitable for planned or actual use."""

    if not isinstance(values, Mapping):
        raise TypeError("solution snapshot must be a mapping")
    solution = SolutionRecipe.model_validate(values)
    if solution.formulation_type == "weighed_solids":
        if not solution.solids:
            raise ValueError("a weighed-solids solution requires at least one solid")
        if solution.stock_dispersion or solution.stock_volume_ml is not None:
            raise ValueError(
                "a weighed-solids solution cannot include a stock dispersion"
            )
    else:
        if not solution.stock_dispersion or solution.stock_volume_ml is None:
            raise ValueError(
                "a diluted dispersion requires a stock name and volume"
            )
        if solution.solids:
            raise ValueError("a diluted dispersion cannot include weighed solids")
    if not solution.solvents:
        raise ValueError("a solution requires at least one solvent")
    for index, ingredient in enumerate(solution.solids, start=1):
        if not ingredient.chemical or ingredient.weight_mg is None:
            raise ValueError(
                f"solid ingredient {index} requires a chemical and weight"
            )
    for index, ingredient in enumerate(solution.solvents, start=1):
        if not ingredient.solvent or ingredient.volume_ml is None:
            raise ValueError(
                f"solvent ingredient {index} requires a solvent and volume"
            )
    if len(solution.solids) > MAX_SOLID_CHEMICALS:
        raise ValueError("solution contains too many solid ingredients")
    if len(solution.solvents) > MAX_SOLVENTS:
        raise ValueError("solution contains too many solvents")
    return solution.model_dump(mode="python")


def validate_process_snapshot(
    values: Mapping[str, Any],
    *,
    expected_method: str | None = None,
) -> dict[str, Any]:
    """Normalize one complete executable process operation."""

    if not isinstance(values, Mapping):
        raise TypeError("process snapshot must be a mapping")
    operation = _PROCESS_OPERATION_ADAPTER.validate_python(values)
    method = str(operation.method)
    if expected_method is not None and method != expected_method:
        raise ValueError(
            f"process snapshot method must be {expected_method!r}, got {method!r}"
        )
    if isinstance(operation, SpinCoatingOperation):
        for index, step in enumerate(operation.spin_steps, start=1):
            if None in (step.rpm, step.seconds, step.acceleration_rpm_per_s):
                raise ValueError(f"spin-coating step {index} is incomplete")
    elif isinstance(operation, AnnealingOperation):
        for index, step in enumerate(operation.anneal_steps, start=1):
            if None in (step.temperature_c, step.seconds):
                raise ValueError(f"annealing step {index} is incomplete")
    elif isinstance(operation, VcdOperation):
        for index, stage in enumerate(operation.vcd_stages, start=1):
            if stage.valve not in VCD_VALVES:
                raise ValueError(
                    f"VCD stage {index} valve must be one of: "
                    + ", ".join(VCD_VALVES)
                )
            if stage.pressure_pa is None or stage.seconds is None:
                raise ValueError(f"VCD stage {index} is incomplete")
        for index, stage in enumerate(operation.gas_backfill_stages, start=1):
            if (
                not stage.gas
                or stage.flow_sccm is None
                or stage.target_pressure_pa is None
                or stage.hold_seconds is None
            ):
                raise ValueError(f"gas backfill stage {index} is incomplete")
    elif isinstance(operation, SputteringProcess):
        if bool(operation.gas2) != (operation.gas2_flow_sccm is not None):
            raise ValueError("sputtering gas 2 and its flow rate are required together")
        required = (
            operation.power_w,
            operation.pressure_pa,
            operation.gas1,
            operation.gas1_flow_sccm,
            operation.duration_seconds,
        )
        if any(value is None or value == "" for value in required):
            raise ValueError("sputtering process snapshot is incomplete")
    elif isinstance(operation, ThermalEvaporationProcess):
        if None in (operation.thickness_nm, operation.rate_angstrom_per_s):
            raise ValueError("thermal evaporation process snapshot is incomplete")
    elif isinstance(operation, AldProcess):
        if None in (
            operation.thickness_nm,
            operation.substrate_temperature_c,
            operation.cycles,
        ):
            raise ValueError("ALD process snapshot is incomplete")
    return operation.model_dump(mode="python")


def snapshot_hash(values: Mapping[str, Any]) -> str:
    """Hash the normalized snapshot JSON using the export representation."""

    return hashlib.sha256(
        json.dumps(
            values,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
