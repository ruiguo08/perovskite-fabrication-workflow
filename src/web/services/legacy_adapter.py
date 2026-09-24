"""Convert grouped legacy recipes into independent condition snapshots."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, Mapping, Sequence

from perovskite_bo.device_recipe import DEVICE_RECIPE_SCHEMA_VERSION

from ..condition_snapshot import build_condition_snapshot
from ..device_layouts import DeviceLayout

DEFAULT_SUBSTRATE_COUNT = 3


def materialize_legacy_conditions(
    recipe_to_dict: Mapping[str, Any],
    experiment_code: str,
    *,
    layouts: Sequence[DeviceLayout],
    condition_plans: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return complete, single-configuration condition specifications.

    ``layouts`` is the caller's device-layout catalog (latest version per
    code, resolved from the database — the Python-side factory list is gone).
    Ambiguous historical facts are preserved as conservative defaults and
    marked ``requires_manual_review``. Such conditions cannot be released by
    the plan state machine until an explicit condition update resolves them.
    """
    if not layouts:
        raise ValueError(
            "no device layouts exist yet; an administrator must create them first"
        )
    layouts_by_code = {layout.code: layout for layout in layouts}

    device_recipe_value = recipe_to_dict.get("device_recipe")
    if not isinstance(device_recipe_value, Mapping):
        return []
    device_recipe = deepcopy(dict(device_recipe_value))
    device_recipe.setdefault("schema_version", DEVICE_RECIPE_SCHEMA_VERSION)
    groups = device_recipe.get("experimental_groups", [])
    if not isinstance(groups, list):
        return []

    inferred_layout, layout_is_ambiguous = _match_layout(layouts, 
        device_recipe.get("substrate", {})
    )
    plans_by_group = _condition_plans_by_group(condition_plans)
    used_plan_groups: set[str] = set()
    control_process = _extract_deposition_process(recipe_to_dict)
    control_layers = deepcopy(device_recipe.get("layers", []))
    conditions: list[dict[str, Any]] = []
    target_index = 0
    standalone_index = 0

    for group_value in groups:
        if not isinstance(group_value, Mapping):
            continue
        group = dict(group_value)
        group_id = str(group.get("group_id", "")).strip()
        kind = str(group.get("kind", "control"))
        name = str(group.get("name") or kind.title()).strip()
        explicit_plan = plans_by_group.get(group_id)
        if explicit_plan is None:
            layout = inferred_layout
            count = _substrate_count(group.get("substrate_count"))
            manual_review = layout_is_ambiguous
        else:
            used_plan_groups.add(group_id)
            layout_code = str(explicit_plan["device_layout_code"])
            layout = layouts_by_code.get(layout_code)
            if layout is None:
                raise ValueError(f"unknown device layout code: {layout_code!r}")
            _validate_layout_dimensions(layout, device_recipe.get("substrate", {}))
            count = _required_substrate_count(
                explicit_plan.get("planned_substrate_count")
            )
            manual_review = False
            if explicit_plan.get("role") != kind:
                raise ValueError(
                    f"condition plan role for {group_id!r} does not match recipe group"
                )

        if kind == "control":
            code = f"{experiment_code}-C"
            role = "control"
            layers = control_layers
            process = control_process
        elif kind == "target":
            target_index += 1
            code = f"{experiment_code}-T{target_index}"
            role = "target"
            group_layers = group.get("layers")
            layers = deepcopy(group_layers) if group_layers else control_layers
            process_value = group.get("deposition_process")
            process = (
                deepcopy(dict(process_value))
                if isinstance(process_value, Mapping)
                else control_process
            )
            # Free-form legacy adjustments do not contain enough typed path
            # information to deterministically mutate a full recipe.
            if not group_layers and group.get("adjustments"):
                manual_review = True
        elif kind == "standalone":
            standalone_index += 1
            suffix = "S" if standalone_index == 1 else f"S{standalone_index}"
            code = f"{experiment_code}-{suffix}"
            role = "standalone"
            layers = deepcopy(group.get("layers") or control_layers)
            process_value = group.get("deposition_process")
            process = (
                deepcopy(dict(process_value))
                if isinstance(process_value, Mapping)
                else control_process
            )
        else:
            continue

        snapshot = build_condition_snapshot(
            device_recipe,
            layers=layers,
            deposition_process=process,
        )
        conditions.append(
            {
                "role": role,
                "condition_code": code,
                "condition_name": name,
                "recipe_snapshot": snapshot,
                "source_baseline_version_id": None,
                "device_layout_code": layout.code,
                "planned_substrate_count": count,
                "requires_manual_review": manual_review,
            }
        )
    if plans_by_group and used_plan_groups != set(plans_by_group):
        unknown = sorted(set(plans_by_group) - used_plan_groups)
        raise ValueError(
            "condition plans do not match recipe groups: " + ", ".join(unknown)
        )
    if plans_by_group and len(conditions) != len(plans_by_group):
        raise ValueError("every recipe group requires exactly one condition plan")
    return conditions


def _condition_plans_by_group(
    values: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    if values is None:
        return {}
    plans: dict[str, Mapping[str, Any]] = {}
    for value in values:
        if not isinstance(value, Mapping):
            raise TypeError("condition plan must be a mapping")
        group_id = str(value.get("group_id", "")).strip()
        if not group_id:
            raise ValueError("condition plan group_id must not be blank")
        if group_id in plans:
            raise ValueError(f"duplicate condition plan for group {group_id!r}")
        role = str(value.get("role", ""))
        if role not in {"control", "target", "standalone"}:
            raise ValueError(f"unsupported condition plan role: {role!r}")
        plans[group_id] = value
    return plans


def _required_substrate_count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("planned substrate count must be a positive integer")
    return value


def _validate_layout_dimensions(
    layout: DeviceLayout,
    substrate: Mapping[str, Any] | Any,
) -> None:
    if not isinstance(substrate, Mapping):
        raise ValueError("condition layout requires recorded substrate dimensions")
    width = substrate.get("width_mm")
    length = substrate.get("length_mm")
    if width is None or length is None:
        raise ValueError("condition layout requires recorded substrate dimensions")
    if (
        layout.substrate_width_mm != Decimal(str(width))
        or layout.substrate_length_mm != Decimal(str(length))
    ):
        raise ValueError(
            f"device layout {layout.code!r} does not match the recorded substrate size"
        )


def _match_layout(
    layouts: Sequence[DeviceLayout],
    substrate: Mapping[str, Any] | Any,
) -> tuple[DeviceLayout, bool]:
    """Match dimensions against the DB catalog and report ambiguity.

    Without a dimension match (or with missing dimensions) the first catalog
    layout is a conservative placeholder flagged for manual review.
    """

    fallback = layouts[0]
    if not isinstance(substrate, Mapping):
        return fallback, True
    width = substrate.get("width_mm")
    length = substrate.get("length_mm")
    if width is None or length is None:
        return fallback, True
    matches = [
        layout
        for layout in layouts
        if layout.substrate_width_mm == Decimal(str(width))
        and layout.substrate_length_mm == Decimal(str(length))
    ]
    if len(matches) == 1:
        return matches[0], False
    if matches:
        return matches[0], True
    return fallback, True


def _substrate_count(value: Any) -> int:
    if isinstance(value, bool):
        return DEFAULT_SUBSTRATE_COUNT
    if isinstance(value, int) and value > 0:
        return value
    return DEFAULT_SUBSTRATE_COUNT


def _extract_deposition_process(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the structured process stored as legacy flat BO fields."""

    spin_steps: list[dict[str, Any]] = []
    for name in ("cast", "spread", "thin", "stage4"):
        rpm = recipe.get(f"spin_{name}_rpm")
        seconds = recipe.get(f"spin_{name}_seconds")
        acceleration = recipe.get(f"spin_{name}_acceleration_rpm_per_s")
        if rpm is None and seconds is None and acceleration is None:
            continue
        spin_steps.append(
            {
                "rpm": rpm,
                "seconds": seconds,
                "acceleration_rpm_per_s": acceleration,
            }
        )

    vcd_stages: list[dict[str, Any]] = []
    for index in range(1, 6):
        valve = recipe.get(f"vcd_stage{index}_valve")
        pressure = recipe.get(f"vcd_stage{index}_pressure_pa")
        seconds = recipe.get(f"vcd_stage{index}_seconds")
        if valve is None and pressure is None and seconds is None:
            continue
        vcd_stages.append(
            {"valve": valve, "pressure_pa": pressure, "seconds": seconds}
        )

    gas_backfill_stages: list[dict[str, Any]] = []
    for index in range(1, 6):
        prefix = f"gas_backfill_stage{index}"
        stage = {
            "gas": recipe.get(f"{prefix}_gas"),
            "flow_sccm": recipe.get(f"{prefix}_flow_sccm"),
            "target_pressure_pa": recipe.get(f"{prefix}_target_pressure_pa"),
            "hold_seconds": recipe.get(
                f"{prefix}_hold_seconds"
            ),
        }
        if all(value is None for value in stage.values()):
            continue
        gas_backfill_stages.append(stage)

    anneal_steps: list[dict[str, Any]] = []
    for index in range(1, 3):
        temperature = recipe.get(f"anneal_stage{index}_temperature_c")
        seconds = recipe.get(f"anneal_stage{index}_seconds")
        if temperature is None and seconds is None:
            continue
        anneal_steps.append(
            {"temperature_c": temperature, "seconds": seconds}
        )

    return {
        "method": "spin_coating_vcd",
        "spin_steps": spin_steps,
        "vcd_stages": vcd_stages,
        "gas_backfill_stages": gas_backfill_stages,
        "vcd_step_sequence": recipe.get("vcd_step_sequence") or [
            *(f"vcd_stage{index}" for index in range(1, len(vcd_stages) + 1)),
            *(
                f"gas_backfill_stage{index}"
                for index in range(1, len(gas_backfill_stages) + 1)
            ),
        ],
        "anneal_steps": anneal_steps,
    }
