import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class AlembicGraphTests(unittest.TestCase):
    def test_migrations_form_one_ordered_chain(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        revisions = list(script.walk_revisions())

        self.assertEqual(script.get_heads(), ["0016_device_scan_stats"])
        self.assertEqual(
            [(revision.revision, revision.down_revision) for revision in revisions],
            [
                (
                    "0016_device_scan_stats",
                    "0015_drop_experiments_recipe_blob",
                ),
                (
                    "0015_drop_experiments_recipe_blob",
                    "0014_deployment_integrity_repairs",
                ),
                ("0014_deployment_integrity_repairs", "0013_substrate_laser_marks"),
                ("0013_substrate_laser_marks", "0012_baseline_scope_owner"),
                ("0012_baseline_scope_owner", "0011_device_layout_versions"),
                ("0011_device_layout_versions", "0010_catalog_integrity"),
                ("0010_catalog_integrity", "0009_material_catalog"),
                ("0009_material_catalog", "0008_user_layer_presets"),
                ("0008_user_layer_presets", "0007_fabrication_batches"),
                ("0007_fabrication_batches", None),
            ],
        )

    def test_deviation_type_metadata_matches_the_integrity_contract(self) -> None:
        """The model metadata (the alembic-check baseline) carries the typed
        deviation contract: a non-null deviation_type with exact allowed
        values and a single-target check that includes condition_id."""

        from web.database import execution_deviations

        column = execution_deviations.c.deviation_type
        self.assertFalse(column.nullable)
        self.assertIsNone(column.server_default)

        checks = {
            # Constraint names carry the ck_<table>_ naming-convention prefix.
            str(constraint.name).split("_execution_deviations_")[-1]:
            constraint.sqltext.text
            for constraint in execution_deviations.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        deviation_type_check = checks["valid_deviation_type"]
        for allowed in (
            "'general'",
            "'fabrication_shortfall'",
            "'measurement_shortfall'",
        ):
            self.assertIn(allowed, deviation_type_check)

        target_check = checks["at_most_one_deviation_target"]
        for target_column in (
            "solution_preparation_id",
            "process_execution_id",
            "substrate_id",
            "device_id",
            "condition_id",
        ):
            self.assertIn(target_column, target_check)


if __name__ == "__main__":
    unittest.main()
