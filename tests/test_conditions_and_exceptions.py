"""Tests for experiment conditions and substrate exception approval."""

from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from web import create_app
from web.condition_snapshot import (
    build_condition_snapshot,
    canonical_hash,
    validate_condition_snapshot,
)
from web.repository import (
    ConditionRole,
    ExceptionDecision,
    PlanStatus,
    UserRole,
)
from layout_fixtures import fixture_layouts
from test_web_app import complete_guided_setup

TEST_USERNAME = "admin"
TEST_PASSWORD = "Adm1n!password"


def _condition_snapshot() -> dict:
    device_recipe, deposition_process = complete_guided_setup()
    return build_condition_snapshot(
        device_recipe,
        deposition_process=deposition_process,
    )


class ConditionRepositoryTests(unittest.TestCase):
    """Test experiment condition creation, listing, and snapshots."""

    def test_schema_version_1_condition_snapshot_is_migrated(self) -> None:
        snapshot = _condition_snapshot()
        snapshot["schema_version"] = 1
        snapshot["device"]["schema_version"] = 1
        snapshot["device"]["setup_mode"] = "reference"

        normalized = validate_condition_snapshot(snapshot)

        self.assertEqual(normalized["schema_version"], 3)
        self.assertEqual(normalized["device"]["schema_version"], 2)
        self.assertEqual(normalized["device"]["setup_mode"], "baseline")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "conditions.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        login_csrf = self.client.get("/api/auth/login-csrf").json()["login_csrf_token"]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": login_csrf,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )
        from tests.layout_fixtures import seed_standard_layouts

        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        self._experiment_id = asyncio.run(self._create_experiment())

    async def _create_experiment(self) -> int:
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        device_recipe, deposition_process = complete_guided_setup()
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        })
        await self.repository.create_campaign(
            code="test-campaign",
            display_name="Condition tests",
            description="",
            actor_user_id=1,
        )
        record = await self.repository.add_experiment(
            recipe, campaign_id="test-campaign", actor_user_id=1
        )
        return record.id

    async def _create_fresh_experiment(self) -> int:
        """A second experiment in its own series (plan states have no
        backwards transition, so each interleaving needs a fresh draft)."""

        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process

        device_recipe, deposition_process = complete_guided_setup()
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        })
        record = await self.repository.add_experiment(
            recipe, campaign_id="test-campaign", actor_user_id=1
        )
        # Same manual-review clearing as the PostgreSQL race test: give the
        # target group its own full layers via a direct flag clear so the
        # plan can be submitted.
        from web.repository import experiment_conditions

        conditions = await self.repository.list_conditions_for_experiment(
            record.id
        )
        for condition in conditions:
            if condition.requires_manual_review:
                async with self.repository.database.begin() as connection:
                    await connection.execute(
                        experiment_conditions.update()
                        .where(experiment_conditions.c.id == condition.id)
                        .values(requires_manual_review=False)
                    )
        return record.id

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_condition_write_keeps_pending_approval_status(self) -> None:
        """Only a condition CREATE preserves an advanced plan status: the
        approval gate re-validates every condition, so a plan can stay
        pending-approval while a new target is added mid-review. An update or
        delete changes the approved content itself, so the plan must return
        to draft (concurrent-release contract: exactly one of
        edit/release commits)."""

        import asyncio
        import json as json_module
        from copy import deepcopy

        snapshot = _condition_snapshot()
        repo = self.repository

        async def raw_plan_status(experiment_id: int) -> str:
            from sqlalchemy import select

            from web.repository import experiments as experiments_table

            async with repo.database.engine.connect() as connection:
                row = (
                    await connection.execute(
                        select(experiments_table.c.plan_status).where(
                            experiments_table.c.id == experiment_id
                        )
                    )
                ).one()
            return str(row[0])

        async def scenario(write: str) -> str:
            experiment_id = await self._create_fresh_experiment()
            await repo.update_plan_status(
                experiment_id, PlanStatus.PENDING_APPROVAL, actor_user_id=1
            )
            conditions = await repo.list_conditions_for_experiment(
                experiment_id
            )
            if write == "create":
                await repo.create_condition(
                    experiment_id=experiment_id,
                    role=ConditionRole.TARGET,
                    condition_code=None,
                    condition_name="Raced target",
                    recipe_snapshot=json_module.loads(
                        json_module.dumps(snapshot)
                    ),
                    source_baseline_version_id=None,
                    device_layout_code="25x25_six_010",
                    planned_substrate_count=3,
                    actor_user_id=1,
                )
            elif write == "update":
                condition = conditions[0]
                await repo.update_condition(
                    condition.id,
                    condition_name=condition.condition_name,
                    recipe_snapshot=deepcopy(dict(condition.recipe_snapshot)),
                    source_baseline_version_id=(
                        condition.source_baseline_version_id
                    ),
                    device_layout_code=condition.device_layout_code,
                    planned_substrate_count=condition.planned_substrate_count,
                    actor_user_id=1,
                )
            else:
                await repo.delete_condition(conditions[0].id, actor_user_id=1)
            return await raw_plan_status(experiment_id)

        expected = {
            "create": PlanStatus.PENDING_APPROVAL.value,
            "update": PlanStatus.DRAFT.value,
            "delete": PlanStatus.DRAFT.value,
        }
        for write, wanted in expected.items():
            with self.subTest(write=write):
                self.assertEqual(asyncio.run(scenario(write)), wanted)

    def test_condition_create_resets_approved_plan_to_draft(self) -> None:
        """A new condition on an APPROVED plan must return it to draft: the
        condition has not been reviewed by an instructor, so keeping
        approved would let it ride straight into a release and bypass the
        review gate. The plan must then pass the full
        pending-approval -> approved -> released chain again."""

        import asyncio
        import json as json_module

        snapshot = _condition_snapshot()
        repo = self.repository

        async def scenario() -> None:
            experiment_id = await self._create_fresh_experiment()
            for status in (PlanStatus.PENDING_APPROVAL, PlanStatus.APPROVED):
                await repo.update_plan_status(
                    experiment_id, status, actor_user_id=1
                )
            await repo.create_condition(
                experiment_id=experiment_id,
                role=ConditionRole.TARGET,
                condition_code=None,
                condition_name="Unreviewed target",
                recipe_snapshot=json_module.loads(
                    json_module.dumps(snapshot)
                ),
                source_baseline_version_id=None,
                device_layout_code="25x25_six_010",
                planned_substrate_count=3,
                actor_user_id=1,
            )
            record = await repo.get_experiment(experiment_id)
            self.assertEqual(
                str(record.plan_status), PlanStatus.DRAFT.value
            )
            # A direct draft -> released jump must be rejected.
            with self.assertRaises(ValueError):
                await repo.update_plan_status(
                    experiment_id, PlanStatus.RELEASED, actor_user_id=1
                )
            # The full re-approval chain works and includes the new
            # condition in the release validation.
            for status in (
                PlanStatus.PENDING_APPROVAL,
                PlanStatus.APPROVED,
                PlanStatus.RELEASED,
            ):
                await repo.update_plan_status(
                    experiment_id, status, actor_user_id=1
                )
            record = await repo.get_experiment(experiment_id)
            self.assertEqual(
                str(record.plan_status), PlanStatus.RELEASED.value
            )
            conditions = await repo.list_conditions_for_experiment(
                experiment_id
            )
            self.assertTrue(
                any(c.condition_name == "Unreviewed target" for c in conditions)
            )

        asyncio.run(scenario())

    def test_create_additional_target_condition(self) -> None:
        import asyncio
        snapshot = _condition_snapshot()
        layout_code = "25x25_six_010"
        record = asyncio.run(self.repository.create_condition(
            experiment_id=self._experiment_id,
            role=ConditionRole.TARGET,
            condition_code="test-campaign-v1-T2",
            condition_name="Target 2",
            recipe_snapshot=snapshot,
            source_baseline_version_id=None,
            device_layout_code=layout_code,
            planned_substrate_count=3,
            actor_user_id=1,
        ))
        self.assertEqual(record.role, ConditionRole.TARGET)
        self.assertEqual(record.condition_code, "test-campaign-v1-T2")
        self.assertEqual(record.planned_substrate_count, 3)
        self.assertEqual(record.expected_device_count, 18)
        self.assertFalse(record.requires_manual_review)
        self.assertEqual(record.device_layout_code, layout_code)
        self.assertEqual(record.device_layout_snapshot["version"], 1)
        self.assertEqual(record.recipe_schema_version, 3)
        self.assertEqual(record.canonical_hash, canonical_hash(snapshot))

    def test_invalid_snapshot_and_layout_are_rejected(self) -> None:
        import asyncio

        with self.assertRaises((TypeError, ValueError)):
            asyncio.run(self.repository.create_condition(
                experiment_id=self._experiment_id,
                role=ConditionRole.CONTROL,
                condition_code=None,
                condition_name="Invalid",
                recipe_snapshot={},
                source_baseline_version_id=None,
                device_layout_code="15x15_dual_005",
                planned_substrate_count=3,
                actor_user_id=1,
            ))
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.create_condition(
                experiment_id=self._experiment_id,
                role=ConditionRole.CONTROL,
                condition_code=None,
                condition_name="Invalid layout",
                recipe_snapshot=_condition_snapshot(),
                source_baseline_version_id=None,
                device_layout_code="not-in-catalog",
                planned_substrate_count=3,
                actor_user_id=1,
            ))

    def test_list_conditions_for_experiment(self) -> None:
        import asyncio
        snapshot = _condition_snapshot()
        asyncio.run(self.repository.create_condition(
            experiment_id=self._experiment_id,
            role=ConditionRole.TARGET,
            condition_code="test-campaign-v1-T2",
            condition_name="plan-T2",
            recipe_snapshot=snapshot,
            source_baseline_version_id=None,
            device_layout_code="15x15_dual_005",
            planned_substrate_count=3,
            actor_user_id=1,
        ))
        conditions = asyncio.run(self.repository.list_conditions_for_experiment(
            self._experiment_id
        ))
        self.assertEqual(len(conditions), 3)
        roles = [c.role for c in conditions]
        self.assertIn(ConditionRole.CONTROL, roles)
        self.assertEqual(roles.count(ConditionRole.TARGET), 2)


class SubstrateExceptionTests(unittest.TestCase):
    """Test the <3 substrate approval workflow."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "exceptions.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        login_csrf = self.client.get("/api/auth/login-csrf").json()["login_csrf_token"]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": login_csrf,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )
        from tests.layout_fixtures import seed_standard_layouts

        seed_standard_layouts(self.client)
        self.repository = self.app.state.repository
        import asyncio
        recipe, condition_plans = asyncio.run(self._make_recipe())
        asyncio.run(self.repository.create_campaign(
            code="exc-campaign",
            display_name="Exception tests",
            description="",
            actor_user_id=1,
        ))
        exp = asyncio.run(self.repository.add_experiment(
            recipe,
            campaign_id="exc-campaign",
            condition_plans=condition_plans,
            actor_user_id=1,
        ))
        conditions = asyncio.run(
            self.repository.list_conditions_for_experiment(exp.id)
        )
        cond = next(item for item in conditions if item.role == ConditionRole.TARGET)
        self._condition_id = cond.id

    async def _make_recipe(self):
        from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
        device_recipe, deposition_process = complete_guided_setup()
        for group in device_recipe["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = deepcopy(device_recipe["layers"])
                group["deposition_process"] = deepcopy(deposition_process)
        recipe = DepositionRecipe.from_mapping({
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        })
        condition_plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": "15x15_dual_005",
                "planned_substrate_count": 2 if group["kind"] == "target" else 3,
            }
            for group in device_recipe["experimental_groups"]
        ]
        return recipe, condition_plans

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_request_exception_pending(self) -> None:
        import asyncio
        record = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="Limited material availability",
            requested_by_id=1,
        ))
        self.assertEqual(record.decision, ExceptionDecision.PENDING)
        self.assertEqual(record.requested_count, 2)

    def test_approve_exception(self) -> None:
        import asyncio
        exc = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="Very limited material",
            requested_by_id=1,
        ))
        approved = asyncio.run(self.repository.decide_substrate_exception(
            exc.id,
            decision=ExceptionDecision.APPROVED,
            decided_by_id=1,
            decision_note="Approved with caution",
        ))
        self.assertEqual(approved.decision, ExceptionDecision.APPROVED)
        self.assertEqual(approved.decision_note, "Approved with caution")
        condition = asyncio.run(self.repository.get_condition(self._condition_id))
        self.assertEqual(approved.approved_condition_hash, condition.canonical_hash)

    def test_reject_exception(self) -> None:
        import asyncio
        exc = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="Not enough",
            requested_by_id=1,
        ))
        rejected = asyncio.run(self.repository.decide_substrate_exception(
            exc.id,
            decision=ExceptionDecision.REJECTED,
            decided_by_id=1,
            decision_note="Need at least 3",
        ))
        self.assertEqual(rejected.decision, ExceptionDecision.REJECTED)

    def test_cannot_decide_non_pending(self) -> None:
        import asyncio
        exc = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="test",
            requested_by_id=1,
        ))
        asyncio.run(self.repository.decide_substrate_exception(
            exc.id,
            decision=ExceptionDecision.APPROVED,
            decided_by_id=1,
        ))
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.decide_substrate_exception(
                exc.id,
                decision=ExceptionDecision.REJECTED,
                decided_by_id=1,
            ))

    def test_invalidate_after_condition_change(self) -> None:
        import asyncio
        exc = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="test",
            requested_by_id=1,
        ))
        asyncio.run(self.repository.decide_substrate_exception(
            exc.id,
            decision=ExceptionDecision.APPROVED,
            decided_by_id=1,
        ))
        # Simulate condition change → invalidate
        count = asyncio.run(self.repository.invalidate_exceptions_for_condition(
            self._condition_id, actor_user_id=1
        ))
        self.assertEqual(count, 1)
        # Verify the exception is now invalidated
        record = asyncio.run(self.repository.get_substrate_exception(exc.id))
        self.assertEqual(record.decision, ExceptionDecision.INVALIDATED)

    def test_blank_reason_rejected(self) -> None:
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(self.repository.request_substrate_exception(
                condition_id=self._condition_id,
                requested_count=2,
                reason="   ",
                requested_by_id=1,
            ))

    def test_duplicate_active_exception_rejected(self) -> None:
        import asyncio

        asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="First request",
            requested_by_id=1,
        ))
        with self.assertRaisesRegex(ValueError, "already has an active"):
            asyncio.run(self.repository.request_substrate_exception(
                condition_id=self._condition_id,
                requested_count=2,
                reason="Duplicate request",
                requested_by_id=1,
            ))

    def test_condition_update_automatically_invalidates_approval(self) -> None:
        import asyncio

        exception = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="Limited material",
            requested_by_id=1,
        ))
        asyncio.run(self.repository.decide_substrate_exception(
            exception.id,
            decision=ExceptionDecision.APPROVED,
            decided_by_id=1,
        ))
        updated = asyncio.run(self.repository.update_condition(
            self._condition_id,
            condition_name="Updated target",
            recipe_snapshot=_condition_snapshot(),
            source_baseline_version_id=None,
            device_layout_code="15x15_dual_005",
            planned_substrate_count=2,
            actor_user_id=1,
        ))
        self.assertEqual(updated.recipe_schema_version, 3)
        invalidated = asyncio.run(
            self.repository.get_substrate_exception(exception.id)
        )
        self.assertEqual(invalidated.decision, ExceptionDecision.INVALIDATED)
        self.assertIsNone(invalidated.approved_condition_hash)

    def test_release_requires_control_and_current_approval(self) -> None:
        import asyncio
        exception = asyncio.run(self.repository.request_substrate_exception(
            condition_id=self._condition_id,
            requested_count=2,
            reason="Limited material",
            requested_by_id=1,
        ))
        # Submission succeeds: a pending substrate exception exists.
        asyncio.run(self.repository.update_plan_status(
            1,
            PlanStatus.PENDING_APPROVAL,
            actor_user_id=1,
        ))
        # Approval is blocked until the exception is decided.
        with self.assertRaisesRegex(ValueError, "not approved"):
            asyncio.run(self.repository.update_plan_status(
                1,
                PlanStatus.APPROVED,
                actor_user_id=1,
            ))
        asyncio.run(self.repository.decide_substrate_exception(
            exception.id,
            decision=ExceptionDecision.APPROVED,
            decided_by_id=1,
        ))
        asyncio.run(self.repository.update_plan_status(
            1,
            PlanStatus.APPROVED,
            actor_user_id=1,
        ))
        asyncio.run(self.repository.update_plan_status(
            1,
            PlanStatus.RELEASED,
            actor_user_id=1,
        ))
        released = asyncio.run(self.repository.get_experiment(1))
        self.assertEqual(released.plan_status, PlanStatus.RELEASED.value)
        with self.assertRaisesRegex(ValueError, "cannot be modified"):
            asyncio.run(self.repository.update_condition(
                self._condition_id,
                condition_name="Too late",
                recipe_snapshot=_condition_snapshot(),
                source_baseline_version_id=None,
                device_layout_code="15x15_dual_005",
                planned_substrate_count=2,
                actor_user_id=1,
            ))


class LegacyAdapterTests(unittest.TestCase):
    """Test the legacy recipe → Plan+Conditions converter."""

    def setUp(self) -> None:
        from test_web_app import complete_guided_setup
        from perovskite_bo import DepositionRecipe
        self.device_recipe, self.deposition_process = complete_guided_setup()
        # Build a legacy recipe dict (the old flat format).
        self.legacy_recipe = {
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
            "vcd_stage1_pressure_pa": 5000,
            "vcd_stage1_seconds": 10,
            "anneal_stage1_temperature_c": 120,
            "anneal_stage1_seconds": 600,
            "device_recipe": self.device_recipe,
        }

    def test_control_materialized(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        conditions = materialize_legacy_conditions(self.legacy_recipe, "CMP-v1", layouts=fixture_layouts())
        self.assertGreaterEqual(len(conditions), 2)
        control = conditions[0]
        self.assertEqual(control["role"], "control")
        self.assertEqual(control["condition_code"], "CMP-v1-C")
        self.assertFalse(control["requires_manual_review"])
        self.assertEqual(control["planned_substrate_count"], 3)

    def test_target_with_layers_materialized(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        # Give the target a full layers stack.
        for group in self.device_recipe["experimental_groups"]:
            if group["kind"] == "target":
                group["layers"] = self.device_recipe["layers"]
        conditions = materialize_legacy_conditions(self.legacy_recipe, "CMP-v2", layouts=fixture_layouts())
        target = next(c for c in conditions if c["role"] == "target")
        self.assertEqual(target["condition_code"], "CMP-v2-T1")
        self.assertFalse(target["requires_manual_review"])
        self.assertNotIn(
            "experimental_groups", target["recipe_snapshot"]["device"]
        )
        self.assertTrue(target["recipe_snapshot"]["deposition_process"]["spin_steps"])

    def test_target_with_only_adjustments_flagged(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        conditions = materialize_legacy_conditions(self.legacy_recipe, "CMP-v3", layouts=fixture_layouts())
        target = next(c for c in conditions if c["role"] == "target")
        self.assertTrue(target["requires_manual_review"])

    def test_layout_inferred_from_substrate(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        self.device_recipe["substrate"]["width_mm"] = 25
        self.device_recipe["substrate"]["length_mm"] = 25
        conditions = materialize_legacy_conditions(self.legacy_recipe, "CMP-v4", layouts=fixture_layouts())
        # 25x25 should match 25x25_six_010 or 25x25_single_1cm2
        control = conditions[0]
        self.assertIn(control["device_layout_code"], {
            "25x25_six_010", "25x25_single_1cm2",
        })
        self.assertTrue(control["requires_manual_review"])

    def test_explicit_condition_plans_disambiguate_25x25_layouts(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions

        self.device_recipe["substrate"]["width_mm"] = 25
        self.device_recipe["substrate"]["length_mm"] = 25
        plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": (
                    "25x25_single_1cm2"
                    if group["kind"] == "control"
                    else "25x25_six_010"
                ),
                "planned_substrate_count": 4,
            }
            for group in self.device_recipe["experimental_groups"]
        ]

        conditions = materialize_legacy_conditions(self.legacy_recipe,
            "CMP-v4",
            condition_plans=plans, layouts=fixture_layouts())

        self.assertEqual(
            [row["device_layout_code"] for row in conditions],
            ["25x25_single_1cm2", "25x25_six_010"],
        )
        self.assertTrue(
            all(row["planned_substrate_count"] == 4 for row in conditions)
        )
        control = next(row for row in conditions if row["role"] == "control")
        target = next(row for row in conditions if row["role"] == "target")
        self.assertFalse(control["requires_manual_review"])
        self.assertTrue(target["requires_manual_review"])

    def test_explicit_layout_must_match_substrate_dimensions(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions

        plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": "20x20_single_1cm2",
                "planned_substrate_count": 3,
            }
            for group in self.device_recipe["experimental_groups"]
        ]

        with self.assertRaisesRegex(ValueError, "does not match"):
            materialize_legacy_conditions(self.legacy_recipe,
                "CMP-v4",
                condition_plans=plans, layouts=fixture_layouts())

    def test_legacy_substrate_count_is_preserved(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions

        self.device_recipe["experimental_groups"][0]["substrate_count"] = 5
        conditions = materialize_legacy_conditions(self.legacy_recipe, "CMP-v5", layouts=fixture_layouts())
        self.assertEqual(conditions[0]["planned_substrate_count"], 5)

    def test_condition_code_format(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        conditions = materialize_legacy_conditions(self.legacy_recipe, "SAM-v1", layouts=fixture_layouts())
        codes = [c["condition_code"] for c in conditions]
        self.assertIn("SAM-v1-C", codes)
        self.assertIn("SAM-v1-T1", codes)

    def test_canonical_hash_stable(self) -> None:
        from web.services.legacy_adapter import materialize_legacy_conditions
        c1 = materialize_legacy_conditions(self.legacy_recipe, "X-v1", layouts=fixture_layouts())
        c2 = materialize_legacy_conditions(self.legacy_recipe, "X-v1", layouts=fixture_layouts())
        self.assertEqual(
            canonical_hash(c1[0]["recipe_snapshot"]),
            canonical_hash(c2[0]["recipe_snapshot"]),
        )

    def test_vcd_program_order_changes_condition_hash(self) -> None:
        self.deposition_process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30,
                "target_pressure_pa": 15,
                "hold_seconds": 20,
            }
        ]
        self.deposition_process["vcd_step_sequence"] = [
            "vcd_stage1",
            "gas_backfill_stage1",
            "vcd_stage2",
            "vcd_stage3",
        ]
        first = build_condition_snapshot(
            self.device_recipe,
            deposition_process=self.deposition_process,
        )
        self.deposition_process["vcd_step_sequence"] = [
            "vcd_stage1",
            "vcd_stage2",
            "gas_backfill_stage1",
            "vcd_stage3",
        ]
        second = build_condition_snapshot(
            self.device_recipe,
            deposition_process=self.deposition_process,
        )

        self.assertNotEqual(canonical_hash(first), canonical_hash(second))


if __name__ == "__main__":
    unittest.main()
