import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from perovskite_bo import (
    BayesianStrategy,
    ChoiceParameter,
    DepositionRecipe,
    ExperimentRecord,
    ExperimentStatus,
    IntegerParameter,
    SearchSpace,
)


def bo_space() -> SearchSpace:
    return SearchSpace(
        [
            IntegerParameter("spin_cast_rpm", 800, 804),
            IntegerParameter("spin_cast_seconds", 60, 60),
            IntegerParameter("spin_cast_acceleration_rpm_per_s", 500, 500),
            IntegerParameter("spin_spread_rpm", 2_000, 2_000),
            IntegerParameter("spin_spread_seconds", 10, 10),
            IntegerParameter("spin_spread_acceleration_rpm_per_s", 1_000, 1_000),
            IntegerParameter("spin_thin_rpm", 5_000, 5_000),
            IntegerParameter("spin_thin_seconds", 20, 20),
            IntegerParameter("spin_thin_acceleration_rpm_per_s", 2_000, 2_000),
            ChoiceParameter("vcd_stage1_valve", ["VV02"]),
            IntegerParameter("vcd_stage1_pressure_pa", 5_000, 5_000),
            IntegerParameter("vcd_stage1_seconds", 10, 10),
            IntegerParameter("anneal_stage1_temperature_c", 120, 120),
            IntegerParameter("anneal_stage1_seconds", 600, 600),
        ]
    )


def recipe(spin_cast_rpm: int) -> DepositionRecipe:
    return DepositionRecipe.from_mapping(
        {
            "spin_cast_rpm": spin_cast_rpm,
            "spin_cast_seconds": 60,
            "spin_cast_acceleration_rpm_per_s": 500,
            "spin_spread_rpm": 2_000,
            "spin_spread_seconds": 10,
            "spin_spread_acceleration_rpm_per_s": 1_000,
            "spin_thin_rpm": 5_000,
            "spin_thin_seconds": 20,
            "spin_thin_acceleration_rpm_per_s": 2_000,
            "vcd_stage1_valve": "VV02",
            "vcd_stage1_pressure_pa": 5_000,
            "vcd_stage1_seconds": 10,
            "anneal_stage1_temperature_c": 120,
            "anneal_stage1_seconds": 600,
        }
    )


def record(
    record_id: int,
    *,
    status: ExperimentStatus,
    metrics: dict[str, float] | None = None,
    failure_reason: str | None = None,
) -> ExperimentRecord:
    return ExperimentRecord(
        id=record_id,
        recipe=recipe(800 + record_id),
        status=status,
        metrics=metrics or {},
        failure_reason=failure_reason,
        created_at="2026-08-01T08:00:00Z",
        updated_at="2026-08-01T08:00:00Z",
    )


class BayesianStrategyTests(unittest.TestCase):
    def test_uses_completed_history_and_avoids_failed_constraint(self) -> None:
        history = [
            record(0, status=ExperimentStatus.COMPLETED, metrics={"pce": 5.0}),
            record(3, status=ExperimentStatus.COMPLETED, metrics={"pce": 20.0}),
            record(2, status=ExperimentStatus.FAILED, failure_reason="coating failure"),
        ]

        suggestion = BayesianStrategy(seed=1, initial_random=0, candidate_count=64).suggest(
            bo_space(), history
        )

        self.assertEqual(suggestion.spin_cast_rpm, 804)


if __name__ == "__main__":
    unittest.main()
