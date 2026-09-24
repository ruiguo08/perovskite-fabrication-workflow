"""Typed representation of one perovskite deposition recipe."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from numbers import Real
from typing import Any, Mapping

from .device_recipe import VCD_VALVES, validate_device_recipe
from .fabrication import (
    default_fabrication_context,
    get_fabrication_baseline,
    resolve_fabrication_context,
    validate_fabrication_context,
)


class _FrozenDict(dict[str, Any]):
    """Small immutable, copyable dictionary for validated recipe context."""

    @staticmethod
    def _immutable(*args: Any, **kwargs: Any) -> None:
        raise TypeError("recipe context is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __copy__(self) -> _FrozenDict:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _FrozenDict:
        return self

    def __reduce__(self):
        return (type(self), (dict(self),))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


_SNO2_DEVICE_STACKS = (
    "FTO/4PADCB/PVK/PEAI/PCBM/C60/SnO2/Ag",
    "FTO/NiOx/4PADCB/PVK/PEAI/PCBM/C60/SnO2/Ag",
    "FTO/NiOx/Me-4PACz/PVK/PEAI/PCBM/C60/SnO2/Ag",
    "ITO/NiOx/4PADCB/SiO2/PVK/PEAI/PCBM/C60/SnO2/Ag",
    "ITO/NiOx/Me-4PACz/SiO2/PVK/PEAI/PCBM/C60/SnO2/Ag",
)
DEVICE_STACKS = _SNO2_DEVICE_STACKS + tuple(
    stack.replace("/SnO2/", "/BCP/") for stack in _SNO2_DEVICE_STACKS
)
_LEGACY_VCD_PRESSURE_FIELDS = (
    ("vcd_stage1_pressure_mbar", "vcd_stage1_pressure_pa"),
    ("vcd_stage2_pressure_mbar", "vcd_stage2_pressure_pa"),
    ("vcd_stage3_pressure_mbar", "vcd_stage3_pressure_pa"),
)


@dataclass(frozen=True)
class DepositionRecipe:
    """Canonical perovskite deposition parameters plus fixed device context.

    VCD pressure is persisted in Pa. Deprecated mbar constructor fields remain
    read-only compatibility aliases for existing code and stored recipe JSON.
    """

    spin_cast_rpm: int
    spin_cast_seconds: int
    spin_cast_acceleration_rpm_per_s: int

    spin_spread_rpm: int | None
    spin_spread_seconds: int | None
    spin_spread_acceleration_rpm_per_s: int | None

    spin_thin_rpm: int | None
    spin_thin_seconds: int | None
    spin_thin_acceleration_rpm_per_s: int | None

    vcd_stage1_valve: str
    vcd_stage1_seconds: int

    anneal_stage1_temperature_c: int
    anneal_stage1_seconds: int

    vcd_stage1_pressure_pa: int | None = None

    # Optional fourth perovskite spin stage. The original BO field names cover
    # cast/spread/thin; this additive field preserves the fourth structured
    # process stage without changing the existing optimization parameter space.
    spin_stage4_rpm: int | None = None
    spin_stage4_seconds: int | None = None
    spin_stage4_acceleration_rpm_per_s: int | None = None

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

    vcd_step_sequence: tuple[str, ...] | None = None

    anneal_stage2_temperature_c: int | None = None
    anneal_stage2_seconds: int | None = None

    # Optional defaults keep recipes already stored in SQLite readable.
    device_stack: str | None = None
    fabrication_context: Mapping[str, Any] | None = field(default=None, hash=False)
    device_recipe: Mapping[str, Any] | None = field(default=None, hash=False)

    # Read-time bookkeeping: gas-backfill stages migrated from legacy rows
    # whose dwell duration is unknown. Never serialized or compared.
    _legacy_partial_backfills: set[str] = field(
        default_factory=set,
        repr=False,
        compare=False,
    )

    # Deprecated input aliases. They are never emitted by to_dict().
    vcd_stage1_pressure_mbar: Real | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    vcd_stage2_pressure_mbar: Real | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    vcd_stage3_pressure_mbar: Real | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        self._canonicalize_vcd_pressures()
        # Read-time leniency for rows written before the d480d19 rename.
        # A legacy gas-backfill stage whose dwell time is unknown is kept
        # readable with hold_seconds=None instead of being rejected. The
        # write path (validate_deposition_process) still requires a complete
        # stage, so no incomplete data can be saved.
        self._adopt_legacy_hold_seconds_aliases()
        self._validate_spin_parameters()

        previous_vcd_stage_exists = True
        for index in range(1, 6):
            stage = f"vcd_stage{index}"
            exists = self._validate_vcd_stage(
                stage,
                valve=getattr(self, f"{stage}_valve"),
                pressure_pa=getattr(self, f"{stage}_pressure_pa"),
                seconds=getattr(self, f"{stage}_seconds"),
                required=index == 1,
            )
            if exists and not previous_vcd_stage_exists:
                raise ValueError(f"{stage} requires vcd_stage{index - 1}")
            previous_vcd_stage_exists = exists

        previous_backfill_stage_exists = True
        for index in range(1, 6):
            stage = f"gas_backfill_stage{index}"
            exists = self._validate_gas_backfill_stage(
                stage,
                allow_partial_hold=(
                    stage in self._legacy_partial_backfills
                ),
            )
            if exists and not previous_backfill_stage_exists:
                raise ValueError(f"{stage} requires gas_backfill_stage{index - 1}")
            previous_backfill_stage_exists = exists

        self._validate_vcd_step_sequence()

        self._require_positive_integer(
            "anneal_stage1_temperature_c",
            self.anneal_stage1_temperature_c,
        )
        self._require_positive_integer(
            "anneal_stage1_seconds",
            self.anneal_stage1_seconds,
        )
        self._validate_anneal_stage2()
        self._validate_context()

    def _canonicalize_vcd_pressures(self) -> None:
        for legacy_name, canonical_name in _LEGACY_VCD_PRESSURE_FIELDS:
            pressure_mbar = getattr(self, legacy_name)
            pressure_pa = getattr(self, canonical_name)
            if pressure_pa is None and pressure_mbar is not None:
                pressure_pa = self._mbar_to_integer_pa(legacy_name, pressure_mbar)
                object.__setattr__(self, canonical_name, pressure_pa)
            elif pressure_pa is not None and pressure_mbar is not None:
                expected_pa = self._mbar_to_integer_pa(legacy_name, pressure_mbar)
                if pressure_pa != expected_pa:
                    raise ValueError(f"{legacy_name} conflicts with {canonical_name}")
            if pressure_pa is not None and pressure_mbar is None:
                object.__setattr__(self, legacy_name, pressure_pa / 100)

    def _validate_spin_parameters(self) -> None:
        for name in (
            "spin_cast_rpm",
            "spin_cast_seconds",
            "spin_cast_acceleration_rpm_per_s",
        ):
            self._require_positive_integer(name, getattr(self, name))

        has_spread = self._validate_optional_spin_stage("spin_spread")
        has_thin = self._validate_optional_spin_stage("spin_thin")
        has_stage4 = self._validate_optional_spin_stage("spin_stage4")
        if has_thin and not has_spread:
            raise ValueError("spin_thin requires spin_spread")
        if has_stage4 and not has_thin:
            raise ValueError("spin_stage4 requires spin_thin")

    def _validate_optional_spin_stage(self, prefix: str) -> bool:
        values = {
            "rpm": getattr(self, f"{prefix}_rpm"),
            "seconds": getattr(self, f"{prefix}_seconds"),
            "acceleration_rpm_per_s": getattr(
                self,
                f"{prefix}_acceleration_rpm_per_s",
            ),
        }
        supplied = self._validate_optional_stage(prefix, **values)
        if not supplied:
            return False
        for suffix, value in values.items():
            assert value is not None
            self._require_positive_integer(f"{prefix}_{suffix}", value)
        return True

    @classmethod
    def _validate_vcd_stage(
        cls,
        stage: str,
        *,
        valve: str | None,
        pressure_pa: int | None,
        seconds: int | None,
        required: bool = False,
    ) -> bool:
        supplied = cls._validate_optional_stage(
            stage,
            valve=valve,
            pressure_pa=pressure_pa,
            seconds=seconds,
        )
        if required and not supplied:
            raise ValueError(f"{stage} is required")
        if not supplied:
            return False

        assert valve is not None
        assert pressure_pa is not None
        assert seconds is not None
        if valve not in VCD_VALVES:
            choices = ", ".join(sorted(VCD_VALVES))
            raise ValueError(f"{stage}_valve must be one of: {choices}")
        cls._require_non_negative_integer(f"{stage}_pressure_pa", pressure_pa)
        cls._require_non_negative_integer(f"{stage}_seconds", seconds)
        return True

    def _validate_gas_backfill_stage(
        self,
        stage: str,
        *,
        allow_partial_hold: bool = False,
    ) -> bool:
        gas = getattr(self, f"{stage}_gas")
        flow_sccm = getattr(self, f"{stage}_flow_sccm")
        target_pressure_pa = getattr(self, f"{stage}_target_pressure_pa")
        hold_seconds = getattr(self, f"{stage}_hold_seconds")
        if allow_partial_hold and hold_seconds is None:
            # Legacy rows written before the d480d19 rename recorded the
            # backfill target but not the dwell duration. Keep them readable
            # by accepting the stage without a hold time.
            supplied = self._validate_optional_stage(
                stage,
                gas=gas,
                flow_sccm=flow_sccm,
                target_pressure_pa=target_pressure_pa,
            )
            if not supplied:
                return False
            assert gas is not None
            assert flow_sccm is not None
            assert target_pressure_pa is not None
            if not isinstance(gas, str) or not gas.strip():
                raise ValueError(f"{stage}_gas must be a non-blank string")
            # Read-time leniency: rows written before flows became integer
            # sccm may hold decimal MFC values. New writes are gated to
            # integers by the pydantic VcdGasBackfillStage model.
            self._require_positive_real(f"{stage}_flow_sccm", flow_sccm)
            self._require_non_negative_integer(
                f"{stage}_target_pressure_pa",
                target_pressure_pa,
            )
            return True

        supplied = self._validate_optional_stage(
            stage,
            gas=gas,
            flow_sccm=flow_sccm,
            target_pressure_pa=target_pressure_pa,
            hold_seconds=hold_seconds,
        )
        if not supplied:
            return False

        assert gas is not None
        assert flow_sccm is not None
        assert target_pressure_pa is not None
        assert hold_seconds is not None
        if not isinstance(gas, str) or not gas.strip():
            raise ValueError(f"{stage}_gas must be a non-blank string")
        self._require_positive_real(f"{stage}_flow_sccm", flow_sccm)
        self._require_non_negative_integer(
            f"{stage}_target_pressure_pa",
            target_pressure_pa,
        )
        self._require_non_negative_integer(
            f"{stage}_hold_seconds",
            hold_seconds,
        )
        return True

    def _validate_vcd_step_sequence(self) -> None:
        expected = {
            *(
                f"vcd_stage{index}"
                for index in range(1, 6)
                if getattr(self, f"vcd_stage{index}_valve") is not None
            ),
            *(
                f"gas_backfill_stage{index}"
                for index in range(1, 6)
                if getattr(self, f"gas_backfill_stage{index}_gas") is not None
            ),
        }
        sequence = self.vcd_step_sequence
        if sequence is None:
            sequence = tuple(
                [key for key in sorted(expected) if key.startswith("vcd_stage")]
                + [
                    key
                    for key in sorted(expected)
                    if key.startswith("gas_backfill_stage")
                ]
            )
            object.__setattr__(self, "vcd_step_sequence", sequence)
        if len(sequence) != len(expected) or set(sequence) != expected:
            raise ValueError(
                "vcd_step_sequence must contain every evacuation and gas "
                "backfill stage exactly once"
            )

    def _validate_anneal_stage2(self) -> None:
        supplied = self._validate_optional_stage(
            "anneal_stage2",
            temperature_c=self.anneal_stage2_temperature_c,
            seconds=self.anneal_stage2_seconds,
        )
        if not supplied:
            return
        assert self.anneal_stage2_temperature_c is not None
        assert self.anneal_stage2_seconds is not None
        self._require_positive_integer(
            "anneal_stage2_temperature_c",
            self.anneal_stage2_temperature_c,
        )
        self._require_positive_integer(
            "anneal_stage2_seconds",
            self.anneal_stage2_seconds,
        )

    def _validate_context(self) -> None:
        if self.fabrication_context is not None and self.device_recipe is not None:
            raise ValueError(
                "use device_recipe for new experiments; fabrication_context is legacy-only"
            )

        if self.fabrication_context is not None:
            validate_fabrication_context(self.fabrication_context)
            resolved_context = resolve_fabrication_context(self.fabrication_context)
            validate_fabrication_context(resolved_context)
            object.__setattr__(
                self,
                "fabrication_context",
                _freeze(resolved_context),
            )

        if self.device_recipe is not None:
            resolved_device_recipe = validate_device_recipe(self.device_recipe)
            object.__setattr__(
                self,
                "device_recipe",
                _freeze(resolved_device_recipe),
            )

        if self.device_stack is not None and (
            not isinstance(self.device_stack, str) or not self.device_stack.strip()
        ):
            raise ValueError("device_stack must be a non-blank string")
        if self.device_stack is not None and self.device_stack not in DEVICE_STACKS:
            choices = ", ".join(DEVICE_STACKS)
            raise ValueError(f"device_stack must be one of: {choices}")

        if self.device_stack is not None and self.fabrication_context is not None:
            selection = self.fabrication_context.get("electron_transport_selection")
            if selection == "sno2_ald" and "/BCP/" in self.device_stack:
                raise ValueError(
                    "device_stack selects BCP but fabrication_context selects SnO2"
                )
            if selection == "bcp_evaporation" and "/SnO2/" in self.device_stack:
                raise ValueError(
                    "device_stack selects SnO2 but fabrication_context selects BCP"
                )

    @staticmethod
    def _require_positive_integer(name: str, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")

    @staticmethod
    def _require_non_negative_integer(name: str, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    @staticmethod
    def _require_positive_real(name: str, value: Real) -> None:
        if not isinstance(value, Real) or isinstance(value, bool):
            raise TypeError(f"{name} must be a real number")
        if not math.isfinite(float(value)) or value <= 0:
            raise ValueError(f"{name} must be finite and greater than zero")

    @staticmethod
    def _validate_optional_stage(stage: str, **values: Any | None) -> bool:
        supplied = [value is not None for value in values.values()]
        if any(supplied) and not all(supplied):
            names = ", ".join(values)
            raise ValueError(f"{stage} must define all or none of: {names}")
        return all(supplied)

    def to_dict(self) -> dict[str, Any]:
        """Return canonical JSON data; deprecated mbar aliases are omitted."""

        legacy_names = {name for name, _ in _LEGACY_VCD_PRESSURE_FIELDS}
        excluded_names = legacy_names | {"_legacy_partial_backfills"}
        values = {
            recipe_field.name: getattr(self, recipe_field.name)
            for recipe_field in fields(self)
            if recipe_field.name not in excluded_names
        }
        if self.fabrication_context is not None:
            values["fabrication_context"] = _thaw(self.fabrication_context)
        if self.device_recipe is not None:
            values["device_recipe"] = _thaw(self.device_recipe)
        if self.vcd_step_sequence is not None:
            values["vcd_step_sequence"] = list(self.vcd_step_sequence)
        return values

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> DepositionRecipe:
        """Construct a recipe while migrating deprecated aliases."""

        if not isinstance(values, Mapping):
            raise TypeError("recipe values must be a mapping")
        migrated = dict(values)
        if isinstance(migrated.get("vcd_step_sequence"), list):
            migrated["vcd_step_sequence"] = tuple(migrated["vcd_step_sequence"])
        cls._migrate_vcd_pressure_aliases(migrated)
        cls._migrate_legacy_pvk_aliases(migrated)
        cls._drop_legacy_hold_seconds_aliases(migrated)
        return cls(**migrated)

    @staticmethod
    def _mbar_to_integer_pa(name: str, value: Real) -> int:
        if not isinstance(value, Real) or isinstance(value, bool):
            raise TypeError(f"{name} must be a real number")
        converted_value = float(value) * 100
        if not math.isfinite(converted_value) or not converted_value.is_integer():
            raise ValueError(f"{name} must convert exactly to an integer number of Pa")
        return int(converted_value)

    @staticmethod
    def _migrate_vcd_pressure_aliases(values: dict[str, Any]) -> None:
        for legacy_name, canonical_name in _LEGACY_VCD_PRESSURE_FIELDS:
            legacy_value = values.pop(legacy_name, None)
            canonical_value = values.get(canonical_name)
            if legacy_value is None:
                continue
            converted_value = DepositionRecipe._mbar_to_integer_pa(
                legacy_name,
                legacy_value,
            )
            if canonical_value is not None and canonical_value != converted_value:
                raise ValueError(f"{legacy_name} conflicts with {canonical_name}")
            values[canonical_name] = converted_value

    @staticmethod
    def _migrate_legacy_pvk_aliases(migrated: dict[str, Any]) -> None:
        legacy_fields = {
            "precursor_solvent": "pvk_solvent",
            "perovskite_concentration_m": "pvk_solution_concentration",
            "rbscn_percent": "pvk_rbscn_percent",
            "pb_scn2_percent": "pvk_pb_scn2_percent",
        }
        legacy_values = {
            old_name: migrated.pop(old_name)
            for old_name in legacy_fields
            if old_name in migrated and migrated[old_name] is not None
        }
        for old_name in legacy_fields:
            migrated.pop(old_name, None)
        if not legacy_values:
            return
        if migrated.get("device_recipe") is not None:
            raise ValueError(
                "deprecated top-level PVK fields cannot be combined with device_recipe"
            )

        supplied_context = migrated.get("fabrication_context")
        if supplied_context is None:
            context = default_fabrication_context()
        elif isinstance(supplied_context, Mapping):
            context = dict(supplied_context)
        else:
            raise TypeError("fabrication_context must be a mapping")

        baseline_id = str(context.get("baseline_id", ""))
        baseline = get_fabrication_baseline(baseline_id)
        device_stack = migrated.get("device_stack")
        if isinstance(device_stack, str) and "/BCP/" in device_stack:
            selection = context.get("electron_transport_selection")
            baseline_selection = baseline.get("electron_transport_selection")
            if selection in (None, baseline_selection):
                context["electron_transport_selection"] = "bcp_evaporation"

        for old_name, legacy_value in legacy_values.items():
            canonical_name = legacy_fields[old_name]
            current_value = context.get(canonical_name)
            baseline_value = baseline.get(canonical_name)
            if (
                current_value is not None
                and current_value != legacy_value
                and current_value != baseline_value
            ):
                raise ValueError(
                    f"{old_name} conflicts with fabrication_context.{canonical_name}"
                )
            context[canonical_name] = legacy_value

        if "perovskite_concentration_m" in legacy_values:
            concentration_unit = context.get("pvk_solution_concentration_unit")
            if concentration_unit not in (None, "mol/L"):
                raise ValueError(
                    "perovskite_concentration_m conflicts with "
                    "fabrication_context.pvk_solution_concentration_unit"
                )
            context["pvk_solution_concentration_unit"] = "mol/L"
        migrated["fabrication_context"] = context

    @staticmethod
    def _drop_legacy_hold_seconds_aliases(migrated: dict[str, Any]) -> None:
        """Remove the obsolete pre-d480d19 ``post_fill_end_pressure_pa`` keys.

        These keys are not dataclass fields and must be removed before
        construction. Their presence means the dwell duration is unknown, so
        ``__post_init__`` records the affected stage as a legacy partial
        backfill and keeps it readable.
        """

        for index in range(1, 6):
            legacy_name = f"gas_backfill_stage{index}_post_fill_end_pressure_pa"
            migrated.pop(legacy_name, None)

    def _adopt_legacy_hold_seconds_aliases(self) -> set[str]:
        """Record gas-backfill stages whose dwell time is unknown (legacy).

        Commit ``d480d19`` replaced the gas-backfill "post-fill end pressure"
        (a pressure that duplicated the target) with ``hold_seconds``, the
        dwell time in seconds at the target pressure. The two units are not
        interconvertible, so a legacy value cannot be migrated losslessly and
        must not be reinterpreted as a duration. This method records which
        stages are missing their dwell time so ``__post_init__`` can keep
        them readable with ``hold_seconds=None`` instead of rejecting them.
        The dwell is left blank for the operator to record; the write path
        still requires a complete stage.
        """

        legacy_partial: set[str] = set()
        for index in range(1, 6):
            stage = f"gas_backfill_stage{index}"
            if (
                getattr(self, f"{stage}_gas", None) is not None
                and getattr(self, f"{stage}_hold_seconds", None) is None
            ):
                legacy_partial.add(stage)
        object.__setattr__(self, "_legacy_partial_backfills", legacy_partial)
        return legacy_partial
