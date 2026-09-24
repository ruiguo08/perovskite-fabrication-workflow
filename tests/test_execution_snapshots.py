from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError

from web.execution_snapshots import (
    snapshot_hash,
    validate_process_snapshot,
    validate_solution_snapshot,
)


class ExecutionSnapshotTests(unittest.TestCase):
    def test_complete_solution_is_normalized_and_hashable(self) -> None:
        snapshot = validate_solution_snapshot(
            {
                "formulation_type": "weighed_solids",
                "solids": [{"chemical": "FAI", "weight_mg": 10}],
                "solvents": [{"solvent": "DMF", "volume_ml": 1}],
            }
        )

        self.assertEqual(snapshot["stock_dispersion"], "")
        self.assertEqual(len(snapshot_hash(snapshot)), 64)

    def test_partial_solution_is_rejected(self) -> None:
        with self.assertRaises((TypeError, ValueError, ValidationError)):
            validate_solution_snapshot({"chemical": "FAI", "weight_mg": 10})

    def test_vcd_snapshot_preserves_interleaved_program(self) -> None:
        snapshot = validate_process_snapshot(
            {
                "method": "vcd",
                "vcd_stages": [
                    {"valve": "VV02", "pressure_pa": 1, "seconds": 10},
                    {"valve": "VV03", "pressure_pa": 100, "seconds": 20},
                ],
                "gas_backfill_stages": [
                    {
                        "gas": "N2",
                        "flow_sccm": 30,
                        "target_pressure_pa": 15,
                        "hold_seconds": 20,
                    }
                ],
                "vcd_step_sequence": [
                    "vcd_stage1",
                    "gas_backfill_stage1",
                    "vcd_stage2",
                ],
            },
            expected_method="vcd",
        )

        self.assertEqual(
            snapshot["vcd_step_sequence"],
            ["vcd_stage1", "gas_backfill_stage1", "vcd_stage2"],
        )

    def test_process_method_must_match_execution(self) -> None:
        with self.assertRaises(ValueError):
            validate_process_snapshot(
                {
                    "method": "thermal_evaporation",
                    "thickness_nm": 20,
                    "rate_angstrom_per_s": 0.2,
                },
                expected_method="ald",
            )

    def test_execution_snapshot_accepts_four_spin_stages(self) -> None:
        snapshot = validate_process_snapshot(
            {
                "method": "spin_coating",
                "spin_steps": [
                    {"rpm": 1, "seconds": 60, "acceleration_rpm_per_s": 1},
                    {"rpm": 180, "seconds": 5, "acceleration_rpm_per_s": 50},
                    {"rpm": 2000, "seconds": 10, "acceleration_rpm_per_s": 2000},
                    {"rpm": 4000, "seconds": 20, "acceleration_rpm_per_s": 2000},
                ],
            }
        )

        self.assertEqual(len(snapshot["spin_steps"]), 4)


if __name__ == "__main__":
    unittest.main()
