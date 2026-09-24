"""Fabrication Batch tests: creation, lifecycle, substrates, devices, and deviations.

Uses direct repository calls to avoid legacy adapter complexity.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from sqlalchemy import select

from web import create_app
from web.condition_snapshot import build_condition_snapshot, canonical_hash
from tests.layout_fixtures import fixture_layout, fixture_layouts, seed_standard_layouts
from web.device_layouts import expected_device_count, layout_snapshot
from web.execution_snapshots import snapshot_hash
from web.repository import (
    BatchStatus,
    ConditionRole,
    ExecutionStatus,
    PlanStatus,
    PreparationStatus,
    UserRole,
)
from test_web_app import TEST_USERNAME, TEST_PASSWORD, complete_guided_setup, VALID_RECIPE


def _recipe_with_standalone_group() -> tuple[dict, dict]:
    """Return a device_recipe + deposition_process with a standalone group."""
    dr, dp = complete_guided_setup()
    dr["experimental_groups"] = [
        {
            "group_id": "standalone",
            "kind": "standalone",
            "name": "Standalone",
            "change_from_control": "",
            "inherits_control": False,
            "adjustments": [],
            "substrate_count": 3,
        }
    ]
    return dr, dp


async def _create_released_experiment_with_conditions(
    repo,
    campaign_code: str,
    layout_code: str = "15x15_dual_005",
    substrate_count: int = 3,
    standalone: bool = False,
    actor_user_id: int = 1,
    campaign_actor_user_id: int | None = None,
    gas_backfill_stages: list[dict] | None = None,
    vcd_step_sequence: list[str] | None = None,
) -> int:
    """Create an experiment, add conditions, release it, return experiment_id."""
    from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
    await repo.create_campaign(
        code=campaign_code,
        display_name=f"Test {campaign_code}",
        description="",
        actor_user_id=campaign_actor_user_id or actor_user_id,
    )
    if standalone:
        dr, dp = _recipe_with_standalone_group()
    else:
        dr, dp = complete_guided_setup()
        if gas_backfill_stages is not None:
            dp["gas_backfill_stages"] = gas_backfill_stages
        if vcd_step_sequence is not None:
            dp["vcd_step_sequence"] = vcd_step_sequence
        # Give the target its own layers to avoid manual review
        import json
        for group in dr["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in dr["layers"]]
                group["deposition_process"] = json.loads(json.dumps(dp))

    # Update substrate dimensions to match layout
    layout = fixture_layout(layout_code)
    dr["substrate"]["width_mm"] = float(layout.substrate_width_mm)
    dr["substrate"]["length_mm"] = float(layout.substrate_length_mm)

    # Build condition plans
    groups = [g for g in dr["experimental_groups"]]
    condition_plans = [
        {"group_id": g["group_id"], "role": g["kind"],
         "device_layout_code": layout_code, "planned_substrate_count": substrate_count}
        for g in groups
    ]

    recipe = DepositionRecipe.from_mapping({
        **deposition_recipe_from_process(dp),
        "device_recipe": dr,
    })
    record = await repo.add_experiment(
        recipe,
        campaign_id=campaign_code,
        condition_plans=condition_plans,
        actor_user_id=actor_user_id,
    )
    exp_id = record.id

    # Release the plan via the strict approval workflow
    # (conditions are auto-created by legacy adapter).
    await repo.update_plan_status(
        exp_id, PlanStatus.PENDING_APPROVAL, actor_user_id=actor_user_id
    )
    await repo.update_plan_status(
        exp_id, PlanStatus.APPROVED, actor_user_id=actor_user_id
    )
    await repo.update_plan_status(
        exp_id, PlanStatus.RELEASED, actor_user_id=actor_user_id
    )
    return exp_id


class LayoutFreezeTests(unittest.TestCase):
    """Catalog updates must never retroactively change frozen geometry:
    condition edits, plan release, batch materialization, and extra
    substrates all resolve the layout version recorded in each frozen
    snapshot, while brand-new conditions select the latest version."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "layout-freeze.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)  # 15x15_dual_005 v1: 2 devices
        self.repository = self.app.state.repository
        self.experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "layout-freeze"
            )
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _bump_layout_to_v2(self) -> None:
        response = self.client.post(
            "/api/device-layouts",
            json={
                "code": "15x15_dual_005",
                "version": 2,
                "substrate_width_mm": "15",
                "substrate_length_mm": "15",
                "devices_per_substrate": 4,
                "device_active_area_cm2": "0.04",
                "total_active_area_cm2": "0.16",
                "description": "15 x 15 mm substrate, 4 devices, 0.04 cm2 each",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        # The creation response must echo the inserted version, not the
        # catalog's latest.
        self.assertEqual(response.json()["version"], 2)

    def _experiment_conditions(self, experiment_id: int) -> list[dict]:
        response = self.client.get(
            f"/api/experiments/{experiment_id}/conditions"
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_draft_experiment(self, campaign_code: str) -> int:
        async def create() -> int:
            from perovskite_bo import (
                DepositionRecipe,
                deposition_recipe_from_process,
            )

            await self.repository.create_campaign(
                code=campaign_code,
                display_name=campaign_code,
                description="",
                actor_user_id=1,
            )
            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = [
                        dict(layer) for layer in device_recipe["layers"]
                    ]
                    group["deposition_process"] = json.loads(
                        json.dumps(deposition_process)
                    )
            condition_plans = [
                {
                    "group_id": group["group_id"],
                    "role": group["kind"],
                    "device_layout_code": "15x15_dual_005",
                    "planned_substrate_count": 3,
                }
                for group in device_recipe["experimental_groups"]
            ]
            recipe = DepositionRecipe.from_mapping(
                {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                }
            )
            record = await self.repository.add_experiment(
                recipe,
                campaign_id=campaign_code,
                condition_plans=condition_plans,
                actor_user_id=1,
            )
            return record.id

        return asyncio.run(create())

    def test_condition_update_keeps_frozen_layout_version(self) -> None:
        draft_experiment = self._create_draft_experiment("layout-freeze-edit")
        self._bump_layout_to_v2()
        condition = self._experiment_conditions(draft_experiment)[0]
        renamed = self.client.put(
            f"/api/conditions/{condition['id']}",
            json={
                "condition_name": "Renamed after catalog update",
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": condition["source_baseline_version_id"],
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": condition["planned_substrate_count"],
            },
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        payload = renamed.json()
        # Geometry stays on the frozen v1 (2 devices x 3 substrates), never
        # the newer catalog version (4 devices).
        self.assertEqual(payload["expected_device_count"], 6)
        self.assertEqual(payload["device_layout_snapshot"]["version"], 1)

    def test_release_and_batch_use_frozen_geometry(self) -> None:
        draft_experiment = self._create_draft_experiment("layout-freeze-draft")
        self._bump_layout_to_v2()
        asyncio.run(
            self.repository.update_plan_status(
                draft_experiment, PlanStatus.PENDING_APPROVAL, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_plan_status(
                draft_experiment, PlanStatus.APPROVED, actor_user_id=1
            )
        )
        # Release validation compares the frozen snapshot against the exact
        # frozen (code, version) row -- it must not fail on a newer catalog
        # version, and batch materialization must not use the new geometry.
        asyncio.run(
            self.repository.update_plan_status(
                draft_experiment, PlanStatus.RELEASED, actor_user_id=1
            )
        )
        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                draft_experiment, actor_user_id=1
            )
        )
        devices = asyncio.run(
            self.repository.get_fabrication_devices_for_batch(batch.id)
        )
        substrates = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(batch.id)
        )
        self.assertEqual(len(substrates), 6)  # 2 conditions x 3 substrates
        self.assertEqual(len(devices), 12)  # ...x 2 devices (v1), not 4

    def test_extra_substrates_use_frozen_geometry(self) -> None:
        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.READY, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
            )
        )
        self._bump_layout_to_v2()
        for preparation in asyncio.run(
            self.repository.list_solution_preparations(batch.id)
        ):
            asyncio.run(
                self.repository.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(
            self.repository.list_process_executions(batch.id)
        ):
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        batch_conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
        )
        actual = {condition.id: 4 for condition in batch_conditions}
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts=actual,
                actor_user_id=1,
            )
        )
        devices = asyncio.run(
            self.repository.get_fabrication_devices_for_batch(batch.id)
        )
        substrates = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(batch.id)
        )
        extra = [
            substrate for substrate in substrates if substrate.substrate_ordinal == 4
        ]
        self.assertEqual(len(extra), len(batch_conditions))
        for substrate in extra:
            substrate_devices = [
                device for device in devices if device.substrate_id == substrate.id
            ]
            # The extra substrate was materialized with the frozen v1
            # geometry (2 devices), never the v2 geometry (4 devices).
            self.assertEqual(len(substrate_devices), 2)


class FabricationBatchCreationTests(unittest.TestCase):
    """Test basic batch creation, conditions freezing, and substrate/device generation."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "fab.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(self.repository, "fab-test")
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    # 4. Comparative Plan creates Batch
    def test_comparative_plan_creates_batch(self) -> None:
        import asyncio
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        self.assertEqual(batch.status, BatchStatus.DRAFT)
        self.assertIn("B01", batch.batch_code)
        self.assertEqual(batch.experiment_id, self._experiment_id)

    # 5. Standalone Plan creates Batch
    def test_standalone_plan_creates_batch(self) -> None:
        import asyncio
        exp_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "fab-standalone", standalone=True
            )
        )
        batch = asyncio.run(self.repository.create_fabrication_batch(
            exp_id, actor_user_id=1,
        ))
        self.assertEqual(batch.status, BatchStatus.DRAFT)
        self.assertIn("B01", batch.batch_code)

    # 6. Non-released Plan rejects
    def test_non_released_plan_rejected(self) -> None:
        import asyncio
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="no-release", display_name="No release", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="no-release", actor_user_id=1
        ))
        exp_id = record.id
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.create_fabrication_batch(
                exp_id, actor_user_id=1,
            ))

    # 7. Manual review condition rejects
    def test_manual_review_condition_rejected(self) -> None:
        import asyncio
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="manual-review", display_name="Manual review", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        # The target has adjustments but no layers, so legacy adapter will set requires_manual_review=True
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="manual-review", actor_user_id=1
        ))
        # Get conditions to verify one requires manual review
        conditions = asyncio.run(self.repository.list_conditions_for_experiment(record.id))
        # Plan should have conditions but batch creation should fail because of manual review
        # Submitting for approval is blocked because a condition requires
        # manual review (the check runs for every non-cancelled target).
        with self.assertRaisesRegex(ValueError, "manual review"):
            asyncio.run(self.repository.update_plan_status(
                record.id, PlanStatus.PENDING_APPROVAL, actor_user_id=1,
            ))

    # 7b. Strict workflow: a draft cannot jump straight to RELEASED.
    def test_draft_cannot_be_released_directly(self) -> None:
        import asyncio
        import json
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="strict-flow", display_name="Strict", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        for group in dr["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in dr["layers"]]
                group["deposition_process"] = json.loads(json.dumps(dp))
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="strict-flow", actor_user_id=1
        ))
        with self.assertRaisesRegex(ValueError, "cannot change from draft to released"):
            asyncio.run(self.repository.update_plan_status(
                record.id, PlanStatus.RELEASED, actor_user_id=1,
            ))

    # 7c. requires_manual_review is preserved on metadata-only edits and
    # cleared only when a substantive field changes.
    def test_manual_review_flag_preserved_on_metadata_only_edit(self) -> None:
        import asyncio
        import json
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="mr-flag", display_name="MR", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        # Target with adjustments but no layers -> legacy adapter marks the
        # condition requires_manual_review=True.
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="mr-flag", actor_user_id=1
        ))
        conditions = asyncio.run(self.repository.list_conditions_for_experiment(record.id))
        manual = next(c for c in conditions if c.requires_manual_review)
        snapshot = manual.recipe_snapshot
        layout_code = manual.device_layout_code
        count = manual.planned_substrate_count

        # Metadata-only rename: same recipe hash, count, and layout -> the
        # manual-review flag must be preserved.
        renamed = asyncio.run(self.repository.update_condition(
            manual.id,
            condition_name="Renamed condition",
            recipe_snapshot=snapshot,
            source_baseline_version_id=None,
            device_layout_code=layout_code,
            planned_substrate_count=count,
            actor_user_id=1,
        ))
        self.assertTrue(renamed.requires_manual_review)

        # Substantive change: a different substrate count clears the flag.
        resolved = asyncio.run(self.repository.update_condition(
            manual.id,
            condition_name="Renamed condition",
            recipe_snapshot=snapshot,
            source_baseline_version_id=None,
            device_layout_code=layout_code,
            planned_substrate_count=count + 1,
            actor_user_id=1,
        ))
        self.assertFalse(resolved.requires_manual_review)

    # 8. <3 substrates without approval rejects
    def test_less_than_3_substrates_without_approval_rejected(self) -> None:
        import asyncio
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="low-count", display_name="Low count", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        # Give target its own layers but use 2 substrates for control
        import json
        for group in dr["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in dr["layers"]]
                group["deposition_process"] = json.loads(json.dumps(dp))
        groups = [g for g in dr["experimental_groups"]]
        condition_plans = [
            {"group_id": g["group_id"], "role": g["kind"],
             "device_layout_code": "15x15_dual_005",
             "planned_substrate_count": 2 if g["kind"] == "control" else 3}
            for g in groups
        ]
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="low-count", condition_plans=condition_plans, actor_user_id=1
        ))
        # The control has 2 substrates - submitting for approval fails
        # because no substrate exception has been requested yet.
        with self.assertRaisesRegex(ValueError, "substrate exception"):
            asyncio.run(self.repository.update_plan_status(
                record.id, PlanStatus.PENDING_APPROVAL, actor_user_id=1,
            ))

    # 9. Layouts generate correct counts
    def test_layouts_generate_correct_counts(self) -> None:
        import asyncio
        for layout in fixture_layouts():
            exp_id = asyncio.run(
                _create_released_experiment_with_conditions(
                    self.repository, f"layout-{layout.code}", layout_code=layout.code
                )
            )
            batch = asyncio.run(self.repository.create_fabrication_batch(
                exp_id, actor_user_id=1,
            ))
            substrates = asyncio.run(self.repository.get_fabrication_substrates_for_batch(batch.id))
            devices = asyncio.run(self.repository.get_fabrication_devices_for_batch(batch.id))
            batch_conditions = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
            # 2 conditions, each with 3 substrates
            self.assertEqual(len(substrates), 2 * 3, f"layout {layout.code} should have 6 substrates")
            expected_devices = 2 * 3 * layout.devices_per_substrate
            self.assertEqual(
                len(devices), expected_devices,
                f"layout {layout.code} should have {expected_devices} devices"
            )

    # 10. 25x25_six_010, 3 substrates = 18 devices per condition
    def test_25x25_six_010_generates_18_devices(self) -> None:
        import asyncio
        layout = fixture_layout("25x25_six_010")
        exp_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "layout-25x25", layout_code="25x25_six_010"
            )
        )
        batch = asyncio.run(self.repository.create_fabrication_batch(
            exp_id, actor_user_id=1,
        ))
        batch_conditions = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
        devices = asyncio.run(self.repository.get_fabrication_devices_for_batch(batch.id))
        # 2 conditions, each with 3 substrates x 6 devices = 18
        self.assertEqual(len(devices), 2 * 18)

    # 11. 15x15_dual_005, 3 substrates = 6 devices per condition
    def test_15x15_dual_005_generates_6_devices(self) -> None:
        import asyncio
        exp_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "layout-15x15", layout_code="15x15_dual_005"
            )
        )
        batch = asyncio.run(self.repository.create_fabrication_batch(
            exp_id, actor_user_id=1,
        ))
        batch_conditions = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
        devices = asyncio.run(self.repository.get_fabrication_devices_for_batch(batch.id))
        # 2 conditions, each with 3 substrates x 2 devices = 6
        self.assertEqual(len(devices), 2 * 6)

    # 12. Approved 1 or 2 substrates generates correct counts
    def test_approved_2_substrates_generates_correct_count(self) -> None:
        import asyncio
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="approved-2", display_name="Approved 2", description="", actor_user_id=1
        ))
        dr, dp = complete_guided_setup()
        # Give target its own layers, use 2 substrates for control
        import json
        for group in dr["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in dr["layers"]]
                group["deposition_process"] = json.loads(json.dumps(dp))
        groups = [g for g in dr["experimental_groups"]]
        condition_plans = [
            {"group_id": g["group_id"], "role": g["kind"],
             "device_layout_code": "15x15_dual_005",
             "planned_substrate_count": 2 if g["kind"] == "control" else 3}
            for g in groups
        ]
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="approved-2", condition_plans=condition_plans, actor_user_id=1
        ))
        exp_id = record.id
        # Get the control condition to request exception
        conditions = asyncio.run(self.repository.list_conditions_for_experiment(exp_id))
        control = next(c for c in conditions if c.role == ConditionRole.CONTROL)
        from web.repository import ExceptionDecision
        exc = asyncio.run(self.repository.request_substrate_exception(
            condition_id=control.id, requested_count=2, reason="Test", requested_by_id=1,
        ))
        asyncio.run(self.repository.decide_substrate_exception(
            exc.id, decision=ExceptionDecision.APPROVED, decided_by_id=1, decision_note="OK",
        ))
        asyncio.run(self.repository.update_plan_status(exp_id, PlanStatus.PENDING_APPROVAL, actor_user_id=1))
        asyncio.run(self.repository.update_plan_status(exp_id, PlanStatus.APPROVED, actor_user_id=1))
        asyncio.run(self.repository.update_plan_status(exp_id, PlanStatus.RELEASED, actor_user_id=1))
        batch = asyncio.run(self.repository.create_fabrication_batch(
            exp_id, actor_user_id=1,
        ))
        # Check total substrate count (2 control + 3 target = 5)
        substrates = asyncio.run(self.repository.get_fabrication_substrates_for_batch(batch.id))
        self.assertEqual(len(substrates), 5)
        devices = asyncio.run(self.repository.get_fabrication_devices_for_batch(batch.id))
        # 2 control substrates x 2 devices + 3 target substrates x 2 devices = 10
        self.assertEqual(len(devices), 10)
        # Verify the control condition has exactly 2 substrates
        conditions = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
        for bc in conditions:
            cond_substrates = [s for s in substrates if s.batch_condition_id == bc.id]
            if bc.role == "control":
                self.assertEqual(len(cond_substrates), 2)

    # 13. Substrate/device labels unique and deterministic
    def test_substrate_device_labels(self) -> None:
        import asyncio
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        conditions = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
        self.assertGreater(len(conditions), 0)
        cond_code = conditions[0].condition_code
        substrates = asyncio.run(self.repository.get_fabrication_substrates_for_batch(batch.id))
        substrate_codes = [s.substrate_code for s in substrates]
        substrate_marks = [s.substrate_mark for s in substrates]
        # Should have 3 substrates per condition
        self.assertEqual(len(substrate_codes), 3 * len(conditions))
        # Check naming pattern
        for c in conditions:
            expected = [
                f"{batch.batch_code}-{c.condition_code}-S01",
                f"{batch.batch_code}-{c.condition_code}-S02",
                f"{batch.batch_code}-{c.condition_code}-S03",
            ]
            for exp in expected:
                self.assertIn(exp, substrate_codes)
        # Check device codes
        devices = asyncio.run(self.repository.get_fabrication_devices_for_batch(batch.id))
        device_codes = [d.device_code for d in devices]
        device_marks = [d.device_mark for d in devices]
        for c in conditions:
            layout = fixture_layout(c.device_layout_code)
            for s_idx in range(1, 4):
                for d_idx in range(1, layout.devices_per_substrate + 1):
                    expected = f"{batch.batch_code}-{c.condition_code}-S{s_idx:02d}-D{d_idx:02d}"
                    self.assertIn(expected, device_codes)
        # Verify uniqueness of internal codes
        self.assertEqual(len(set(device_codes)), len(device_codes))
        # Laser marks are physical facts entered at result-CSV upload, so they
        # are null at batch creation.
        self.assertTrue(
            all(mark is None for mark in substrate_marks),
            f"expected null substrate laser marks at batch creation, got {substrate_marks}",
        )
        self.assertTrue(
            all(mark is None for mark in device_marks),
            f"expected null device marks at batch creation, got {device_marks}",
        )

    # 14. Multiple batches use different B01/B02 codes for same experiment
    def test_multiple_batches_have_sequential_codes(self) -> None:
        import asyncio
        batch1 = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1, notes="First",
        ))
        batch2 = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1, notes="Second",
        ))
        self.assertEqual(batch1.batch_code, f"fab-test-v1-B01")
        self.assertEqual(batch2.batch_code, f"fab-test-v1-B02")
        self.assertNotEqual(batch1.batch_code, batch2.batch_code)
        first_marks = [
            device.device_mark
            for device in asyncio.run(
                self.repository.get_fabrication_devices_for_batch(batch1.id)
            )
        ]
        second_marks = [
            device.device_mark
            for device in asyncio.run(
                self.repository.get_fabrication_devices_for_batch(batch2.id)
            )
        ]
        # Laser marks are null until a result CSV associates each substrate.
        self.assertTrue(all(mark is None for mark in first_marks))
        self.assertTrue(all(mark is None for mark in second_marks))

    # 15. Frozen condition snapshots/hashes are immutable
    def test_frozen_condition_immutable(self) -> None:
        import asyncio
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        frozen = asyncio.run(self.repository.get_fabrication_batch_conditions(batch.id))
        self.assertGreater(len(frozen), 0)
        # Verify the snapshot hash is preserved
        self.assertEqual(len(frozen[0].source_condition_hash), 64)
        # Verify the recipe_snapshot is a proper dict (not a reference)
        self.assertIn("device", frozen[0].recipe_snapshot)

    # 22. Batch status transitions
    def test_batch_status_transitions(self) -> None:
        from web.repository import _batch_status_transitions
        self.assertIn(BatchStatus.READY, _batch_status_transitions(BatchStatus.DRAFT))
        self.assertIn(BatchStatus.CANCELLED, _batch_status_transitions(BatchStatus.DRAFT))
        self.assertIn(BatchStatus.IN_PROGRESS, _batch_status_transitions(BatchStatus.READY))
        self.assertIn(BatchStatus.CANCELLED, _batch_status_transitions(BatchStatus.READY))
        self.assertIn(BatchStatus.COMPLETED, _batch_status_transitions(BatchStatus.IN_PROGRESS))
        self.assertIn(BatchStatus.CANCELLED, _batch_status_transitions(BatchStatus.IN_PROGRESS))
        self.assertEqual(_batch_status_transitions(BatchStatus.COMPLETED), set())
        self.assertEqual(_batch_status_transitions(BatchStatus.CANCELLED), set())

    # 22b. Illegal status transitions rejected
    def test_illegal_batch_status_transition_rejected(self) -> None:
        import asyncio
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        # Cannot go from draft to in_progress directly
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1,
            ))
        # Can go to ready
        asyncio.run(self.repository.update_fabrication_batch_status(
            batch.id, BatchStatus.READY, actor_user_id=1,
        ))
        refreshed = asyncio.run(self.repository.get_fabrication_batch(batch.id))
        self.assertEqual(refreshed.status, BatchStatus.READY)

    # 23. After in_progress, status is frozen
    def test_frozen_after_in_progress(self) -> None:
        import asyncio
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        asyncio.run(self.repository.update_fabrication_batch_status(
            batch.id, BatchStatus.READY, actor_user_id=1,
        ))
        asyncio.run(self.repository.update_fabrication_batch_status(
            batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1,
        ))
        refreshed = asyncio.run(self.repository.get_fabrication_batch(batch.id))
        self.assertEqual(refreshed.status, BatchStatus.IN_PROGRESS)
        self.assertIsNotNone(refreshed.started_at)

    def test_completion_requires_terminal_execution_records(self) -> None:
        import asyncio
        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self._experiment_id, actor_user_id=1
            )
        )
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
        )
        # Record actual counts equal to planned (no shortfall, no deviation
        # required) so completion is gated only by the terminal-record check.
        actual_counts = {
            condition.id: condition.planned_substrate_count
            for condition in conditions
        }
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.READY, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
            )
        )
        with self.assertRaises(ValueError):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    batch.id, BatchStatus.COMPLETED, actor_user_id=1,
                    actual_substrate_counts=actual_counts,
                )
            )

        for preparation in asyncio.run(
            self.repository.list_solution_preparations(batch.id)
        ):
            asyncio.run(
                self.repository.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(
            self.repository.list_process_executions(batch.id)
        ):
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id, BatchStatus.COMPLETED, actor_user_id=1,
                actual_substrate_counts=actual_counts,
            )
        )
        with self.assertRaises(ValueError):
            asyncio.run(
                self.repository.create_solution_preparation(
                    fabrication_batch_id=batch.id,
                    planned_solution_snapshot={"late": True},
                    actor_user_id=1,
                )
            )

    # 31. Transaction failure rolls back
    def test_transaction_rollback_on_failure(self) -> None:
        import asyncio
        with self.assertRaises(KeyError):
            asyncio.run(self.repository.create_fabrication_batch(
                99999, actor_user_id=1,
            ))
        # No batches should exist for invalid experiment
        batches = asyncio.run(self.repository.list_fabrication_batches_for_experiment(
            self._experiment_id
        ))
        self.assertEqual(len(batches), 0)


class FabricationBatchAPITests(unittest.TestCase):
    """Test the HTTP API for fabrication batches."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "fab-api.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _create_released_experiment(self) -> int:
        import asyncio
        return asyncio.run(
            _create_released_experiment_with_conditions(
                self.app.state.repository, "api-test"
            )
        )

    def test_api_create_batch(self) -> None:
        exp_id = self._create_released_experiment()
        resp = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={"notes": "Test batch"})
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "draft")
        self.assertIn("B01", data["batch_code"])

    def test_api_list_batches(self) -> None:
        exp_id = self._create_released_experiment()
        self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        resp = self.client.get(f"/api/experiments/{exp_id}/fabrication-batches")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_api_get_batch(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.get(f"/api/fabrication-batches/{batch_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], batch_id)

    def test_api_get_conditions(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.get(f"/api/fabrication-batches/{batch_id}/conditions")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_api_get_substrates(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.get(f"/api/fabrication-batches/{batch_id}/substrates")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_api_get_devices(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.get(f"/api/fabrication-batches/{batch_id}/devices")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_api_update_status(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.patch(f"/api/fabrication-batches/{batch_id}/status", json={"status": "ready"})
        self.assertEqual(resp.status_code, 204)
        batch = self.client.get(f"/api/fabrication-batches/{batch_id}").json()
        self.assertEqual(batch["status"], "ready")

    def test_api_create_deviation(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.post(f"/api/fabrication-batches/{batch_id}/deviations", json={
            "category": "process", "severity": "warning",
            "description": "Temperature exceeded by 2 deg C",
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["category"], "process")
        self.assertEqual(data["severity"], "warning")

    def test_api_list_deviations(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        self.client.post(f"/api/fabrication-batches/{batch_id}/deviations", json={
            "category": "material", "severity": "error", "description": "Wrong chemical",
        })
        resp = self.client.get(f"/api/fabrication-batches/{batch_id}/deviations")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_api_create_solution_preparation(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.post(f"/api/fabrication-batches/{batch_id}/solution-preparations", json={
            "planned_solution_snapshot": {
                "formulation_type": "weighed_solids",
                "stock_dispersion": "",
                "stock_volume_ml": None,
                "solids": [{"chemical": "Me-4PACz", "weight_mg": 2.0}],
                "solvents": [{"solvent": "Ethanol", "volume_ml": 1.0}],
            },
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "planned")

    def test_api_create_process_execution(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(f"/api/experiments/{exp_id}/fabrication-batches", json={})
        batch_id = created.json()["id"]
        resp = self.client.post(f"/api/fabrication-batches/{batch_id}/process-executions", json={
            "method": "thermal_evaporation", "layer_role": "etl",
            "layer_type": "c60", "layer_name": "C60",
            "planned_process_snapshot": {
                "method": "thermal_evaporation",
                "thickness_nm": 20,
                "rate_angstrom_per_s": 0.5,
            },
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()
        self.assertEqual(data["method"], "thermal_evaporation")

    def test_legacy_batch_detail_redirects_to_react(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = created.json()["id"]

        response = self.client.get(
            f"/experiments/{exp_id}/batches/{batch_id}",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(
            response.headers["location"],
            f"/app/experiments/{exp_id}/batches/{batch_id}",
        )

    def test_batch_export_json(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = created.json()["id"]
        export = self.client.get(f"/experiments/{exp_id}/batches/{batch_id}/export.json")
        self.assertEqual(export.status_code, 200, export.text)
        payload = export.json()
        self.assertEqual(payload["schema_version"], 5)
        self.assertIn("batch", payload)
        self.assertIn("frozen_conditions", payload)
        self.assertTrue(payload["solution_preparation_uses"])
        self.assertTrue(payload["process_execution_members"])

    def test_batch_export_pdf(self) -> None:
        exp_id = self._create_released_experiment()
        created = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        )
        batch_id = created.json()["id"]
        exported = self.client.get(
            f"/experiments/{exp_id}/batches/{batch_id}/export.pdf"
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertTrue(exported.content.startswith(b"%PDF-"))

    def test_child_resource_path_must_match_batch(self) -> None:
        exp_id = self._create_released_experiment()
        first = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        ).json()
        second = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        ).json()
        preparations = self.client.get(
            f"/api/fabrication-batches/{first['id']}/solution-preparations"
        ).json()
        response = self.client.patch(
            f"/api/fabrication-batches/{second['id']}/solution-preparations/{preparations[0]['id']}",
            json={"status": "ready"},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_deviation_rejects_multiple_and_cross_batch_targets(self) -> None:
        exp_id = self._create_released_experiment()
        first = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        ).json()
        second = self.client.post(
            f"/api/experiments/{exp_id}/fabrication-batches", json={}
        ).json()
        preparation = self.client.get(
            f"/api/fabrication-batches/{first['id']}/solution-preparations"
        ).json()[0]
        execution = self.client.get(
            f"/api/fabrication-batches/{first['id']}/process-executions"
        ).json()[0]
        multiple = self.client.post(
            f"/api/fabrication-batches/{first['id']}/deviations",
            json={
                "category": "process",
                "severity": "warning",
                "description": "invalid multiple targets",
                "solution_preparation_id": preparation["id"],
                "process_execution_id": execution["id"],
            },
        )
        self.assertEqual(multiple.status_code, 422, multiple.text)
        cross_batch = self.client.post(
            f"/api/fabrication-batches/{second['id']}/deviations",
            json={
                "category": "material",
                "severity": "warning",
                "description": "invalid cross batch target",
                "solution_preparation_id": preparation["id"],
            },
        )
        self.assertEqual(cross_batch.status_code, 400, cross_batch.text)


class SolutionPreparationTests(unittest.TestCase):
    """Test solution preparation grouping and management."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "prep.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(self.repository, "prep-test")
        )
        self._batch_id = asyncio.run(self._create_batch())

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    async def _create_batch(self) -> int:
        batch = await self.repository.create_fabrication_batch(self._experiment_id, actor_user_id=1)
        return batch.id

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_preparations_created_on_batch_create(self) -> None:
        import asyncio
        preps = asyncio.run(self.repository.list_solution_preparations(self._batch_id))
        self.assertGreaterEqual(len(preps), 1)
        for p in preps:
            self.assertEqual(len(p.planned_canonical_hash), 64)
            self.assertEqual(p.planned_snapshot_schema_version, 1)
            self.assertEqual(
                p.planned_canonical_hash,
                snapshot_hash(p.planned_solution_snapshot),
            )

    def test_preparation_uses_created(self) -> None:
        import asyncio
        preps = asyncio.run(self.repository.list_solution_preparations(self._batch_id))
        if preps:
            uses = asyncio.run(self.repository.list_solution_preparation_uses(preps[0].id))
            self.assertGreaterEqual(len(uses), 1)

    def test_update_preparation_status(self) -> None:
        import asyncio
        preps = asyncio.run(self.repository.list_solution_preparations(self._batch_id))
        if preps:
            updated = asyncio.run(self.repository.update_solution_preparation(
                preps[0].id, status=PreparationStatus.READY, actor_user_id=1,
            ))
            self.assertEqual(updated.status, PreparationStatus.READY)

    def test_update_preparation_actual(self) -> None:
        import asyncio
        preps = asyncio.run(self.repository.list_solution_preparations(self._batch_id))
        if preps:
            updated = asyncio.run(self.repository.update_solution_preparation(
                preps[0].id, actual_matches_planned=True, actor_user_id=1,
            ))
            self.assertEqual(
                updated.actual_solution_snapshot,
                updated.planned_solution_snapshot,
            )
            self.assertEqual(updated.actual_recording_mode, "copied_from_plan")
            self.assertEqual(
                updated.actual_canonical_hash,
                updated.planned_canonical_hash,
            )

    def test_shared_preparation_can_split_and_merge_only_identical_hashes(self) -> None:
        import asyncio
        preps = asyncio.run(self.repository.list_solution_preparations(self._batch_id))
        shared = next(
            item
            for item in preps
            if len(asyncio.run(self.repository.list_solution_preparation_uses(item.id))) > 1
        )
        uses = asyncio.run(self.repository.list_solution_preparation_uses(shared.id))
        split = asyncio.run(
            self.repository.split_solution_preparation(
                shared.id,
                member_ids=[uses[0]["id"]],
                actor_user_id=1,
            )
        )
        self.assertEqual(split.planned_canonical_hash, shared.planned_canonical_hash)
        merged = asyncio.run(
            self.repository.merge_solution_preparations(
                shared.id,
                source_id=split.id,
                actor_user_id=1,
            )
        )
        self.assertEqual(merged.id, shared.id)

        other = next(
            (item for item in preps if item.planned_canonical_hash != shared.planned_canonical_hash),
            None,
        )
        if other is not None:
            with self.assertRaises(ValueError):
                asyncio.run(
                    self.repository.merge_solution_preparations(
                        shared.id,
                        source_id=other.id,
                        actor_user_id=1,
                    )
                )


class ProcessExecutionTests(unittest.TestCase):
    """Test process execution grouping and management."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "exec.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository,
                "exec-test",
                gas_backfill_stages=[
                    {
                        "gas": "N2",
                        "flow_sccm": 30,
                        "target_pressure_pa": 15,
                        "hold_seconds": 20,
                    }
                ],
                vcd_step_sequence=[
                    "vcd_stage1",
                    "gas_backfill_stage1",
                    "vcd_stage2",
                    "vcd_stage3",
                ],
            )
        )
        self._batch_id = asyncio.run(self._create_batch())

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    async def _create_batch(self) -> int:
        batch = await self.repository.create_fabrication_batch(self._experiment_id, actor_user_id=1)
        return batch.id

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_executions_created_on_batch_create(self) -> None:
        import asyncio
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        self.assertGreaterEqual(len(execs), 1)
        methods = {item.method for item in execs}
        self.assertTrue(
            {"spin_coating", "vcd", "annealing", "thermal_evaporation", "ald"}
            .issubset(methods)
        )
        for item in execs:
            self.assertEqual(item.planned_snapshot_schema_version, 1)
            self.assertEqual(
                item.planned_canonical_hash,
                snapshot_hash(item.planned_process_snapshot),
            )

    def test_vcd_execution_includes_planned_mfc_gas_backfill(self) -> None:
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        vcd = next(item for item in execs if item.method == "vcd")

        self.assertEqual(
            vcd.planned_process_snapshot["gas_backfill_stages"],
            [
                {
                    "gas": "N2",
                    "flow_sccm": 30.0,
                    "target_pressure_pa": 15,
                    "hold_seconds": 20,
                }
            ],
        )
        self.assertEqual(
            vcd.planned_process_snapshot["vcd_step_sequence"],
            [
                "vcd_stage1",
                "gas_backfill_stage1",
                "vcd_stage2",
                "vcd_stage3",
            ],
        )

    def test_identical_parameters_do_not_merge_different_material_layers(self) -> None:
        import asyncio
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        matching = [
            item
            for item in execs
            if item.method == "thermal_evaporation"
            and item.planned_process_snapshot.get("thickness_nm") == 20.0
            and item.planned_process_snapshot.get("rate_angstrom_per_s") == 0.2
        ]
        self.assertGreaterEqual(len(matching), 2)
        self.assertGreaterEqual(len({item.layer_type for item in matching}), 2)

    def test_execution_members_created(self) -> None:
        import asyncio
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        if execs:
            members = asyncio.run(self.repository.list_process_execution_members(execs[0].id))
            self.assertGreaterEqual(len(members), 1)

    def test_update_execution_status(self) -> None:
        import asyncio
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        if execs:
            updated = asyncio.run(self.repository.update_process_execution(
                execs[0].id, status=ExecutionStatus.RUNNING, actor_user_id=1,
            ))
            self.assertEqual(updated.status, ExecutionStatus.RUNNING)

    def test_update_execution_actual(self) -> None:
        import asyncio
        execs = asyncio.run(self.repository.list_process_executions(self._batch_id))
        if execs:
            updated = asyncio.run(self.repository.update_process_execution(
                execs[0].id, actual_matches_planned=True, actor_user_id=1,
            ))
            self.assertEqual(
                updated.actual_process_snapshot,
                updated.planned_process_snapshot,
            )
            self.assertEqual(updated.actual_recording_mode, "copied_from_plan")
            self.assertEqual(
                updated.actual_canonical_hash,
                updated.planned_canonical_hash,
            )

    def test_shared_execution_can_split_and_merge(self) -> None:
        import asyncio
        executions = asyncio.run(self.repository.list_process_executions(self._batch_id))
        shared = next(
            item
            for item in executions
            if len(asyncio.run(self.repository.list_process_execution_members(item.id))) > 1
        )
        members = asyncio.run(self.repository.list_process_execution_members(shared.id))
        split = asyncio.run(
            self.repository.split_process_execution(
                shared.id,
                member_ids=[members[0]["id"]],
                actor_user_id=1,
            )
        )
        self.assertEqual(split.planned_canonical_hash, shared.planned_canonical_hash)
        merged = asyncio.run(
            self.repository.merge_process_executions(
                shared.id,
                source_id=split.id,
                actor_user_id=1,
            )
        )
        self.assertEqual(merged.id, shared.id)


class DeviationTests(unittest.TestCase):
    """Test append-only deviation recording."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "dev.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(self.repository, "dev-test")
        )
        self._batch_id = asyncio.run(self._create_batch())

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    async def _create_batch(self) -> int:
        batch = await self.repository.create_fabrication_batch(self._experiment_id, actor_user_id=1)
        return batch.id

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    # 24. Deviation append-only
    def test_deviation_append_only(self) -> None:
        import asyncio
        dev = asyncio.run(self.repository.create_deviation(
            fabrication_batch_id=self._batch_id,
            category="process", severity="warning",
            description="Temperature deviation",
            actor_user_id=1,
        ))
        self.assertIsNotNone(dev.id)
        loaded = asyncio.run(self.repository.get_deviation(dev.id))
        self.assertEqual(loaded.description, "Temperature deviation")

    # 25. Superseding deviation preserves old record
    def test_superseding_deviation(self) -> None:
        import asyncio
        dev1 = asyncio.run(self.repository.create_deviation(
            fabrication_batch_id=self._batch_id,
            category="process", severity="warning",
            description="Initial deviation",
            actor_user_id=1,
        ))
        dev2 = asyncio.run(self.repository.create_deviation(
            fabrication_batch_id=self._batch_id,
            category="process", severity="error",
            description="Superseding deviation",
            supersedes_deviation_id=dev1.id,
            actor_user_id=1,
        ))
        self.assertEqual(dev2.supersedes_deviation_id, dev1.id)
        # Old record is still accessible
        loaded = asyncio.run(self.repository.get_deviation(dev1.id))
        self.assertEqual(loaded.description, "Initial deviation")

    def test_deviation_validates_category(self) -> None:
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.create_deviation(
                fabrication_batch_id=self._batch_id,
                category="invalid", severity="warning",
                description="Bad category",
                actor_user_id=1,
            ))

    def test_deviation_blank_description_rejected(self) -> None:
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.create_deviation(
                fabrication_batch_id=self._batch_id,
                category="process", severity="warning",
                description="   ",
                actor_user_id=1,
            ))


class BatchCompletionMaterializesActualCountsTests(unittest.TestCase):
    """Completing a batch must make the recorded actual counts structurally
    true: extra substrates, their devices, and their execution membership all
    exist after the ``in_progress -> completed`` transition."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "fab-actual.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        self.experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "fab-actual"
            )
        )
        self.batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.READY, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
            )
        )
        for preparation in asyncio.run(
            self.repository.list_solution_preparations(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(
            self.repository.list_process_executions(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )
        self.conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(self.batch.id)
        )
        self.control = next(
            condition for condition in self.conditions if condition.role == "control"
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _substrates_for_condition(self, condition_id: int):
        rows = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(self.batch.id)
        )
        return sorted(
            (row for row in rows if row.batch_condition_id == condition_id),
            key=lambda row: row.substrate_ordinal,
        )

    def _complete(self, actual_by_condition_id: dict) -> None:
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts=actual_by_condition_id,
                actor_user_id=1,
            )
        )

    def test_completion_above_planned_materializes_rows(self) -> None:
        self._complete({condition.id: 5 for condition in self.conditions})

        rows = self._substrates_for_condition(self.control.id)
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [row.substrate_ordinal for row in rows], [1, 2, 3, 4, 5]
        )
        self.assertEqual(
            [row.substrate_code for row in rows],
            [
                f"{self.batch.batch_code}-{self.control.condition_code}-S0{index}"
                for index in range(1, 6)
            ],
        )
        self.assertTrue(
            all(row.substrate_mark is None for row in rows),
            "extra substrates must stay unmarked until a CSV associates them",
        )

        layout = fixture_layout("15x15_dual_005")
        devices = asyncio.run(
            self.repository.get_fabrication_devices_for_batch(self.batch.id)
        )
        for substrate in rows[3:]:
            substrate_devices = sorted(
                (
                    device
                    for device in devices
                    if device.substrate_id == substrate.id
                ),
                key=lambda device: device.device_ordinal,
            )
            self.assertEqual(
                [device.device_ordinal for device in substrate_devices],
                list(range(1, layout.devices_per_substrate + 1)),
            )
            self.assertEqual(
                [device.device_code for device in substrate_devices],
                [
                    f"{substrate.substrate_code}-D0{index}"
                    for index in range(1, layout.devices_per_substrate + 1)
                ],
            )

    def test_extra_substrates_join_every_layer_execution_group(self) -> None:
        self._complete({condition.id: 5 for condition in self.conditions})

        executions = asyncio.run(
            self.repository.list_process_executions(self.batch.id)
        )
        self.assertTrue(executions)
        control_substrate_ids = {
            row.id for row in self._substrates_for_condition(self.control.id)
        }
        for execution in executions:
            members = asyncio.run(
                self.repository.list_process_execution_members(execution.id)
            )
            member_pairs = {
                (int(member["substrate_id"]), int(member["layer_ordinal"]))
                for member in members
            }
            if not any(
                int(member["batch_condition_id"]) == self.control.id
                for member in members
            ):
                continue
            layer_ordinals = {
                int(member["layer_ordinal"])
                for member in members
                if int(member["batch_condition_id"]) == self.control.id
            }
            for layer_ordinal in layer_ordinals:
                self.assertEqual(
                    {
                        substrate_id
                        for (substrate_id, ordinal) in member_pairs
                        if ordinal == layer_ordinal
                    }
                    & control_substrate_ids,
                    control_substrate_ids,
                    f"execution {execution.execution_code} layer {layer_ordinal} "
                    "must include every actual substrate of the condition",
                )

        # The run-sheet export reports the new substrates under the batch.
        sheet = asyncio.run(self.repository.get_batch_run_sheet(self.batch.id))
        sheet_codes = {
            substrate.substrate_code for substrate in sheet["substrates"]
        }
        self.assertTrue(
            {row.substrate_code for row in self._substrates_for_condition(self.control.id)}
            <= sheet_codes
        )

    def test_failed_completion_rolls_back_and_retry_does_not_duplicate(self) -> None:
        # A completion payload missing one condition fails validation.
        with self.assertRaisesRegex(ValueError, "must cover exactly"):
            self._complete({self.control.id: 5})
        self.assertEqual(len(self._substrates_for_condition(self.control.id)), 3)

        self._complete({condition.id: 5 for condition in self.conditions})
        self.assertEqual(len(self._substrates_for_condition(self.control.id)), 5)

        # Repeated completion is rejected by the state machine and leaves no
        # duplicate substrate/device/member rows behind.
        with self.assertRaisesRegex(ValueError, "cannot change"):
            self._complete({condition.id: 5 for condition in self.conditions})
        self.assertEqual(len(self._substrates_for_condition(self.control.id)), 5)
        devices = asyncio.run(
            self.repository.get_fabrication_devices_for_batch(self.batch.id)
        )
        layout = fixture_layout("15x15_dual_005")
        self.assertEqual(len(devices), 2 * 5 * layout.devices_per_substrate)

    def test_completion_still_rejects_negative_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "negative"):
            self._complete({condition.id: -1 for condition in self.conditions})
        self.assertEqual(len(self._substrates_for_condition(self.control.id)), 3)


class BatchCompletionAtomicityTests(unittest.TestCase):
    """Completion with embedded shortfall deviations must be a single
    transaction: deviations, actual counts, materialized rows, the status
    change, and the audit event commit together or not at all."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "fab-atomic.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        self.experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "fab-atomic"
            )
        )
        self.batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.READY, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
            )
        )
        self.conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(self.batch.id)
        )
        self.control = next(
            condition for condition in self.conditions if condition.role == "control"
        )
        self.target = next(
            condition for condition in self.conditions if condition.role != "control"
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _terminate_steps(self) -> None:
        for preparation in asyncio.run(
            self.repository.list_solution_preparations(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(
            self.repository.list_process_executions(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )

    def _complete_with_shortfalls(self, shortfall_deviations):
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 2 for c in self.conditions},
                shortfall_deviations=shortfall_deviations,
                actor_user_id=1,
            )
        )

    def _condition_states(self):
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(self.batch.id)
        )
        return {condition.id: condition.actual_substrate_count for condition in conditions}

    def test_shortfall_deviations_and_completion_commit_atomically(self) -> None:
        shortfall_deviations = [
            (self.control.id, "Control lost one substrate to breakage."),
            (self.target.id, "Target group stopped after two substrates."),
        ]
        # Preparations are still open, so the later completion validation
        # fails after the deviations would have been inserted.
        with self.assertRaisesRegex(ValueError, "solution preparations"):
            self._complete_with_shortfalls(shortfall_deviations)

        self.assertEqual(asyncio.run(self.repository.list_deviations(self.batch.id)), [])
        self.assertEqual(
            self._condition_states(),
            {condition.id: None for condition in self.conditions},
        )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)
        substrates = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(self.batch.id)
        )
        self.assertEqual(len(substrates), 2 * 3)

        # Retry after fixing the blocker: everything commits together.
        self._terminate_steps()
        self._complete_with_shortfalls(shortfall_deviations)

        deviations = asyncio.run(self.repository.list_deviations(self.batch.id))
        self.assertEqual(len(deviations), 2)
        by_condition = {deviation.condition_id: deviation for deviation in deviations}
        self.assertEqual(set(by_condition), {self.control.id, self.target.id})
        for condition in self.conditions:
            deviation = by_condition[condition.id]
            self.assertEqual(deviation.category, "substrate")
            self.assertEqual(deviation.severity, "warning")
            self.assertEqual(deviation.planned_value, {"substrate_count": 3})
            self.assertEqual(deviation.actual_value, {"substrate_count": 2})
            self.assertEqual(deviation.recorded_by_id, 1)
            self.assertTrue(deviation.description)
        self.assertEqual(
            self._condition_states(),
            {condition.id: 2 for condition in self.conditions},
        )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.COMPLETED)

        from web.database import audit_events

        async def audit_rows():
            async with self.app.state.database.engine.connect() as connection:
                rows = await connection.execute(
                    select(audit_events.c.action, audit_events.c.details).where(
                        audit_events.c.entity_id == str(self.batch.id)
                    )
                )
                return rows.all()

        rows = asyncio.run(audit_rows())
        self.assertTrue(
            any(
                action == "batch.status_change"
                and row_details.get("to") == "completed"
                for action, row_details in rows
            ),
            rows,
        )

    def test_shortfall_explanations_are_validated(self) -> None:
        self._terminate_steps()

        with self.assertRaisesRegex(ValueError, "unknown"):
            self._complete_with_shortfalls([(999999, "unknown condition")])
        with self.assertRaisesRegex(ValueError, "blank"):
            self._complete_with_shortfalls([(self.control.id, "   ")])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self._complete_with_shortfalls(
                [
                    (self.control.id, "first"),
                    (self.control.id, "second"),
                ]
            )
        # A condition without a shortfall must not carry an explanation.
        with self.assertRaisesRegex(ValueError, "no shortfall"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    self.batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 3 for c in self.conditions},
                    shortfall_deviations=[(self.control.id, "not needed")],
                    actor_user_id=1,
                )
            )
        self.assertEqual(asyncio.run(self.repository.list_deviations(self.batch.id)), [])
        self.assertEqual(
            self._condition_states(),
            {condition.id: None for condition in self.conditions},
        )

    def test_audit_event_records_completion_counts_and_new_rows(self) -> None:
        from web.database import audit_events
        from sqlalchemy import select

        self._terminate_steps()
        self._complete_with_shortfalls([
            (self.control.id, "control shortfall"),
            (self.target.id, "target shortfall"),
        ])
        async def audit_rows():
            async with self.app.state.database.engine.connect() as connection:
                rows = await connection.execute(
                    select(audit_events.c.action, audit_events.c.details).where(
                        audit_events.c.entity_id == str(self.batch.id)
                    )
                )
                return rows.all()
        rows = asyncio.run(audit_rows())
        completion_audit = [
            details for action, details in rows
            if action == "batch.status_change" and details.get("to") == "completed"
        ]
        self.assertEqual(len(completion_audit), 1)
        details = completion_audit[0]
        self.assertIn("actual_substrate_counts", details)
        self.assertEqual(details["new_shortfall_deviations"], 2)
        self.assertEqual(details["new_substrates"], 0)
        self.assertEqual(details["new_devices"], 0)
        self.assertEqual(details["new_execution_members"], 0)

    def test_audit_records_real_member_count_on_actual_above_planned(self) -> None:
        from web.database import audit_events
        from sqlalchemy import select

        self._terminate_steps()
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 5 for c in self.conditions},
                shortfall_deviations=[],
                actor_user_id=1,
            )
        )
        async def audit_rows():
            async with self.app.state.database.engine.connect() as connection:
                rows = await connection.execute(
                    select(audit_events.c.action, audit_events.c.details).where(
                        audit_events.c.entity_id == str(self.batch.id)
                    )
                )
                return rows.all()
        rows = asyncio.run(audit_rows())
        details = [
            d for a, d in rows
            if a == "batch.status_change" and d.get("to") == "completed"
        ][0]
        self.assertEqual(details["new_substrates"], 4)  # 2 conditions × (5-3)
        self.assertGreater(details["new_execution_members"], 0)

    def test_missing_execution_group_rolls_back_completion(self) -> None:
        from web.database import process_execution_members
        from sqlalchemy import delete

        self._terminate_steps()
        # Delete all execution members for the control condition so the
        # new substrates have no group to attach to.
        async def wipe():
            async with self.app.state.database.engine.begin() as conn:
                await conn.execute(
                    delete(process_execution_members).where(
                        process_execution_members.c.batch_condition_id
                        == self.control.id
                    )
                )
        asyncio.run(wipe())
        # Completion with actual > planned must fail because the control
        # condition has no execution groups.
        with self.assertRaisesRegex(ValueError, "no frozen execution groups"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    self.batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 5 for c in self.conditions},
                    shortfall_deviations=[],
                    actor_user_id=1,
                )
            )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)

    def test_missing_one_layer_group_rolls_back_completion(self) -> None:
        """Keep one execution group but delete another required layer's group.
        Completion with actual > planned must fail before inserting anything
        because not all required layer ordinals have groups."""
        from web.database import process_execution_members
        from sqlalchemy import delete, select as sa_select

        self._terminate_steps()
        # Find the distinct layer ordinals that have execution members.
        async def get_ordinals():
            async with self.app.state.database.engine.connect() as conn:
                rows = await conn.execute(
                    sa_select(
                        process_execution_members.c.layer_ordinal
                    )
                    .distinct()
                    .where(
                        process_execution_members.c.batch_condition_id
                        == self.control.id
                    )
                )
                return sorted(int(r) for r in rows.scalars().all())

        ordinals = asyncio.run(get_ordinals())
        self.assertGreaterEqual(
            len(ordinals), 2, f"expected ≥2 layer ordinals, got {ordinals}"
        )
        # Delete members for one required layer ordinal, keep the rest.
        victim_ordinal = ordinals[0]

        async def wipe_one():
            async with self.app.state.database.engine.begin() as conn:
                await conn.execute(
                    delete(process_execution_members).where(
                        process_execution_members.c.batch_condition_id
                        == self.control.id,
                        process_execution_members.c.layer_ordinal
                        == victim_ordinal,
                    )
                )

        asyncio.run(wipe_one())
        # Completion with actual > planned must fail because the victim
        # layer's group is missing.
        with self.assertRaisesRegex(ValueError, "missing frozen execution groups"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    self.batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 5 for c in self.conditions},
                    shortfall_deviations=[],
                    actor_user_id=1,
                )
            )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)
        # The surviving group's members must still be intact (no partial insert).
        survivors = asyncio.run(get_ordinals())
        self.assertIn(ordinals[1], survivors)

    def test_pre_check_blocks_all_writes_when_one_condition_fails(self) -> None:
        """Two conditions: control would pass materialization, but target
        is missing a required layer group.  The full-condition pre-check must
        reject the completion BEFORE any substrate, device, or member is
        inserted for EITHER condition — no partial writes."""
        from web.database import (
            fabrication_substrates as fs_table,
            fabrication_devices as fd_table,
            process_execution_members as pem_table,
        )
        from sqlalchemy import delete, select as sa_select, func as sa_func

        self._terminate_steps()
        # Count rows before the attempt.
        async def count_rows():
            async with self.app.state.database.engine.connect() as conn:
                sub = await conn.scalar(
                    sa_select(sa_func.count()).select_from(fs_table)
                    .where(
                        fs_table.c.batch_condition_id.in_(
                            [self.control.id, self.target.id]
                        )
                    )
                )
                dev = await conn.scalar(
                    sa_select(sa_func.count()).select_from(fd_table)
                    .where(
                        fd_table.c.substrate_id.in_(
                            sa_select(fs_table.c.id).where(
                                fs_table.c.batch_condition_id.in_(
                                    [self.control.id, self.target.id]
                                )
                            )
                        )
                    )
                )
                mem = await conn.scalar(
                    sa_select(sa_func.count()).select_from(pem_table)
                    .where(
                        pem_table.c.batch_condition_id.in_(
                            [self.control.id, self.target.id]
                        )
                    )
                )
                return int(sub or 0), int(dev or 0), int(mem or 0)

        # Delete one required layer group for the target condition only.
        async def get_target_ordinals():
            async with self.app.state.database.engine.connect() as conn:
                rows = await conn.execute(
                    sa_select(pem_table.c.layer_ordinal).distinct().where(
                        pem_table.c.batch_condition_id == self.target.id
                    )
                )
                return sorted(int(r) for r in rows.scalars().all())

        target_ordinals = asyncio.run(get_target_ordinals())
        self.assertGreaterEqual(len(target_ordinals), 2)
        victim = target_ordinals[0]

        async def wipe_target_layer():
            async with self.app.state.database.engine.begin() as conn:
                await conn.execute(
                    delete(pem_table).where(
                        pem_table.c.batch_condition_id == self.target.id,
                        pem_table.c.layer_ordinal == victim,
                    )
                )

        asyncio.run(wipe_target_layer())

        # Count rows AFTER the wipe (this is the baseline for "no partial
        # writes" — the failed completion must not add anything).
        before_sub, before_dev, before_mem = asyncio.run(count_rows())

        # Attempt completion with actual > planned for BOTH conditions.
        # The pre-check must detect target's missing group and reject
        # the entire operation before inserting anything.
        with self.assertRaisesRegex(ValueError, "missing frozen execution groups"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    self.batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 5 for c in self.conditions},
                    shortfall_deviations=[],
                    actor_user_id=1,
                )
            )

        # No partial writes: row counts unchanged for both conditions.
        after_sub, after_dev, after_mem = asyncio.run(count_rows())
        self.assertEqual(
            after_sub, before_sub,
            f"substrate count changed: {before_sub} → {after_sub}"
        )
        self.assertEqual(
            after_dev, before_dev,
            f"device count changed: {before_dev} → {after_dev}"
        )
        self.assertEqual(
            after_mem, before_mem,
            f"member count changed: {before_mem} → {after_mem}"
        )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)

    def test_pre_check_blocks_writes_when_second_condition_has_no_groups(self) -> None:
        """Two conditions: control has groups and would pass, but target has
        ZERO execution groups (all members deleted).  The full-condition
        pre-check must reject before any write for either condition."""
        from web.database import (
            fabrication_substrates as fs_table,
            fabrication_devices as fd_table,
            process_execution_members as pem_table,
        )
        from sqlalchemy import delete, select as sa_select, func as sa_func

        self._terminate_steps()
        # Wipe ALL execution members for the target condition.
        async def wipe_all():
            async with self.app.state.database.engine.begin() as conn:
                await conn.execute(
                    delete(pem_table).where(
                        pem_table.c.batch_condition_id == self.target.id
                    )
                )
        asyncio.run(wipe_all())

        # Count rows after the wipe (baseline for "no partial writes").
        async def count_rows():
            async with self.app.state.database.engine.connect() as conn:
                sub = await conn.scalar(
                    sa_select(sa_func.count()).select_from(fs_table)
                    .where(
                        fs_table.c.batch_condition_id.in_(
                            [self.control.id, self.target.id]
                        )
                    )
                )
                dev = await conn.scalar(
                    sa_select(sa_func.count()).select_from(fd_table)
                    .where(
                        fd_table.c.substrate_id.in_(
                            sa_select(fs_table.c.id).where(
                                fs_table.c.batch_condition_id.in_(
                                    [self.control.id, self.target.id]
                                )
                            )
                        )
                    )
                )
                mem = await conn.scalar(
                    sa_select(sa_func.count()).select_from(pem_table)
                    .where(
                        pem_table.c.batch_condition_id.in_(
                            [self.control.id, self.target.id]
                        )
                    )
                )
                return int(sub or 0), int(dev or 0), int(mem or 0)

        before_sub, before_dev, before_mem = asyncio.run(count_rows())

        # Completion with actual > planned for BOTH conditions must fail
        # in the pre-check because target has no execution groups.
        with self.assertRaisesRegex(ValueError, "no frozen execution groups"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    self.batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 5 for c in self.conditions},
                    shortfall_deviations=[],
                    actor_user_id=1,
                )
            )

        # No partial writes for either condition.
        after_sub, after_dev, after_mem = asyncio.run(count_rows())
        self.assertEqual(after_sub, before_sub, f"substrate: {before_sub} → {after_sub}")
        self.assertEqual(after_dev, before_dev, f"device: {before_dev} → {after_dev}")
        self.assertEqual(after_mem, before_mem, f"member: {before_mem} → {after_mem}")
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)

    def test_preexisting_fabrication_shortfall_does_not_satisfy_gate(self) -> None:
        """A fabrication_shortfall deviation declared before the completion
        PATCH does NOT satisfy the gate — each actual<planned condition must
        carry its own embedded shortfall_deviation in the completion PATCH."""
        self._terminate_steps()
        asyncio.run(
            self.repository.create_deviation(
                fabrication_batch_id=self.batch.id,
                category="substrate",
                severity="info",
                description="Pre-declared shortfall",
                condition_id=self.control.id,
                deviation_type="fabrication_shortfall",
                actor_user_id=1,
            )
        )
        # Completion WITHOUT an embedded shortfall for the control condition
        # must fail even though a pre-existing fabrication_shortfall exists.
        with self.assertRaisesRegex(ValueError, "shortfall"):
            self._complete_with_shortfalls([(self.target.id, "target shortfall")])
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.IN_PROGRESS)

        # Retry with an embedded shortfall for every short condition succeeds.
        self._complete_with_shortfalls([
            (self.control.id, "control shortfall"),
            (self.target.id, "target shortfall"),
        ])
        deviations = asyncio.run(self.repository.list_deviations(self.batch.id))
        self.assertEqual(len(deviations), 3)
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.COMPLETED)


class DeviationTypeGateTests(unittest.TestCase):
    """Only a matching, non-superseded typed condition deviation unlocks the
    fabrication-shortfall (completion) gate; general deviations never do."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "fab-types.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        self.experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "fab-types"
            )
        )
        self.batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.READY, actor_user_id=1
            )
        )
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
            )
        )
        self.conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(self.batch.id)
        )
        self.control = next(
            condition for condition in self.conditions if condition.role == "control"
        )
        self.target = next(
            condition for condition in self.conditions if condition.role != "control"
        )
        for preparation in asyncio.run(
            self.repository.list_solution_preparations(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(
            self.repository.list_process_executions(self.batch.id)
        ):
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=self.batch.id,
                    actor_user_id=1,
                )
            )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _complete(self, actual_by_id, shortfall=None):
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                self.batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts=actual_by_id,
                shortfall_deviations=shortfall,
                actor_user_id=1,
            )
        )

    def test_general_deviation_does_not_unlock_the_shortfall_gate(self) -> None:
        asyncio.run(
            self.repository.create_deviation(
                fabrication_batch_id=self.batch.id,
                category="operator",
                severity="info",
                description="Unrelated operator note",
                condition_id=self.control.id,
                actor_user_id=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "explaining the shortfall"):
            self._complete(
                {c.id: (2 if c.id == self.control.id else 3) for c in self.conditions}
            )
        self.assertEqual(asyncio.run(self.repository.list_deviations(self.batch.id))[0].deviation_type, "general")

    def test_qualifying_fabrication_shortfall_unlocks_the_gate(self) -> None:
        """A fabrication_shortfall deviation embedded in the completion PATCH
        (not a pre-existing one) satisfies the gate."""
        self._complete(
            {c.id: (2 if c.id == self.control.id else 3) for c in self.conditions},
            shortfall=[(self.control.id, "Two usable substrates only.")],
        )
        batch = asyncio.run(self.repository.get_fabrication_batch(self.batch.id))
        self.assertEqual(batch.status, BatchStatus.COMPLETED)
        deviations = asyncio.run(self.repository.list_deviations(self.batch.id))
        self.assertEqual(deviations[0].deviation_type, "fabrication_shortfall")

    def test_superseded_shortfall_no_longer_unlocks_the_gate(self) -> None:
        """A superseded pre-existing shortfall does not satisfy the gate; the
        completion PATCH must carry its own embedded shortfall."""
        first = asyncio.run(
            self.repository.create_deviation(
                fabrication_batch_id=self.batch.id,
                category="substrate",
                severity="warning",
                description="Initially reported shortfall",
                condition_id=self.control.id,
                deviation_type="fabrication_shortfall",
                actor_user_id=1,
            )
        )
        asyncio.run(
            self.repository.create_deviation(
                fabrication_batch_id=self.batch.id,
                category="substrate",
                severity="info",
                description="Correction: the shortfall record was wrong",
                condition_id=self.control.id,
                supersedes_deviation_id=first.id,
                actor_user_id=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "shortfall"):
            self._complete(
                {c.id: (2 if c.id == self.control.id else 3) for c in self.conditions}
            )

    def test_shortfall_for_another_condition_does_not_unlock(self) -> None:
        asyncio.run(
            self.repository.create_deviation(
                fabrication_batch_id=self.batch.id,
                category="substrate",
                severity="warning",
                description="Shortfall declared on the wrong condition",
                condition_id=self.target.id,
                deviation_type="fabrication_shortfall",
                actor_user_id=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "Control"):
            self._complete(
                {c.id: (2 if c.id == self.control.id else 3) for c in self.conditions}
            )

    def test_embedded_shortfall_records_the_fabrication_type(self) -> None:
        self._complete(
            {c.id: (2 if c.id == self.control.id else 3) for c in self.conditions},
            shortfall=[(self.control.id, "Control lost one substrate.")],
        )
        deviations = asyncio.run(self.repository.list_deviations(self.batch.id))
        self.assertEqual([d.deviation_type for d in deviations], ["fabrication_shortfall"])
        self.assertEqual(deviations[0].planned_value, {"substrate_count": 3})
        self.assertEqual(deviations[0].actual_value, {"substrate_count": 2})

    def test_zero_actual_count_uses_the_same_typed_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "explaining the shortfall"):
            self._complete(
                {c.id: (0 if c.id == self.control.id else 3) for c in self.conditions}
            )
        self._complete(
            {c.id: (0 if c.id == self.control.id else 3) for c in self.conditions},
            shortfall=[(self.control.id, "Whole group abandoned: solution failed QC.")],
        )
        deviations = asyncio.run(self.repository.list_deviations(self.batch.id))
        self.assertEqual(deviations[0].deviation_type, "fabrication_shortfall")
        self.assertEqual(deviations[0].actual_value, {"substrate_count": 0})


class FabricationBatchGuardTests(unittest.TestCase):
    """Batch-creation window and the zero-batch plan-status guards.

    Results upload is keyed per fabrication batch, so the plan lifecycle must
    never reach a state where fabrication can be finished without a batch:
    starting fabrication requires one, completing fabrication requires one,
    and batch creation stays available while fabrication is in progress as a
    recovery path."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "batch-guard.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(self.repository, "batch-guard")
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_start_fabrication_requires_a_frozen_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one fabrication batch"):
            asyncio.run(self.repository.update_plan_status(
                self._experiment_id, PlanStatus.IN_PROGRESS, actor_user_id=1,
            ))

    def test_batch_creation_stays_available_while_in_progress(self) -> None:
        batch = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        asyncio.run(self.repository.update_fabrication_batch_status(
            batch.id, BatchStatus.READY, actor_user_id=1,
        ))
        asyncio.run(self.repository.update_fabrication_batch_status(
            batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1,
        ))
        asyncio.run(self.repository.update_plan_status(
            self._experiment_id, PlanStatus.IN_PROGRESS, actor_user_id=1,
        ))
        # Recovery path: a student who started fabrication without freezing a
        # batch (or who needs a second one) can still freeze it now.
        recovered = asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))
        self.assertEqual(recovered.status, BatchStatus.DRAFT)

    def test_batch_creation_still_rejected_outside_the_window(self) -> None:
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        asyncio.run(self.repository.create_campaign(
            code="batch-guard-draft", display_name="Batch guard draft",
            description="", actor_user_id=1,
        ))
        dr, dp = complete_guided_setup()
        for group in dr["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in dr["layers"]]
                group["deposition_process"] = json.loads(json.dumps(dp))
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(dp), "device_recipe": dr,
        })
        record = asyncio.run(self.repository.add_experiment(
            recipe, campaign_id="batch-guard-draft", actor_user_id=1,
        ))
        with self.assertRaisesRegex(ValueError, "'released' or 'in_progress'"):
            asyncio.run(self.repository.create_fabrication_batch(
                record.id, actor_user_id=1,
            ))

    def test_zero_batch_guard_rejects_before_any_batch_is_frozen(self) -> None:
        from web.repository.condition import _require_fabrication_batches

        async def run() -> None:
            async with self.repository.database.begin() as connection:
                for target in (PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED):
                    with self.assertRaisesRegex(ValueError, "at least one fabrication batch"):
                        await _require_fabrication_batches(
                            connection, self._experiment_id, target,
                        )
                # Non-fabrication transitions are never blocked.
                await _require_fabrication_batches(
                    connection, self._experiment_id, PlanStatus.PENDING_APPROVAL,
                )

        asyncio.run(run())

    def test_zero_batch_guard_passes_once_a_batch_exists(self) -> None:
        from web.repository.condition import _require_fabrication_batches

        asyncio.run(self.repository.create_fabrication_batch(
            self._experiment_id, actor_user_id=1,
        ))

        async def run() -> None:
            async with self.repository.database.begin() as connection:
                await _require_fabrication_batches(
                    connection, self._experiment_id, PlanStatus.IN_PROGRESS,
                )
                await _require_fabrication_batches(
                    connection, self._experiment_id, PlanStatus.COMPLETED,
                )

        asyncio.run(run())


class RecordBatchAsPlannedTests(unittest.TestCase):
    """Bulk "record all as planned" marks every unrecorded run-sheet row as
    copied from the plan, leaves already-recorded and terminal rows alone, and
    is idempotent."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "record-as-planned.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(self.repository, "record-as-planned")
        )
        self.batch = asyncio.run(self.repository.create_fabrication_batch(
            experiment_id, actor_user_id=1,
        ))

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_marks_all_unrecorded_rows_as_copied_from_plan(self) -> None:
        counts = asyncio.run(self.repository.record_batch_as_planned(
            self.batch.id, actor_user_id=1,
        ))
        self.assertGreater(counts["preparations"], 0)
        self.assertGreater(counts["executions"], 0)

        preparations = asyncio.run(
            self.repository.list_solution_preparations(self.batch.id)
        )
        executions = asyncio.run(
            self.repository.list_process_executions(self.batch.id)
        )
        for preparation in preparations:
            self.assertEqual(preparation.actual_recording_mode, "copied_from_plan")
            self.assertEqual(
                preparation.actual_solution_snapshot,
                preparation.planned_solution_snapshot,
            )
            self.assertEqual(preparation.prepared_by_id, 1)
        for execution in executions:
            if execution.status in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}:
                continue
            self.assertEqual(execution.actual_recording_mode, "copied_from_plan")
            self.assertEqual(
                execution.actual_process_snapshot,
                execution.planned_process_snapshot,
            )
            self.assertEqual(execution.executed_by_id, 1)

    def test_repeat_call_is_idempotent(self) -> None:
        asyncio.run(self.repository.record_batch_as_planned(
            self.batch.id, actor_user_id=1,
        ))
        counts = asyncio.run(self.repository.record_batch_as_planned(
            self.batch.id, actor_user_id=1,
        ))
        self.assertEqual(counts, {"preparations": 0, "executions": 0})

    def test_already_entered_actual_snapshot_is_untouched(self) -> None:
        preparations = asyncio.run(
            self.repository.list_solution_preparations(self.batch.id)
        )
        target = preparations[0]
        adjusted = json.loads(json.dumps(target.planned_solution_snapshot))
        adjusted["solids"][0]["weight_mg"] = (
            (adjusted["solids"][0].get("weight_mg") or 0) + 5
        )
        asyncio.run(self.repository.update_solution_preparation(
            target.id,
            actual_solution_snapshot=adjusted,
            actor_user_id=1,
        ))
        counts = asyncio.run(self.repository.record_batch_as_planned(
            self.batch.id, actor_user_id=1,
        ))
        self.assertEqual(counts["preparations"], len(preparations) - 1)
        refreshed = asyncio.run(
            self.repository.get_solution_preparation(target.id)
        )
        self.assertEqual(refreshed.actual_recording_mode, "entered")
        self.assertEqual(refreshed.actual_solution_snapshot, adjusted)


class RepositoryCompatDelegateExceptionTests(unittest.TestCase):
    """The deprecated repository delegates preserve the original exception
    contract (KeyError / ValueError / PermissionError) so historical direct
    callers keep working: typed-error translation happens only at the
    application-operations boundary used by the HTTP routes."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "compat-delegates.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login()
        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        self._experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "compat-delegates"
            )
        )

    def _login(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_batch_delegate_unknown_id_raises_key_error(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown fabrication batch id"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    999_999, BatchStatus.READY, actor_user_id=1,
                )
            )

    def test_batch_delegate_invalid_transition_raises_value_error(self) -> None:
        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self._experiment_id, actor_user_id=1,
            )
        )
        with self.assertRaisesRegex(ValueError, "cannot change from draft to"):
            asyncio.run(
                self.repository.update_fabrication_batch_status(
                    batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1,
                )
            )
        # No partial write: the batch is still a draft.
        refreshed = asyncio.run(self.repository.get_fabrication_batch(batch.id))
        self.assertEqual(refreshed.status, BatchStatus.DRAFT)

    def test_result_delegate_unknown_id_raises_key_error(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown result file id"):
            asyncio.run(
                self.repository.update_result_analysis_and_complete(
                    999_999,
                    {"schema_version": 3, "devices": [], "substrates": []},
                    substrate_assignments={},
                    group_assignment="",
                    actor_user_id=1,
                )
            )


if __name__ == "__main__":
    unittest.main()
