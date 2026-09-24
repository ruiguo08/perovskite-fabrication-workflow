"""Validated device-stack recipes and deposition-process contracts."""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEVICE_RECIPE_SCHEMA_VERSION = 2
DEFAULT_BASELINE_SEED_ID = "ito_niox_spin_pcbm_sno2_v1"
MAX_SOLID_CHEMICALS = 20
MAX_SOLVENTS = 10
VCD_VALVES = ("VV02", "VV03", "VV06", "Pudi")

LayerType = Literal[
    "niox",
    "sam",
    "buried_interface",
    "sio2_np",
    "perovskite",
    "passivation",
    "peai",
    "edadi",
    "pcbm",
    "c60",
    "bcp",
    "sno2",
    "ag",
]
LayerRole = Literal[
    "htl",
    "buried_interface_modifier",
    "perovskite",
    "top_passivation",
    "etl",
    "top_electrode",
]
ExperimentGroupKind = Literal["control", "target", "standalone"]
SetupMode = Literal["baseline", "blank"]
SubstrateMaterial = Annotated[str, Field(min_length=1, max_length=160)]

LAYER_ROLE_BY_TYPE: dict[str, LayerRole] = {
    "niox": "htl",
    "sam": "htl",
    "buried_interface": "buried_interface_modifier",
    "sio2_np": "buried_interface_modifier",
    "perovskite": "perovskite",
    "passivation": "top_passivation",
    "peai": "top_passivation",
    "edadi": "top_passivation",
    "pcbm": "etl",
    "c60": "etl",
    "bcp": "etl",
    "sno2": "etl",
    "ag": "top_electrode",
}
LAYER_ROLE_ORDER = tuple(
    [
        "htl",
        "buried_interface_modifier",
        "perovskite",
        "top_passivation",
        "etl",
        "top_electrode",
    ]
)
_NIP_ROLE_ORDER = tuple(
    [
        "etl",
        "buried_interface_modifier",
        "perovskite",
        "top_passivation",
        "htl",
        "top_electrode",
    ]
)
REQUIRED_ROLES = ("htl", "perovskite", "etl", "top_electrode")


def layer_role_order(architecture: str) -> tuple[str, ...]:
    """Deposition role order for a device architecture.

    ``pin`` (inverted): HTL on the transparent electrode, ETL on top.
    ``nip`` (regular): ETL on the transparent electrode, HTL on top. The
    buried interface sits below the perovskite and the top passivation above
    it in both architectures; only the htl/etl positions swap.
    """
    if architecture == "nip":
        return _NIP_ROLE_ORDER
    return LAYER_ROLE_ORDER


def _default_experimental_groups() -> list[dict[str, Any]]:
    return [
        {
            "group_id": "control",
            "kind": "control",
            "name": "Control",
            "change_from_control": "Baseline fabrication procedure",
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


class RecipeModel(BaseModel):
    """Strict immutable base model for nested recipe data."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )


class SolidIngredient(RecipeModel):
    chemical: str = ""
    weight_mg: float | None = Field(default=None, gt=0)

    @field_validator("chemical")
    @classmethod
    def strip_chemical(cls, value: str) -> str:
        return value.strip()


class SolventIngredient(RecipeModel):
    solvent: str = ""
    volume_ml: float | None = Field(default=None, gt=0)

    @field_validator("solvent")
    @classmethod
    def strip_solvent(cls, value: str) -> str:
        return value.strip()


class SolutionRecipe(RecipeModel):
    formulation_type: Literal["weighed_solids", "diluted_dispersion"] = "weighed_solids"
    stock_dispersion: str = ""
    stock_volume_ml: float | None = Field(default=None, gt=0)
    solids: list[SolidIngredient] = Field(default_factory=list, max_length=MAX_SOLID_CHEMICALS)
    solvents: list[SolventIngredient] = Field(default_factory=list, max_length=MAX_SOLVENTS)

    @field_validator("stock_dispersion")
    @classmethod
    def strip_stock_dispersion(cls, value: str) -> str:
        return value.strip()


class SpinStep(RecipeModel):
    rpm: int | None = Field(default=None, gt=0)
    seconds: int | None = Field(default=None, gt=0)
    acceleration_rpm_per_s: int | None = Field(default=None, gt=0)


class AnnealStep(RecipeModel):
    temperature_c: int | None = Field(default=None, gt=0)
    seconds: int | None = Field(default=None, gt=0)


class VcdStage(RecipeModel):
    valve: str = ""
    pressure_pa: int | None = Field(default=None, ge=0)
    # 0 s = reach the pressure and move on without holding (VV03 pumps fast
    # and can overshoot a setpoint; a following VV06 row stabilizes it).
    seconds: int | None = Field(default=None, ge=0)

    @field_validator("valve")
    @classmethod
    def strip_valve(cls, value: str) -> str:
        return value.strip()


class VcdGasBackfillStage(RecipeModel):
    gas: str = ""
    flow_sccm: int | None = Field(default=None, gt=0)
    target_pressure_pa: int | None = Field(default=None, ge=0)
    # 0 s = reach the target pressure and move on without holding.
    hold_seconds: int | None = Field(default=None, ge=0)

    @field_validator("gas")
    @classmethod
    def strip_gas(cls, value: str) -> str:
        return value.strip()


class SpinCoatingProcess(RecipeModel):
    method: Literal["spin_coating"] = "spin_coating"
    spin_steps: list[SpinStep] = Field(default_factory=list, min_length=1, max_length=3)
    anneal_steps: list[AnnealStep] = Field(default_factory=list, max_length=2)


class SputteringProcess(RecipeModel):
    method: Literal["sputtering"] = "sputtering"
    sputter_mode: Literal["rf", "dc", "pulsed_dc"] = "rf"
    power_w: float | None = Field(default=None, gt=0)
    pressure_pa: float | None = Field(default=None, gt=0)
    gas1: str = ""
    gas1_flow_sccm: float | None = Field(default=None, gt=0)
    gas2: str = ""
    gas2_flow_sccm: float | None = Field(default=None, gt=0)
    duration_seconds: int | None = Field(default=None, gt=0)

    @field_validator("gas1", "gas2")
    @classmethod
    def strip_gas(cls, value: str) -> str:
        return value.strip()

class ThermalEvaporationProcess(RecipeModel):
    method: Literal["thermal_evaporation"] = "thermal_evaporation"
    thickness_nm: float | None = Field(default=None, gt=0)
    rate_angstrom_per_s: float | None = Field(default=None, gt=0)


class AldProcess(RecipeModel):
    method: Literal["ald"] = "ald"
    thickness_nm: float | None = Field(default=None, gt=0)
    substrate_temperature_c: float | None = Field(default=None, gt=0)
    cycles: int | None = Field(default=None, gt=0)


LayerProcess = Annotated[
    SpinCoatingProcess | SputteringProcess | ThermalEvaporationProcess | AldProcess,
    Field(discriminator="method"),
]


class PerovskiteDepositionProcess(RecipeModel):
    """Canonical perovskite process flattened into DepositionRecipe for BO."""

    method: Literal["spin_coating_vcd"] = "spin_coating_vcd"
    spin_steps: list[SpinStep] = Field(min_length=1, max_length=4)
    vcd_stages: list[VcdStage] = Field(min_length=1, max_length=5)
    gas_backfill_stages: list[VcdGasBackfillStage] = Field(
        default_factory=list,
        max_length=5,
    )
    vcd_step_sequence: list[str] = Field(default_factory=list, max_length=10)
    anneal_steps: list[AnnealStep] = Field(min_length=1, max_length=2)

    @model_validator(mode="before")
    @classmethod
    def default_vcd_step_sequence(cls, values: Any) -> Any:
        if not isinstance(values, dict) or "vcd_step_sequence" in values:
            return values
        migrated = dict(values)
        migrated["vcd_step_sequence"] = [
            *(f"vcd_stage{index}" for index, _ in enumerate(values.get("vcd_stages", []), 1)),
            *(
                f"gas_backfill_stage{index}"
                for index, _ in enumerate(values.get("gas_backfill_stages", []), 1)
            ),
        ]
        return migrated

    @model_validator(mode="after")
    def validate_vcd_step_sequence(self) -> PerovskiteDepositionProcess:
        expected = {
            *(f"vcd_stage{index}" for index in range(1, len(self.vcd_stages) + 1)),
            *(
                f"gas_backfill_stage{index}"
                for index in range(1, len(self.gas_backfill_stages) + 1)
            ),
        }
        if (
            len(self.vcd_step_sequence) != len(expected)
            or set(self.vcd_step_sequence) != expected
        ):
            raise ValueError(
                "vcd_step_sequence must contain every evacuation and gas "
                "backfill stage exactly once"
            )
        return self


def _require_complete_gas_backfill_stages(
    stages: list[VcdGasBackfillStage],
    *,
    prefix: str = "perovskite ",
) -> None:
    for index, stage in enumerate(stages, start=1):
        if (
            not stage.gas
            or stage.flow_sccm is None
            or stage.target_pressure_pa is None
            or stage.hold_seconds is None
        ):
            raise ValueError(f"{prefix}gas backfill stage {index} is incomplete")


class SubstrateRecipe(RecipeModel):
    material: SubstrateMaterial
    vendor: str = ""
    type_number: str = ""
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)

    @field_validator("material", "vendor", "type_number")
    @classmethod
    def strip_substrate_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_material(self) -> SubstrateRecipe:
        if not self.material:
            raise ValueError("substrate material must not be blank")
        return self


class GroupAdjustment(RecipeModel):
    parameter: str = ""
    parameter_label: str = ""
    control_value: str = ""
    target_value: str = ""

    @field_validator("parameter", "parameter_label", "control_value", "target_value")
    @classmethod
    def strip_adjustment_text(cls, value: str) -> str:
        return value.strip()


class ExperimentalGroup(RecipeModel):
    group_id: str
    kind: ExperimentGroupKind
    name: str
    change_from_control: str = ""
    inherits_control: bool = False
    adjustments: list[GroupAdjustment] = Field(default_factory=list, max_length=20)
    layers: list[DeviceLayer] | None = None
    deposition_process: PerovskiteDepositionProcess | None = None
    substrate_count: int | None = Field(default=None, gt=0)

    @field_validator("group_id", "name", "change_from_control")
    @classmethod
    def strip_group_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_group_text(self) -> ExperimentalGroup:
        if not self.group_id:
            raise ValueError("experimental group ID must not be blank")
        if not self.name:
            raise ValueError("experimental group name must not be blank")
        if self.kind == "control" and self.inherits_control:
            raise ValueError("the control group cannot inherit from itself")
        if self.kind == "control" and self.adjustments:
            raise ValueError("the control group cannot contain target adjustments")
        if self.kind == "control" and self.layers is not None:
            raise ValueError("the control group cannot contain its own layers")
        if self.kind == "control" and self.deposition_process is not None:
            raise ValueError("the control group cannot contain its own deposition process")
        if self.kind == "standalone" and self.inherits_control:
            raise ValueError("the standalone condition cannot inherit from control")
        if self.kind == "standalone" and self.adjustments:
            raise ValueError("the standalone condition cannot contain target adjustments")
        if self.kind == "standalone" and self.layers is not None:
            raise ValueError("the standalone condition uses the root layer stack")
        if self.kind == "standalone" and self.deposition_process is not None:
            raise ValueError("the standalone condition uses the root deposition process")
        if self.kind == "target" and self.layers is not None:
            if not self.layers:
                raise ValueError("target group layers must not be empty")
            _validate_layer_completeness(self.layers)
        if self.kind == "target" and not self.inherits_control and self.layers is None:
            raise ValueError("a non-inheriting target group requires its own complete layer stack")
        return self


class DeviceLayer(RecipeModel):
    layer_type: LayerType
    role: LayerRole | None = None
    name: str
    preset_id: str | None = None
    solution: SolutionRecipe | None = None
    process: LayerProcess | None = None

    @field_validator("name")
    @classmethod
    def strip_layer_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("layer name must not be blank")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_reference_id(cls, values: Any) -> Any:
        """Convert old ``reference_id`` key to ``preset_id``."""
        if not isinstance(values, dict):
            return values
        if "reference_id" in values and "preset_id" not in values:
            values["preset_id"] = values.pop("reference_id")
        return values

    @model_validator(mode="after")
    def validate_role(self) -> DeviceLayer:
        expected_role = LAYER_ROLE_BY_TYPE[self.layer_type]
        if self.role is not None and self.role != expected_role:
            raise ValueError(
                f"{self.layer_type} belongs to the {expected_role} role, not {self.role}"
            )
        if self.role is None:
            object.__setattr__(self, "role", expected_role)
        return self


def _validate_layer_completeness(layers: list[DeviceLayer]) -> None:
    """Architecture-independent layer checks: uniqueness, required roles,
    transport-layer exclusivity, and within-role material order.

    Used by the experimental-group validator, which runs before the parent
    DeviceRecipe validator and therefore does not yet know the architecture;
    the role-order check (which depends on architecture) is performed by
    validate_layer_sequence at the recipe level.
    """
    layer_types = [layer.layer_type for layer in layers]
    for unique_type in ("perovskite", "c60", "bcp", "sno2", "ag"):
        if layer_types.count(unique_type) > 1:
            raise ValueError(f"{unique_type} may appear only once in the device stack")

    transport_layers = [name for name in ("bcp", "sno2") if name in layer_types]
    if len(transport_layers) != 1:
        raise ValueError("device stack must contain exactly one of BCP or SnO2")
    if "c60" not in layer_types:
        raise ValueError("C60 is required in the ETL role")

    roles = [layer.role for layer in layers]
    missing_roles = [role for role in REQUIRED_ROLES if role not in roles]
    if missing_roles:
        raise ValueError(
            "device stack is missing required functional roles: "
            + ", ".join(missing_roles)
        )

    if len([layer for layer in layers if layer.role == "perovskite"]) != 1:
        raise ValueError("device stack must contain exactly one perovskite layer")
    if len([layer for layer in layers if layer.role == "top_electrode"]) != 1:
        raise ValueError("device stack must contain exactly one top electrode")

    material_order = {
        "htl": ["niox", "sam"],
        "buried_interface_modifier": ["buried_interface", "sio2_np"],
        "perovskite": ["perovskite"],
        "top_passivation": ["passivation", "peai", "edadi"],
        "etl": ["pcbm", "c60", transport_layers[0]],
        "top_electrode": ["ag"],
    }
    for role, expected_order in material_order.items():
        positions = {layer_type: index for index, layer_type in enumerate(expected_order)}
        actual_positions = [
            positions[layer.layer_type]
            for layer in layers
            if layer.role == role and layer.layer_type in positions
        ]
        if actual_positions != sorted(actual_positions):
            raise ValueError(f"{role} material layers are not in the required order")

    for layer in layers:
        _validate_layer_method(layer)


def validate_layer_sequence(layers: list[DeviceLayer], architecture: str = "pin") -> None:
    """Validate the order, completeness, and material constraints of a device-layer list.

    This is a standalone helper so it can be reused for both the control group's
    layer stack and any target group that carries its own full layer stack.

    The functional-role order depends on the device architecture: ``pin``
    (inverted) deposits the HTL first, ``nip`` (regular) deposits the ETL first.
    Spin-coated layers (NiOx, SAM, SiO2, passivation, PCBM) may be applied more
    than once. Perovskite, C60, the BCP/SnO2 transport layer, and the Ag top
    electrode must each appear exactly once.
    """
    _validate_layer_completeness(layers)
    roles = [layer.role for layer in layers]
    order = layer_role_order(architecture)
    role_indexes = [order.index(role) for role in roles]
    if role_indexes != sorted(role_indexes):
        raise ValueError("device layers are not in the required functional-role order")


class DeviceRecipe(RecipeModel):
    schema_version: Literal[DEVICE_RECIPE_SCHEMA_VERSION] = DEVICE_RECIPE_SCHEMA_VERSION
    setup_mode: SetupMode
    junction_type: Literal["single_junction", "tandem"] = "single_junction"
    perovskite_bandgap: Literal[
        "wide_bandgap",
        "normal_bandgap",
        "narrow_bandgap",
    ] | None = "normal_bandgap"
    tandem_type: Literal[
        "all_perovskite",
        "perovskite_silicon",
        "perovskite_cigs",
    ] | None = None
    architecture: Literal["pin", "nip"] = "pin"
    experimental_groups: list[ExperimentalGroup] = Field(
        default_factory=_default_experimental_groups,
    )
    substrate: SubstrateRecipe
    layers: list[DeviceLayer] = Field(min_length=5, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_data(cls, values: Any) -> Any:
        """Upgrade supported legacy DeviceRecipe JSON to the current shape."""
        if not isinstance(values, dict):
            return values
        values = dict(values)
        if values.get("setup_mode") == "reference":
            values["setup_mode"] = "baseline"
        if "stack_reference_id" in values:
            del values["stack_reference_id"]
        if values.get("schema_version") in (None, 1):
            values["schema_version"] = DEVICE_RECIPE_SCHEMA_VERSION
        return values

    @model_validator(mode="after")
    def validate_layer_sequence(self) -> DeviceRecipe:
        if self.junction_type != "single_junction":
            raise ValueError("tandem device setup will be added in a later workflow")
        if self.perovskite_bandgap != "normal_bandgap":
            raise ValueError(
                "only normal-bandgap single-junction perovskites are supported for now"
            )
        if self.tandem_type is not None:
            raise ValueError("tandem type must be blank for a single-junction device")

        control_groups = [group for group in self.experimental_groups if group.kind == "control"]
        target_groups = [group for group in self.experimental_groups if group.kind == "target"]
        standalone_groups = [
            group for group in self.experimental_groups if group.kind == "standalone"
        ]
        if standalone_groups:
            if len(standalone_groups) != 1 or len(self.experimental_groups) != 1:
                raise ValueError(
                    "a standalone plan must contain exactly one standalone condition"
                )
        else:
            if len(control_groups) != 1:
                raise ValueError("an experiment must contain exactly one control group")
            if not target_groups:
                raise ValueError("an experiment must contain at least one target group")
        group_ids = [group.group_id for group in self.experimental_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("experimental group IDs must be unique")

        validate_layer_sequence(self.layers, self.architecture)

        for group in self.experimental_groups:
            if group.kind == "target" and group.layers is not None:
                validate_layer_sequence(group.layers, self.architecture)
        return self


def _validate_layer_method(layer: DeviceLayer) -> None:
    allowed_methods = {
        "niox": {"spin_coating", "sputtering"},
        "sam": {"spin_coating"},
        "buried_interface": {"spin_coating"},
        "sio2_np": {"spin_coating"},
        "perovskite": set(),
        "passivation": {"spin_coating"},
        "peai": {"spin_coating"},
        "edadi": {"spin_coating"},
        "pcbm": {"spin_coating"},
        "c60": {"thermal_evaporation"},
        "bcp": {"thermal_evaporation"},
        "sno2": {"ald"},
        "ag": {"thermal_evaporation"},
    }
    process_method = None if layer.process is None else layer.process.method
    if layer.layer_type == "perovskite":
        if layer.process is not None:
            raise ValueError(
                "perovskite process must be stored in the canonical deposition recipe, not device_recipe"
            )
    elif process_method not in allowed_methods[layer.layer_type]:
        choices = ", ".join(sorted(allowed_methods[layer.layer_type]))
        raise ValueError(f"{layer.layer_type} deposition method must be one of: {choices}")

    needs_solution = process_method == "spin_coating" or layer.layer_type == "perovskite"
    if needs_solution and layer.solution is None:
        raise ValueError(f"{layer.layer_type} requires a solution recipe")
    if not needs_solution and layer.solution is not None:
        raise ValueError(f"{layer.layer_type} does not use a solution recipe")


def _require_complete_solution(layer: DeviceLayer) -> None:
    solution = layer.solution
    if solution is None:
        return
    if solution.formulation_type == "weighed_solids" and not solution.solids:
        raise ValueError(f"{layer.layer_type} requires at least one solid chemical")
    if solution.formulation_type == "diluted_dispersion":
        if not solution.stock_dispersion or solution.stock_volume_ml is None:
            raise ValueError(
                f"{layer.layer_type} diluted dispersion requires a stock name and volume in mL"
            )
    if not solution.solvents:
        raise ValueError(f"{layer.layer_type} requires at least one solvent")
    for index, ingredient in enumerate(solution.solids, start=1):
        if not ingredient.chemical or ingredient.weight_mg is None:
            raise ValueError(
                f"{layer.layer_type} solid chemical {index} requires a name and weight in mg"
            )
    for index, ingredient in enumerate(solution.solvents, start=1):
        if not ingredient.solvent or ingredient.volume_ml is None:
            raise ValueError(
                f"{layer.layer_type} solvent {index} requires a name and volume in mL"
            )


def _require_complete_process(layer: DeviceLayer) -> None:
    process = layer.process
    if process is None:
        return
    if isinstance(process, SpinCoatingProcess):
        for index, step in enumerate(process.spin_steps, start=1):
            if None in (step.rpm, step.seconds, step.acceleration_rpm_per_s):
                raise ValueError(f"{layer.layer_type} spin step {index} is incomplete")
        for index, step in enumerate(process.anneal_steps, start=1):
            if None in (step.temperature_c, step.seconds):
                raise ValueError(f"{layer.layer_type} anneal step {index} is incomplete")
        return
    if isinstance(process, SputteringProcess):
        if bool(process.gas2) != (process.gas2_flow_sccm is not None):
            raise ValueError(
                "sputtering gas 2 and its flow rate must be supplied together"
            )
        values = (
            process.sputter_mode,
            process.power_w,
            process.pressure_pa,
            process.gas1,
            process.gas1_flow_sccm,
            process.duration_seconds,
        )
    elif isinstance(process, ThermalEvaporationProcess):
        values = (
            process.thickness_nm,
            process.rate_angstrom_per_s,
        )
    else:
        values = (
            process.thickness_nm,
            process.substrate_temperature_c,
            process.cycles,
        )
    if any(value is None or value == "" for value in values):
        raise ValueError(f"{layer.layer_type} {process.method} process is incomplete")


def _require_complete_experimental_groups(recipe: DeviceRecipe) -> None:
    """Require every target-owned setup to be a complete experiment snapshot."""

    for group in recipe.experimental_groups:
        if group.kind != "target":
            continue
        if group.layers is not None:
            for layer in group.layers:
                _require_complete_solution(layer)
                _require_complete_process(layer)
            if group.deposition_process is None:
                raise ValueError(
                    f"{group.name} requires a complete perovskite deposition process"
                )
            _require_complete_deposition_process(group.name, group.deposition_process)
            continue
        if group.deposition_process is not None:
            _require_complete_deposition_process(group.name, group.deposition_process)
        if group.adjustments:
            seen_parameters: set[str] = set()
            for index, adjustment in enumerate(group.adjustments, start=1):
                if not adjustment.parameter:
                    raise ValueError(f"{group.name} adjustment {index} requires a control parameter")
                if not adjustment.control_value:
                    raise ValueError(f"{group.name} adjustment {index} requires the control value")
                if not adjustment.target_value:
                    raise ValueError(f"{group.name} adjustment {index} requires a target value")
                if adjustment.target_value == adjustment.control_value:
                    raise ValueError(
                        f"{group.name} adjustment {index} must differ from the control value"
                    )
                if adjustment.parameter in seen_parameters:
                    raise ValueError(
                        f"{group.name} contains the same adjusted parameter more than once"
                    )
                seen_parameters.add(adjustment.parameter)
            continue
        # Target inherits control fully with no explicit adjustments or layers —
        # it is valid as-is (the target uses the same recipe as the control).


def _require_complete_deposition_process(
    group_name: str,
    process: PerovskiteDepositionProcess,
) -> None:
    """Require a target group's perovskite process to be fully recorded."""

    for index, step in enumerate(process.spin_steps, start=1):
        if None in (step.rpm, step.seconds, step.acceleration_rpm_per_s):
            raise ValueError(f"{group_name} perovskite spin step {index} is incomplete")
    for index, stage in enumerate(process.vcd_stages, start=1):
        if stage.valve not in VCD_VALVES:
            raise ValueError(
                f"{group_name} perovskite VCD stage {index} valve must be one of: "
                + ", ".join(VCD_VALVES)
            )
        if stage.pressure_pa is None or stage.seconds is None:
            raise ValueError(f"{group_name} perovskite VCD stage {index} is incomplete")
    _require_complete_gas_backfill_stages(
        process.gas_backfill_stages,
        prefix=f"{group_name} perovskite ",
    )
    for index, step in enumerate(process.anneal_steps, start=1):
        if None in (step.temperature_c, step.seconds):
            raise ValueError(f"{group_name} perovskite anneal step {index} is incomplete")


def normalize_device_recipe(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate shape and order while allowing blank preset-template values."""

    if not isinstance(values, Mapping):
        raise TypeError("device_recipe must be a mapping")
    return DeviceRecipe.model_validate(values).model_dump(mode="python")


def validate_device_recipe(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a complete normalized device recipe suitable for persistence."""

    normalized = normalize_device_recipe(values)
    recipe = DeviceRecipe.model_validate(normalized)
    substrate = recipe.substrate
    if not substrate.vendor:
        raise ValueError("substrate vendor is required")
    if not substrate.type_number:
        raise ValueError("substrate SKU is required")
    if substrate.width_mm is None or substrate.length_mm is None:
        raise ValueError("substrate width and length are required")

    _require_complete_experimental_groups(recipe)
    for layer in recipe.layers:
        _require_complete_solution(layer)
        _require_complete_process(layer)
    return normalized


def validate_deposition_process(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the perovskite spin/VCD/annealing process shown in its layer card."""

    if not isinstance(values, Mapping):
        raise TypeError("deposition_process must be a mapping")
    process = PerovskiteDepositionProcess.model_validate(values)
    for index, step in enumerate(process.spin_steps, start=1):
        if None in (step.rpm, step.seconds, step.acceleration_rpm_per_s):
            raise ValueError(f"perovskite spin step {index} is incomplete")
    for index, stage in enumerate(process.vcd_stages, start=1):
        if stage.valve not in VCD_VALVES:
            raise ValueError(
                f"perovskite VCD stage {index} valve must be one of: {', '.join(VCD_VALVES)}"
            )
        if stage.pressure_pa is None or stage.seconds is None:
            raise ValueError(f"perovskite VCD stage {index} is incomplete")
    _require_complete_gas_backfill_stages(process.gas_backfill_stages)
    for index, step in enumerate(process.anneal_steps, start=1):
        if None in (step.temperature_c, step.seconds):
            raise ValueError(f"perovskite anneal step {index} is incomplete")
    return process.model_dump(mode="python")


def deposition_recipe_from_process(values: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a validated perovskite process into canonical BO recipe fields."""

    process = validate_deposition_process(values)
    recipe: dict[str, Any] = {}
    spin_names = ("cast", "spread", "thin", "stage4")
    for index, name in enumerate(spin_names):
        step = process["spin_steps"][index] if index < len(process["spin_steps"]) else None
        recipe[f"spin_{name}_rpm"] = None if step is None else step["rpm"]
        recipe[f"spin_{name}_seconds"] = None if step is None else step["seconds"]
        recipe[f"spin_{name}_acceleration_rpm_per_s"] = (
            None if step is None else step["acceleration_rpm_per_s"]
        )
    for index, stage in enumerate(process["vcd_stages"], start=1):
        recipe[f"vcd_stage{index}_valve"] = stage["valve"]
        recipe[f"vcd_stage{index}_pressure_pa"] = stage["pressure_pa"]
        recipe[f"vcd_stage{index}_seconds"] = stage["seconds"]
    for index in range(len(process["vcd_stages"]) + 1, 6):
        recipe[f"vcd_stage{index}_valve"] = None
        recipe[f"vcd_stage{index}_pressure_pa"] = None
        recipe[f"vcd_stage{index}_seconds"] = None
    for index, stage in enumerate(process["gas_backfill_stages"], start=1):
        prefix = f"gas_backfill_stage{index}"
        recipe[f"{prefix}_gas"] = stage["gas"]
        recipe[f"{prefix}_flow_sccm"] = stage["flow_sccm"]
        recipe[f"{prefix}_target_pressure_pa"] = stage["target_pressure_pa"]
        recipe[f"{prefix}_hold_seconds"] = stage[
            "hold_seconds"
        ]
    for index in range(len(process["gas_backfill_stages"]) + 1, 6):
        prefix = f"gas_backfill_stage{index}"
        recipe[f"{prefix}_gas"] = None
        recipe[f"{prefix}_flow_sccm"] = None
        recipe[f"{prefix}_target_pressure_pa"] = None
        recipe[f"{prefix}_hold_seconds"] = None
    recipe["vcd_step_sequence"] = list(process["vcd_step_sequence"])
    for index, step in enumerate(process["anneal_steps"], start=1):
        recipe[f"anneal_stage{index}_temperature_c"] = step["temperature_c"]
        recipe[f"anneal_stage{index}_seconds"] = step["seconds"]
    if len(process["anneal_steps"]) == 1:
        recipe["anneal_stage2_temperature_c"] = None
        recipe["anneal_stage2_seconds"] = None
    return recipe


def blank_device_recipe() -> dict[str, Any]:
    """Return the empty state used by the ground-up layer builder."""

    return {
        "schema_version": DEVICE_RECIPE_SCHEMA_VERSION,
        "setup_mode": "blank",
            # (removed: legacy_baseline_seed_id)
        "junction_type": "single_junction",
        "perovskite_bandgap": "normal_bandgap",
        "tandem_type": None,
        "experimental_groups": _default_experimental_groups(),
        "substrate": {
            "material": "ITO",
            "vendor": "",
            "type_number": "",
            "width_mm": 15,
            "length_mm": 15,
        },
        "layers": [],
    }


def device_stack_label(values: Mapping[str, Any]) -> str:
    """Create a concise material-order label from a validated device recipe."""

    recipe = DeviceRecipe.model_validate(values)
    names = [recipe.substrate.material]
    names.extend(layer.name for layer in recipe.layers)
    return " / ".join(names)
