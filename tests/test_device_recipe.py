"""Tests for stack references, nested solution recipes and Pa-based VCD."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from pydantic import ValidationError

from perovskite_bo import (
    MAX_SOLID_CHEMICALS,
    MAX_SOLVENTS,
    DepositionRecipe,
    deposition_recipe_from_process,
    validate_deposition_process,
    validate_device_recipe,
)
from tests.recipe_fixtures import (
    FACTORY_BASELINE_SEEDS as BUILTIN_BASELINE_SEEDS,
    FACTORY_LAYER_PRESETS as LAYER_PRESETS,
)


def complete_reference(reference_id: str) -> tuple[dict, dict]:
    reference = deepcopy(BUILTIN_BASELINE_SEEDS[reference_id])
    device_recipe = reference["device_recipe"]
    deposition_process = reference["deposition_process"]
    device_recipe["substrate"]["vendor"] = "Example vendor"
    device_recipe["substrate"]["type_number"] = "ITO-15"
    for group in device_recipe["experimental_groups"]:
        if group["kind"] == "target":
            group["inherits_control"] = True
            group["adjustments"] = [
                {
                    "parameter": "device_recipe.substrate.width_mm",
                    "parameter_label": "Substrate · Width (mm)",
                    "control_value": "15",
                    "target_value": "25",
                }
            ]
    for layer in device_recipe["layers"]:
        solution = layer.get("solution")
        if solution:
            if solution.get("formulation_type") == "diluted_dispersion":
                solution["stock_dispersion"] = "SiO2 NP stock dispersion"
                solution["stock_volume_ml"] = 0.1
                solution["solids"] = []
            else:
                solution["solids"] = [
                    {
                        "chemical": f"{layer['name']} solid",
                        "weight_mg": 10.0,
                    }
                ]
            solution["solvents"] = [
                {
                    "solvent": "Example solvent",
                    "volume_ml": 1.0,
                }
            ]
        process = layer.get("process")
        if not process:
            continue
        if process["method"] == "sputtering":
            process.update(
                {
                    "power_w": 100.0,
                    "pressure_pa": 1.0,
                    "gas1": "Ar",
                    "gas1_flow_sccm": 20.0,
                    "gas2": "O2",
                    "gas2_flow_sccm": 5.0,
                    "duration_seconds": 60,
                }
            )
        elif process["method"] == "thermal_evaporation":
            process.update(
                {
                    "thickness_nm": 20.0,
                    "rate_angstrom_per_s": 0.2,
                }
            )
        elif process["method"] == "ald":
            process.update(
                {
                    "thickness_nm": 20.0,
                    "substrate_temperature_c": 80.0,
                    "cycles": 100,
                }
            )
        elif process["method"] == "spin_coating":
            for step in process["spin_steps"]:
                step["rpm"] = step["rpm"] or 3000
                step["seconds"] = step["seconds"] or 30
                step["acceleration_rpm_per_s"] = (
                    step["acceleration_rpm_per_s"] or 1000
                )
            for step in process["anneal_steps"]:
                step["temperature_c"] = step["temperature_c"] or 100
                step["seconds"] = step["seconds"] or 600
    for index, stage in enumerate(deposition_process["vcd_stages"]):
        stage["valve"] = ("VV02", "VV03", "VV06")[index]
    return device_recipe, deposition_process


class DeviceRecipeTests(unittest.TestCase):
    def test_catalog_defined_substrate_material_is_accepted(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        device_recipe["substrate"]["material"] = "AZO-coated glass"

        normalized = validate_device_recipe(device_recipe)

        self.assertEqual(normalized["substrate"]["material"], "AZO-coated glass")

    def test_schema_version_1_is_migrated_to_current_shape(self) -> None:
        device_recipe, deposition_process = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        device_recipe["schema_version"] = 1
        device_recipe["setup_mode"] = "reference"
        device_recipe["stack_reference_id"] = "legacy-stack"
        first_layer = device_recipe["layers"][0]
        first_layer["reference_id"] = first_layer.pop("preset_id", None)

        normalized = validate_device_recipe(device_recipe)
        restored = DepositionRecipe.from_mapping(
            {
                **deposition_recipe_from_process(deposition_process),
                "device_recipe": device_recipe,
            }
        )

        self.assertEqual(normalized["schema_version"], 2)
        self.assertEqual(normalized["setup_mode"], "baseline")
        self.assertNotIn("stack_reference_id", normalized)
        self.assertIn("preset_id", normalized["layers"][0])
        self.assertEqual(restored.device_recipe["schema_version"], 2)

    def test_builtin_baselines_defer_supplier_identity_to_the_directory(self) -> None:
        for baseline in BUILTIN_BASELINE_SEEDS.values():
            self.assertEqual(baseline["device_recipe"]["substrate"]["vendor"], "")
            self.assertEqual(
                baseline["device_recipe"]["substrate"]["type_number"], ""
            )

    def test_stack_references_cover_every_requested_stack_choice(self) -> None:
        self.assertEqual(len(BUILTIN_BASELINE_SEEDS), 24)
        labels = {reference["label"] for reference in BUILTIN_BASELINE_SEEDS.values()}
        self.assertEqual(len(labels), 24)
        self.assertEqual(
            BUILTIN_BASELINE_SEEDS["fto_niox_skip_pcbm_bcp_v1"]["label"],
            "FTO / SAM / with PCBM / BCP",
        )
        self.assertEqual(
            BUILTIN_BASELINE_SEEDS["ito_niox_spin_pcbm_sno2_v1"]["label"],
            "ITO / spin-coated NiOx / SAM / with PCBM / SNO2",
        )

        for substrate in ("ito", "fto"):
            for niox in ("skip", "spin", "sputter"):
                for pcbm in ("pcbm", "no_pcbm"):
                    for transport in ("bcp", "sno2"):
                        reference_id = (
                            f"{substrate}_niox_{niox}_{pcbm}_{transport}_v1"
                        )
                        self.assertIn(reference_id, BUILTIN_BASELINE_SEEDS)

    def test_complete_reference_validates_with_ordered_layers(self) -> None:
        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )

        normalized = validate_device_recipe(device_recipe)

        self.assertEqual(normalized["substrate"]["material"], "ITO")
        self.assertEqual(
            [layer["layer_type"] for layer in normalized["layers"]],
            [
                "niox",
                "sam",
                "sio2_np",
                "perovskite",
                "peai",
                "pcbm",
                "c60",
                "sno2",
                "ag",
            ],
        )

    def test_optional_niox_and_pcbm_can_both_be_skipped(self) -> None:
        device_recipe, _ = complete_reference(
            "fto_niox_skip_no_pcbm_bcp_v1"
        )

        normalized = validate_device_recipe(device_recipe)

        self.assertEqual(
            [layer["layer_type"] for layer in normalized["layers"]],
            [
                "sam",
                "sio2_np",
                "perovskite",
                "peai",
                "c60",
                "bcp",
                "ag",
            ],
        )

    def test_buried_interface_and_top_passivation_are_optional(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        device_recipe["layers"] = [
            layer
            for layer in device_recipe["layers"]
            if layer["role"] not in {"buried_interface_modifier", "top_passivation"}
        ]

        normalized = validate_device_recipe(device_recipe)

        roles = {layer["role"] for layer in normalized["layers"]}
        self.assertNotIn("buried_interface_modifier", roles)
        self.assertNotIn("top_passivation", roles)

    def test_invalid_layer_order_is_rejected(self) -> None:
        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        device_recipe["layers"][1], device_recipe["layers"][2] = (
            device_recipe["layers"][2],
            device_recipe["layers"][1],
        )

        with self.assertRaisesRegex(ValueError, "functional-role order"):
            validate_device_recipe(device_recipe)

    def test_nip_architecture_requires_etl_first_order(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        # The reference stack is in pin order (HTL first); pin (the default) validates.
        validate_device_recipe(device_recipe)

        # Declaring nip without reordering rejects the pin-ordered stack.
        device_recipe["architecture"] = "nip"
        with self.assertRaisesRegex(ValueError, "functional-role order"):
            validate_device_recipe(device_recipe)

        # Reorder to nip deposition order (ETL on the transparent electrode,
        # HTL near the top electrode) -> accepted.
        nip_role_order = {
            "etl": 0,
            "buried_interface_modifier": 1,
            "perovskite": 2,
            "top_passivation": 3,
            "htl": 4,
            "top_electrode": 5,
        }
        device_recipe["layers"].sort(
            key=lambda layer: nip_role_order.get(layer["role"], 99)
        )
        validate_device_recipe(device_recipe)

    def test_solution_limits_are_enforced(self) -> None:
        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        sam = next(
            layer
            for layer in device_recipe["layers"]
            if layer["layer_type"] == "sam"
        )
        sam["solution"]["solids"] = [
            {"chemical": f"chemical-{index}", "weight_mg": 1.0}
            for index in range(MAX_SOLID_CHEMICALS + 1)
        ]

        with self.assertRaises(ValidationError):
            validate_device_recipe(device_recipe)

        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        sam = next(
            layer
            for layer in device_recipe["layers"]
            if layer["layer_type"] == "sam"
        )
        sam["solution"]["solvents"] = [
            {"solvent": f"solvent-{index}", "volume_ml": 1.0}
            for index in range(MAX_SOLVENTS + 1)
        ]
        with self.assertRaises(ValidationError):
            validate_device_recipe(device_recipe)

    def test_each_solution_requires_quantified_ingredients(self) -> None:
        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        perovskite = next(
            layer
            for layer in device_recipe["layers"]
            if layer["layer_type"] == "perovskite"
        )
        perovskite["solution"]["solids"][0]["weight_mg"] = None

        with self.assertRaisesRegex(ValueError, "weight in mg"):
            validate_device_recipe(device_recipe)

    def test_diluted_dispersion_does_not_require_weighed_solids(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        buried_interface = next(
            layer for layer in device_recipe["layers"]
            if layer["layer_type"] == "sio2_np"
        )

        normalized = validate_device_recipe(device_recipe)

        self.assertEqual(buried_interface["solution"]["solids"], [])
        normalized_layer = next(
            layer for layer in normalized["layers"]
            if layer["layer_type"] == "sio2_np"
        )
        self.assertEqual(
            normalized_layer["solution"]["formulation_type"],
            "diluted_dispersion",
        )

    def test_diluted_dispersion_requires_stock_volume(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        buried_interface = next(
            layer for layer in device_recipe["layers"]
            if layer["layer_type"] == "sio2_np"
        )
        buried_interface["solution"]["stock_volume_ml"] = None

        with self.assertRaisesRegex(ValueError, "stock name and volume"):
            validate_device_recipe(device_recipe)

    def test_perovskite_process_flattens_to_pascal_recipe_fields(self) -> None:
        _, process = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )

        values = deposition_recipe_from_process(process)

        self.assertEqual(values["vcd_stage1_pressure_pa"], 900)
        self.assertEqual(values["vcd_stage2_pressure_pa"], 600)
        self.assertEqual(values["vcd_stage3_pressure_pa"], 300)
        self.assertNotIn("vcd_stage1_pressure_mbar", values)
        self.assertEqual(values["anneal_stage2_temperature_c"], 60)
        self.assertEqual(values["spin_cast_rpm"], 1000)
        self.assertIsNone(values["spin_spread_rpm"])
        self.assertIsNone(values["spin_thin_rpm"])

    def test_four_spin_stages_round_trip_without_losing_the_final_stage(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["spin_steps"] = [
            {"rpm": 500, "seconds": 5, "acceleration_rpm_per_s": 100},
            {"rpm": 1000, "seconds": 10, "acceleration_rpm_per_s": 200},
            {"rpm": 3000, "seconds": 20, "acceleration_rpm_per_s": 1000},
            {"rpm": 5000, "seconds": 30, "acceleration_rpm_per_s": 2000},
        ]

        values = deposition_recipe_from_process(process)
        restored = DepositionRecipe.from_mapping(values)

        self.assertEqual(values["spin_stage4_rpm"], 5000)
        self.assertEqual(values["spin_stage4_seconds"], 30)
        self.assertEqual(values["spin_stage4_acceleration_rpm_per_s"], 2000)
        self.assertEqual(restored.spin_stage4_rpm, 5000)

    def test_five_vcd_and_gas_backfill_stages_round_trip(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["vcd_stages"] = [
            {
                "valve": ("VV02", "VV03", "VV06", "Pudi", "VV02")[index],
                "pressure_pa": (1000, 400, 150, 10, 1)[index],
                "seconds": (5, 5, 10, 5, 0)[index],
            }
            for index in range(5)
        ]
        process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30 + index,
                "target_pressure_pa": 15 + index * 10,
                "hold_seconds": 20 + index * 10,
            }
            for index in range(5)
        ]
        process["vcd_step_sequence"] = [
            step
            for index in range(1, 6)
            for step in (f"vcd_stage{index}", f"gas_backfill_stage{index}")
        ]

        values = deposition_recipe_from_process(process)
        restored = DepositionRecipe.from_mapping(values)

        self.assertEqual(values["vcd_stage5_pressure_pa"], 1)
        self.assertEqual(values["vcd_stage5_seconds"], 0)
        self.assertEqual(values["gas_backfill_stage1_flow_sccm"], 30)
        self.assertEqual(
            values["gas_backfill_stage5_hold_seconds"],
            60,
        )
        self.assertEqual(restored.vcd_stage5_pressure_pa, 1)
        self.assertEqual(restored.gas_backfill_stage5_gas, "N2")
        self.assertEqual(restored.vcd_step_sequence, tuple(process["vcd_step_sequence"]))

    def test_vcd_and_gas_backfill_are_limited_to_five_stages(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["vcd_stages"] = [
            {"valve": "VV02", "pressure_pa": 10, "seconds": 5}
        ] * 6
        with self.assertRaises(ValidationError):
            validate_deposition_process(process)

        process["vcd_stages"] = process["vcd_stages"][:5]
        process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30,
                "target_pressure_pa": 15,
                "hold_seconds": 20,
            }
        ] * 6
        with self.assertRaises(ValidationError):
            validate_deposition_process(process)

    def test_gas_backfill_requires_complete_stage_with_hold_time(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30,
                "target_pressure_pa": 15,
                "hold_seconds": None,
            }
        ]
        with self.assertRaisesRegex(ValueError, "gas backfill stage 1 is incomplete"):
            validate_deposition_process(process)

        # hold_seconds is the dwell time after reaching target pressure (not a
        # pressure), so any non-negative value completes the stage.
        process["gas_backfill_stages"][0]["hold_seconds"] = 14
        validate_deposition_process(process)

    def test_vcd_step_sequence_must_include_each_step_once(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30,
                "target_pressure_pa": 15,
                "hold_seconds": 20,
            }
        ]
        process["vcd_step_sequence"] = [
            "vcd_stage1",
            "gas_backfill_stage1",
            "vcd_stage2",
            "vcd_stage2",
        ]

        with self.assertRaisesRegex(ValueError, "every evacuation and gas backfill"):
            validate_deposition_process(process)

        process["vcd_step_sequence"] = []
        with self.assertRaisesRegex(ValueError, "every evacuation and gas backfill"):
            validate_deposition_process(process)

    def test_spin_coating_references_start_with_one_stage(self) -> None:
        for reference in LAYER_PRESETS.values():
            process = reference["layer"].get("process")
            if process and process["method"] == "spin_coating":
                self.assertEqual(len(process["spin_steps"]), 1)
        self.assertEqual(
            len(LAYER_PRESETS["perovskite_spin_v1"]["deposition_process"]["spin_steps"]),
            1,
        )

    def test_perovskite_process_accepts_four_spin_stages(self) -> None:
        _, process = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        process["spin_steps"] = [
            {"rpm": 1, "seconds": 60, "acceleration_rpm_per_s": 1},
            {"rpm": 180, "seconds": 5, "acceleration_rpm_per_s": 50},
            {"rpm": 2000, "seconds": 10, "acceleration_rpm_per_s": 2000},
            {"rpm": 4000, "seconds": 20, "acceleration_rpm_per_s": 2000},
        ]

        self.assertEqual(len(validate_deposition_process(process)["spin_steps"]), 4)

    def test_buried_interface_reference_is_between_sam_and_perovskite(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        layer_types = [layer["layer_type"] for layer in device_recipe["layers"]]
        self.assertEqual(
            layer_types.index("sio2_np"),
            layer_types.index("sam") + 1,
        )
        self.assertEqual(
            layer_types.index("perovskite"),
            layer_types.index("sio2_np") + 1,
        )

    def test_control_and_target_groups_are_required(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        device_recipe["experimental_groups"] = [
            {
                "group_id": "control",
                "kind": "control",
                "name": "Control",
                "change_from_control": "Reference procedure",
            }
        ]

        with self.assertRaisesRegex(ValueError, "at least one target group"):
            validate_device_recipe(device_recipe)

    def test_standalone_plan_has_one_independent_condition(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        device_recipe["experimental_groups"] = [
            {
                "group_id": "standalone",
                "kind": "standalone",
                "name": "Best-efficiency condition",
                "change_from_control": "",
                "inherits_control": False,
                "adjustments": [],
                "substrate_count": 3,
            }
        ]

        normalized = validate_device_recipe(device_recipe)

        self.assertEqual(
            normalized["experimental_groups"][0]["kind"],
            "standalone",
        )

    def test_standalone_condition_cannot_mix_with_comparative_groups(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        device_recipe["experimental_groups"].append(
            {
                "group_id": "standalone",
                "kind": "standalone",
                "name": "Standalone",
                "change_from_control": "",
                "inherits_control": False,
                "adjustments": [],
            }
        )

        with self.assertRaisesRegex(ValueError, "exactly one standalone"):
            validate_device_recipe(device_recipe)

    def test_control_derived_target_may_match_control(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []

        # A target inheriting from control with no layers and no adjustments is
        # valid — it uses the same recipe as the control.
        validate_device_recipe(device_recipe)

    def test_target_value_must_differ_from_control(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"][0]["target_value"] = "15"

        with self.assertRaisesRegex(ValueError, "must differ from the control value"):
            validate_device_recipe(device_recipe)

    def test_multiple_material_layers_can_share_a_functional_role(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        normalized = validate_device_recipe(device_recipe)

        htl_layers = [
            layer["layer_type"]
            for layer in normalized["layers"]
            if layer["role"] == "htl"
        ]
        self.assertEqual(htl_layers, ["niox", "sam"])

    def test_spin_coated_layers_may_be_applied_twice(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        niox = next(
            layer for layer in device_recipe["layers"] if layer["layer_type"] == "niox"
        )
        second_niox = deepcopy(niox)
        device_recipe["layers"].insert(1, second_niox)

        normalized = validate_device_recipe(device_recipe)
        htl_layers = [
            layer["layer_type"]
            for layer in normalized["layers"]
            if layer["role"] == "htl"
        ]
        self.assertEqual(htl_layers, ["niox", "niox", "sam"])

    def test_perovskite_layer_may_not_be_duplicated(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        perovskite = next(
            layer for layer in device_recipe["layers"] if layer["layer_type"] == "perovskite"
        )
        device_recipe["layers"].append(deepcopy(perovskite))

        with self.assertRaisesRegex(ValueError, "perovskite may appear only once"):
            validate_device_recipe(device_recipe)

    def test_evaporation_layers_may_not_be_duplicated(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        c60 = next(
            layer for layer in device_recipe["layers"] if layer["layer_type"] == "c60"
        )
        ag = next(
            layer for layer in device_recipe["layers"] if layer["layer_type"] == "ag"
        )
        device_recipe["layers"].remove(ag)
        device_recipe["layers"].append(deepcopy(c60))
        device_recipe["layers"].append(ag)

        with self.assertRaisesRegex(ValueError, "c60 may appear only once"):
            validate_device_recipe(device_recipe)

    def test_target_group_with_full_layers_and_process(self) -> None:
        device_recipe, deposition = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = deepcopy(device_recipe["layers"])
        target["deposition_process"] = deepcopy(deposition)

        normalized = validate_device_recipe(device_recipe)
        normalized_target = next(
            group for group in normalized["experimental_groups"]
            if group["kind"] == "target"
        )
        self.assertEqual(
            len(normalized_target["layers"]),
            len(device_recipe["layers"]),
        )
        self.assertEqual(
            normalized_target["deposition_process"]["method"],
            "spin_coating_vcd",
        )

    def test_target_group_deposition_process_must_be_complete(self) -> None:
        device_recipe, deposition = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = deepcopy(device_recipe["layers"])
        incomplete = deepcopy(deposition)
        incomplete["vcd_stages"][0]["pressure_pa"] = None
        target["deposition_process"] = incomplete

        with self.assertRaisesRegex(ValueError, "VCD stage 1 is incomplete"):
            validate_device_recipe(device_recipe)

    def test_target_with_own_layers_requires_deposition_process(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = deepcopy(device_recipe["layers"])
        target["deposition_process"] = None

        with self.assertRaisesRegex(ValueError, "requires a complete perovskite"):
            validate_device_recipe(device_recipe)

    def test_non_inheriting_target_cannot_bypass_completeness(self) -> None:
        device_recipe, deposition = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["inherits_control"] = False
        target["adjustments"] = []
        target["layers"] = deepcopy(device_recipe["layers"])
        target["deposition_process"] = deepcopy(deposition)
        target["layers"][0]["solution"]["solvents"] = []

        with self.assertRaisesRegex(ValueError, "requires at least one solvent"):
            validate_device_recipe(device_recipe)

    def test_sputtering_second_gas_is_optional_but_paired_with_its_flow(self) -> None:
        device_recipe, _ = complete_reference("ito_niox_sputter_pcbm_sno2_v1")
        sputtering = next(
            layer["process"]
            for layer in device_recipe["layers"]
            if layer["layer_type"] == "niox"
        )
        sputtering["gas2"] = ""
        sputtering["gas2_flow_sccm"] = None
        validate_device_recipe(device_recipe)

        sputtering["gas2"] = "O2"
        with self.assertRaisesRegex(ValueError, "gas 2 and its flow rate"):
            validate_device_recipe(device_recipe)

    def test_control_group_cannot_carry_layers_or_process(self) -> None:
        device_recipe, deposition = complete_reference("ito_niox_spin_pcbm_sno2_v1")
        control = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "control"
        )
        control["layers"] = deepcopy(device_recipe["layers"])

        with self.assertRaisesRegex(ValueError, "control group cannot contain its own layers"):
            validate_device_recipe(device_recipe)

    def test_deposition_recipe_from_process_pairs_device_recipe(self) -> None:
        device_recipe, process = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )

        values = deposition_recipe_from_process(process)
        values["device_recipe"] = validate_device_recipe(device_recipe)

        self.assertIn("device_recipe", values)
        self.assertEqual(values["vcd_stage3_pressure_pa"], 300)

    def test_deprecated_mbar_input_is_migrated_but_not_emitted(self) -> None:
        values = {
            "spin_cast_rpm": 800,
            "spin_cast_seconds": 60,
            "spin_cast_acceleration_rpm_per_s": 500,
            "spin_spread_rpm": 2000,
            "spin_spread_seconds": 10,
            "spin_spread_acceleration_rpm_per_s": 1000,
            "spin_thin_rpm": 5000,
            "spin_thin_seconds": 20,
            "spin_thin_acceleration_rpm_per_s": 2000,
            "vcd_stage1_valve": "VV02",
            "vcd_stage1_pressure_mbar": 1.5,
            "vcd_stage1_seconds": 10,
            "anneal_stage1_temperature_c": 120,
            "anneal_stage1_seconds": 600,
        }

        recipe = DepositionRecipe.from_mapping(values)

        self.assertEqual(recipe.vcd_stage1_pressure_pa, 150)
        self.assertEqual(recipe.vcd_stage1_pressure_mbar, 1.5)
        self.assertNotIn("vcd_stage1_pressure_mbar", recipe.to_dict())

    def test_non_finite_nested_measurements_are_rejected(self) -> None:
        device_recipe, _ = complete_reference(
            "ito_niox_spin_pcbm_sno2_v1"
        )
        device_recipe["substrate"]["width_mm"] = float("inf")

        with self.assertRaises(ValidationError):
            validate_device_recipe(device_recipe)

    def test_layer_references_are_returned_as_independent_data(self) -> None:
        first = deepcopy(LAYER_PRESETS["sam_spin_v1"])
        second = deepcopy(LAYER_PRESETS["sam_spin_v1"])
        first["layer"]["solution"]["solids"][0]["chemical"] = "4PADCB"
        self.assertEqual(
            second["layer"]["solution"]["solids"][0]["chemical"],
            "",
        )


if __name__ == "__main__":
    unittest.main()
