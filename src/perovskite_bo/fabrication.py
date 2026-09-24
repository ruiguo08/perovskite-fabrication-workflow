"""Structured experimental context for full-device fabrication."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping

DEFAULT_FABRICATION_BASELINE_ID = "usual_v1"
FABRICATION_SCHEMA_VERSION = 1
PRECURSOR_SOLVENTS = ("DMF:DMSO", "DMF:DMSO:NMP=16:3:1")

LOW_SPEED_DISPENSE_DESCRIPTION = (
    "Intentional low-speed dispense/wetting stage used to fully cover the "
    "substrate before high-rpm spinning."
)


@dataclass(frozen=True)
class FabricationField:
    """One editable fabrication-context field shown by the web interface."""

    name: str
    label: str
    kind: str
    unit: str = ""
    default: Any | None = None
    choices: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class FabricationSection:
    """A process or material layer containing related fabrication fields."""

    key: str
    label: str
    fields: tuple[FabricationField, ...]


def _integer(
    name: str,
    label: str,
    unit: str,
    default: int | None,
    description: str = "",
) -> FabricationField:
    return FabricationField(name, label, "integer", unit, default, description=description)


def _number(name: str, label: str, unit: str, default: Real | None = None) -> FabricationField:
    return FabricationField(name, label, "number", unit, default)


def _text(name: str, label: str, default: str | None = None) -> FabricationField:
    return FabricationField(name, label, "text", default=default)


def _choice(name: str, label: str, default: str, *choices: str) -> FabricationField:
    return FabricationField(name, label, "choice", default=default, choices=tuple(choices))


FABRICATION_SECTIONS = (
    FabricationSection(
        "baseline",
        "Fabrication baseline",
        (
            _choice(
                "baseline_id",
                "Baseline recipe",
                DEFAULT_FABRICATION_BASELINE_ID,
                DEFAULT_FABRICATION_BASELINE_ID,
            ),
            _integer(
                "schema_version",
                "Fabrication schema version",
                "",
                FABRICATION_SCHEMA_VERSION,
            ),
        ),
    ),
    FabricationSection(
        "plasma",
        "Plasma treatment",
        (
            _number("plasma_pressure_pa", "Vacuum pressure", "Pa", 50),
            _number("plasma_rf_power_w", "RF power", "W", 150),
            _integer("plasma_rf_time_seconds", "RF time", "s", 300),
            _number("plasma_gas1_flow_sccm", "Gas 1 flow", "sccm", 30),
            _number("plasma_gas2_flow_sccm", "Gas 2 flow", "sccm", 0),
            _integer("plasma_gas_refill_seconds", "Gas refill time", "s", 60),
        ),
    ),
    FabricationSection(
        "sam",
        "SAM",
        (
            _text("sam_material", "SAM material"),
            _number("sam_solution_concentration", "Solution concentration", ""),
            _choice(
                "sam_solution_concentration_unit",
                "Concentration unit",
                "mg/mL",
                "mg/mL",
                "mM",
                "mol/L",
                "wt%",
                "vol%",
            ),
            _text("sam_solvent", "Solvent"),
            _text("sam_solution_additives", "Additives or mixing ratio"),
            _integer(
                "sam_step1_rpm",
                "Dispense/coverage step 1 speed (intentional low speed)",
                "rpm",
                1,
                LOW_SPEED_DISPENSE_DESCRIPTION,
            ),
            _integer("sam_step1_acceleration_rpm_per_s", "Step 1 acceleration", "rpm/s", 1),
            _integer("sam_step1_seconds", "Step 1 time", "s", 60),
            _integer(
                "sam_step2_rpm",
                "Dispense/coverage step 2 speed (intentional low speed)",
                "rpm",
                2,
                LOW_SPEED_DISPENSE_DESCRIPTION,
            ),
            _integer("sam_step2_acceleration_rpm_per_s", "Step 2 acceleration", "rpm/s", 1),
            _integer("sam_step2_seconds", "Step 2 time", "s", 10),
            _integer("sam_step3_rpm", "Step 3 speed", "rpm", 3_000),
            _integer("sam_step3_acceleration_rpm_per_s", "Step 3 acceleration", "rpm/s", 1_000),
            _integer("sam_step3_seconds", "Step 3 time", "s", 30),
            _number("sam_anneal_temperature_c", "Annealing temperature", "°C", 100),
            _integer("sam_anneal_seconds", "Annealing time", "s", 600),
        ),
    ),
    FabricationSection(
        "pvk",
        "PVK",
        (
            _text("pvk_solution_composition", "Solution composition"),
            _number("pvk_solution_concentration", "Solution concentration", ""),
            _choice(
                "pvk_solution_concentration_unit",
                "Concentration unit",
                "mol/L",
                "mg/mL",
                "mM",
                "mol/L",
                "wt%",
                "vol%",
            ),
            _choice(
                "pvk_solvent",
                "Precursor solvent system",
                "NMP",
                "NMP",
                *PRECURSOR_SOLVENTS,
            ),
            _number("pvk_rbscn_percent", "RbSCN", "%"),
            _number("pvk_pb_scn2_percent", "Pb(SCN)2", "%"),
            _text("pvk_solution_additives", "Other additives or mixing ratio"),
            _integer(
                "pvk_step1_rpm",
                "Dispense/coverage step 1 speed (intentional low speed)",
                "rpm",
                1,
                LOW_SPEED_DISPENSE_DESCRIPTION,
            ),
            _integer("pvk_step1_acceleration_rpm_per_s", "Step 1 acceleration", "rpm/s", 1),
            _integer("pvk_step1_seconds", "Step 1 time", "s", 60),
            _integer(
                "pvk_step2_rpm",
                "Dispense/coverage step 2 speed (intentional low speed)",
                "rpm",
                2,
                LOW_SPEED_DISPENSE_DESCRIPTION,
            ),
            _integer("pvk_step2_acceleration_rpm_per_s", "Step 2 acceleration", "rpm/s", 1),
            _integer("pvk_step2_seconds", "Step 2 time", "s", 10),
            _integer("pvk_step3_rpm", "Step 3 speed", "rpm", 3_000),
            _integer("pvk_step3_acceleration_rpm_per_s", "Step 3 acceleration", "rpm/s", 1_000),
            _integer("pvk_step3_seconds", "Step 3 time", "s", 30),
            _number("pvk_anneal_stage1_temperature_c", "Anneal stage 1 temperature", "°C", 60),
            _integer("pvk_anneal_stage1_seconds", "Anneal stage 1 time", "s", 60),
            _number("pvk_anneal_stage2_temperature_c", "Anneal stage 2 temperature", "°C", 100),
            _integer("pvk_anneal_stage2_seconds", "Anneal stage 2 time", "s", 1_800),
            _number("pvk_vcd_target_pressure_pa", "VCD target pressure", "Pa", 1),
            _integer("pvk_vcd_pumpdown_seconds", "Typical pump-down time", "s", 10),
            _integer("pvk_vcd_total_seconds", "Total VCD time", "s", 15),
        ),
    ),
    FabricationSection(
        "passivation",
        "Passivation",
        (
            _text("passivation_material", "Material", "PEAI + EDADI"),
            _number("passivation_solution_concentration", "Solution concentration", ""),
            _choice(
                "passivation_solution_concentration_unit",
                "Concentration unit",
                "mg/mL",
                "mg/mL",
                "mM",
                "mol/L",
                "wt%",
                "vol%",
            ),
            _text("passivation_solvent", "Solvent"),
            _text("passivation_solution_additives", "Additives or mixing ratio"),
            _choice(
                "passivation_recipe_variant",
                "Recipe variant",
                "modified_dynamic",
                "modified_dynamic",
                "initial",
            ),
            _integer("passivation_step1_rpm", "Step 1 speed", "rpm", 4_000),
            _integer("passivation_step1_acceleration_rpm_per_s", "Step 1 acceleration", "rpm/s", 2_000),
            _integer("passivation_step1_seconds", "Step 1 time", "s", 60),
            _integer("passivation_step2_rpm", "Step 2 speed", "rpm", 4_000),
            _integer("passivation_step2_acceleration_rpm_per_s", "Step 2 acceleration", "rpm/s", 2_000),
            _integer("passivation_step2_seconds", "Step 2 time", "s", 30),
            _number("passivation_anneal_temperature_c", "Annealing temperature", "°C", 100),
            _integer("passivation_anneal_seconds", "Annealing time", "s", 300),
        ),
    ),
    FabricationSection(
        "pcbm",
        "PCBM",
        (
            _text("pcbm_material", "Material", "PCBM"),
            _number("pcbm_solution_concentration", "Solution concentration", ""),
            _choice(
                "pcbm_solution_concentration_unit",
                "Concentration unit",
                "mg/mL",
                "mg/mL",
                "mM",
                "mol/L",
                "wt%",
                "vol%",
            ),
            _text("pcbm_solvent", "Solvent"),
            _text("pcbm_solution_additives", "Additives or mixing ratio"),
            _integer(
                "pcbm_step1_rpm",
                "Dispense/coverage step 1 speed (intentional low speed)",
                "rpm",
                5,
                LOW_SPEED_DISPENSE_DESCRIPTION,
            ),
            _integer("pcbm_step1_acceleration_rpm_per_s", "Step 1 acceleration", "rpm/s", 5),
            _integer("pcbm_step1_seconds", "Step 1 time", "s", 60),
            _integer("pcbm_step2_rpm", "Step 2 speed", "rpm", 7_000),
            _integer("pcbm_step2_acceleration_rpm_per_s", "Step 2 acceleration", "rpm/s", 3_000),
            _integer("pcbm_step2_seconds", "Step 2 time", "s", 30),
            _number("pcbm_anneal_temperature_c", "Annealing temperature", "°C", 75),
            _integer("pcbm_anneal_seconds", "Annealing time", "s", 300),
        ),
    ),
    FabricationSection(
        "c60",
        "C60",
        (
            _choice("c60_method", "Deposition method", "thermal_evaporation", "thermal_evaporation", "other"),
            _number("c60_thickness_nm", "Thickness", "nm"),
            _number("c60_rate_angstrom_per_s", "Deposition rate", "Å/s"),
        ),
    ),
    FabricationSection(
        "electron_transport",
        "SnO₂ / BCP selection",
        (
            _choice(
                "electron_transport_selection",
                "Use exactly one layer",
                "sno2_ald",
                "sno2_ald",
                "bcp_evaporation",
            ),
        ),
    ),
    FabricationSection(
        "sno2",
        "SnO₂",
        (
            _number("sno2_thickness_nm", "Thickness", "nm"),
            _number("sno2_substrate_temperature_c", "Substrate temperature", "°C"),
            _integer("sno2_ald_cycles", "ALD cycles", "cycles", None),
        ),
    ),
    FabricationSection(
        "bcp",
        "BCP",
        (
            _number("bcp_thickness_nm", "Thickness", "nm"),
            _number("bcp_rate_angstrom_per_s", "Deposition rate", "Å/s"),
        ),
    ),
    FabricationSection(
        "ag",
        "Ag electrode",
        (
            _choice("ag_method", "Deposition method", "thermal_evaporation", "thermal_evaporation", "other"),
            _number("ag_thickness_nm", "Thickness", "nm"),
            _number("ag_rate_angstrom_per_s", "Deposition rate", "Å/s"),
        ),
    ),
)

FABRICATION_FIELDS = {
    field.name: field
    for section in FABRICATION_SECTIONS
    for field in section.fields
}


def default_fabrication_context() -> dict[str, Any]:
    """Return the documented baseline while leaving unspecified values blank."""

    return {
        field.name: field.default
        for field in FABRICATION_FIELDS.values()
        if field.default is not None
    }


FABRICATION_BASELINES = {
    DEFAULT_FABRICATION_BASELINE_ID: default_fabrication_context(),
}


def get_fabrication_baseline(
    baseline_id: str = DEFAULT_FABRICATION_BASELINE_ID,
) -> dict[str, Any]:
    """Return a copy of a versioned fabrication Baseline recipe."""

    try:
        return dict(FABRICATION_BASELINES[baseline_id])
    except KeyError as error:
        choices = ", ".join(sorted(FABRICATION_BASELINES))
        raise ValueError(f"baseline_id must be one of: {choices}") from error


def resolve_fabrication_context(values: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize a baseline plus the explicitly supplied overrides."""

    if not isinstance(values, Mapping):
        raise TypeError("fabrication_context must be a mapping")
    baseline_id = values.get("baseline_id")
    if not isinstance(baseline_id, str):
        choices = ", ".join(sorted(FABRICATION_BASELINES))
        raise ValueError(f"baseline_id must be one of: {choices}")

    schema_version = values.get("schema_version", FABRICATION_SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != FABRICATION_SCHEMA_VERSION:
        raise ValueError(
            "schema_version must equal the supported fabrication schema version "
            f"{FABRICATION_SCHEMA_VERSION}"
        )
    resolved = get_fabrication_baseline(baseline_id)
    resolved.update(values)
    return resolved


def fabrication_overrides(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return values that differ from the selected fabrication baseline."""

    values = resolve_fabrication_context(values)
    baseline_id = str(values["baseline_id"])
    baseline = get_fabrication_baseline(baseline_id)
    return {
        name: value
        for name, value in values.items()
        if name != "baseline_id" and baseline.get(name) != value
    }


def coerce_fabrication_value(name: str, value: str) -> str | int | float:
    """Convert one non-blank web/API string using the field schema."""

    field = FABRICATION_FIELDS.get(name)
    if field is None:
        raise ValueError(f"unknown fabrication context field: {name}")
    if field.kind == "integer":
        return int(value)
    if field.kind == "number":
        return float(value)
    return value


def validate_fabrication_context(values: Mapping[str, Any]) -> None:
    """Validate known fabrication fields without making them BO variables."""

    if not isinstance(values, Mapping):
        raise TypeError("fabrication_context must be a mapping")

    unknown = set(values) - set(FABRICATION_FIELDS)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"unknown fabrication context fields: {names}")

    baseline_id = values.get("baseline_id")
    if baseline_id not in FABRICATION_BASELINES:
        choices = ", ".join(sorted(FABRICATION_BASELINES))
        raise ValueError(f"baseline_id must be one of: {choices}")

    selection = values.get("electron_transport_selection")
    if selection not in {"sno2_ald", "bcp_evaporation"}:
        raise ValueError(
            "electron_transport_selection must choose exactly one of: "
            "sno2_ald, bcp_evaporation"
        )
    inactive_prefix = "bcp_" if selection == "sno2_ald" else "sno2_"
    inactive = sorted(name for name in values if name.startswith(inactive_prefix))
    if inactive:
        names = ", ".join(inactive)
        raise ValueError(f"inactive electron-transport fields must be omitted: {names}")

    for name, value in values.items():
        field = FABRICATION_FIELDS[name]
        if field.kind == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        elif field.kind == "number":
            if not isinstance(value, Real) or isinstance(value, bool):
                raise TypeError(f"{name} must be a real number")
            try:
                finite = math.isfinite(float(value))
            except OverflowError:
                finite = False
            if not finite or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        elif field.kind == "choice":
            if value not in field.choices:
                choices = ", ".join(field.choices)
                raise ValueError(f"{name} must be one of: {choices}")
        elif field.kind == "text":
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")
        else:
            raise ValueError(f"unsupported fabrication field kind: {field.kind}")
