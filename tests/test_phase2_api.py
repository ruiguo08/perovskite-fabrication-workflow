"""Role-scoped JSON contracts required by the Phase 2 React application."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from perovskite_bo import (
    VCD_VALVES,
    deposition_recipe_from_process,
    validate_deposition_process,
)
from tests.recipe_fixtures import FACTORY_LAYER_PRESETS as LAYER_PRESETS
from web import create_app
from web.repository import UserRole

from tests.layout_fixtures import seed_standard_layouts
from tests.test_web_app import complete_guided_setup


ADMIN_USERNAME = "phase2-admin"
ADMIN_PASSWORD = "Phase 2 administrator password 2026"
OWNER_USERNAME = "phase2-owner"
OWNER_PASSWORD = "Phase 2 owner password 2026"
OTHER_USERNAME = "phase2-other"
OTHER_PASSWORD = "Phase 2 other password 2026"


class Phase2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "phase2.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                UserRole.ADMINISTRATOR,
            ),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        self.create_user(OWNER_USERNAME, OWNER_PASSWORD, UserRole.STUDENT)
        self.create_user(OTHER_USERNAME, OTHER_PASSWORD, UserRole.STUDENT)
        seed_standard_layouts(self.client)

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def login(self, username: str, password: str) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200, csrf.text)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def logout(self) -> None:
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204, response.text)
        self.client.headers.pop("X-CSRF-Token", None)

    def create_user(
        self,
        username: str,
        password: str,
        role: UserRole,
    ) -> None:
        response = self.client.post(
            "/api/users",
            json={
                "username": username,
                "display_name": username.replace("-", " ").title(),
                "password": password,
                "role": role.value,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def create_student_experiment(self) -> tuple[int, int]:
        device_recipe, deposition_process = complete_guided_setup()
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "Phase 2 student baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(baseline.status_code, 201, baseline.text)
        baseline_version_id = int(baseline.json()["current_version_id"])
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
                "source_baseline_version_id": baseline_version_id,
            },
        )
        self.assertEqual(experiment.status_code, 201, experiment.text)
        return int(experiment.json()["id"]), baseline_version_id

    def test_experiment_detail_composes_planning_records(self) -> None:
        experiment_id, _ = self.create_student_experiment()
        conditions = self.client.get(
            f"/api/experiments/{experiment_id}/conditions"
        ).json()
        condition = conditions[0]
        reduced = self.client.put(
            f"/api/conditions/{condition['id']}",
            json={
                "condition_name": condition["condition_name"],
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": condition[
                    "source_baseline_version_id"
                ],
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": 2,
            },
        )
        self.assertEqual(reduced.status_code, 200, reduced.text)
        exception = self.client.post(
            f"/api/conditions/{condition['id']}/substrate-exceptions",
            json={
                "requested_count": 2,
                "reason": "Limited conductive-glass inventory",
            },
        )
        self.assertEqual(exception.status_code, 201, exception.text)

        response = self.client.get(f"/api/experiments/{experiment_id}")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["experiment"]["id"], experiment_id)
        self.assertEqual(
            [row["id"] for row in body["conditions"]],
            [row["id"] for row in conditions],
        )
        self.assertEqual(
            body["substrate_exceptions"][0]["reason"],
            "Limited conductive-glass inventory",
        )
        self.assertEqual(body["fabrication_batches"], [])
        self.assertEqual(body["results"], [])

    def test_react_builder_payload_preserves_complete_target_and_fourth_spin_stage(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        deposition_process["spin_steps"] = [
            {"rpm": 1000, "seconds": 10, "acceleration_rpm_per_s": 500},
            {"rpm": 2000, "seconds": 10, "acceleration_rpm_per_s": 1000},
            {"rpm": 4000, "seconds": 20, "acceleration_rpm_per_s": 2000},
            {"rpm": 6000, "seconds": 30, "acceleration_rpm_per_s": 3000},
        ]
        target = next(
            group
            for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target.update(
            {
                "inherits_control": False,
                "adjustments": [],
                "layers": deepcopy(device_recipe["layers"]),
                "deposition_process": deepcopy(deposition_process),
            }
        )
        self.client.post(
            "/api/campaigns",
            json={
                "code": "react-builder",
                "display_name": "React builder contract",
                "description": "End-to-end complete snapshot test",
            },
        )
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "React builder source",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(baseline.status_code, 201, baseline.text)

        created = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "react-builder",
                "source_baseline_version_id": baseline.json()["current_version_id"],
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
                "condition_plans": [
                    {
                        "group_id": "control",
                        "role": "control",
                        "device_layout_code": "15x15_dual_005",
                        "planned_substrate_count": 3,
                    },
                    {
                        "group_id": "target-1",
                        "role": "target",
                        "device_layout_code": "15x15_dual_005",
                        "planned_substrate_count": 3,
                    },
                ],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        detail = self.client.get(f"/api/experiments/{created.json()['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)

        target_condition = next(
            condition
            for condition in detail.json()["conditions"]
            if condition["role"] == "target"
        )
        self.assertEqual(
            target_condition["recipe_snapshot"]["device"]["layers"],
            target["layers"],
        )
        self.assertEqual(
            target_condition["recipe_snapshot"]["deposition_process"]["spin_steps"][3],
            deposition_process["spin_steps"][3],
        )
        self.assertEqual(
            detail.json()["experiment"]["recipe"]["spin_stage4_rpm"],
            6000,
        )

    def test_student_cannot_read_another_students_experiment_detail(self) -> None:
        experiment_id, _ = self.create_student_experiment()
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)

        detail = self.client.get(f"/api/experiments/{experiment_id}")
        exceptions = self.client.get(
            f"/api/experiments/{experiment_id}/substrate-exceptions"
        )

        self.assertEqual(detail.status_code, 404, detail.text)
        self.assertEqual(exceptions.status_code, 404, exceptions.text)
        self.assertIn("unknown experiment id", detail.json()["detail"])
        self.assertIn("unknown experiment id", exceptions.json()["detail"])

    def test_layer_preset_versions_are_immutable_and_owner_scoped(self) -> None:
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        layer = deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"])
        created = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Owner SAM preset",
                "layer": layer,
                "deposition_process": None,
                "scope": "personal",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        preset_id = int(created.json()["id"])
        layer["name"] = "Revised owner SAM"
        revised = self.client.put(
            f"/api/layer-presets/{preset_id}",
            json={
                "name": "Owner SAM preset",
                "layer": layer,
                "deposition_process": None,
                "scope": "personal",
            },
        )
        self.assertEqual(revised.status_code, 200, revised.text)

        versions = self.client.get(
            f"/api/layer-presets/{preset_id}/versions"
        )
        self.assertEqual(versions.status_code, 200, versions.text)
        self.assertEqual(
            [row["revision_number"] for row in versions.json()],
            [1, 2],
        )
        self.assertEqual(
            versions.json()[0]["layer"]["name"],
            "SAM",
        )
        self.assertEqual(
            versions.json()[1]["layer"]["name"],
            "Revised owner SAM",
        )

        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        hidden = self.client.get(f"/api/layer-presets/{preset_id}/versions")
        self.assertEqual(hidden.status_code, 404, hidden.text)
        self.assertIn("unknown layer preset", hidden.json()["detail"])

    def test_instructor_promotes_student_layer_preset_to_shared(self) -> None:
        instructor_password = "promotion instructor password 2026"
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        self.create_user("promote-instructor", instructor_password, UserRole.INSTRUCTOR)
        self.logout()

        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        created = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Student SAM preset",
                "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
                "deposition_process": None,
                "scope": "personal",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        preset_id = int(created.json()["id"])

        # Students cannot promote, and cannot list promotion candidates.
        denied = self.client.post(f"/api/layer-presets/{preset_id}/promote")
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(
            self.client.get("/api/layer-presets?promotable=true").status_code, 403
        )

        # An instructor sees the preset as promotable and promotes it.
        self.login("promote-instructor", instructor_password)
        promotable = self.client.get("/api/layer-presets?promotable=true")
        self.assertEqual(promotable.status_code, 200, promotable.text)
        self.assertIn(preset_id, [row["id"] for row in promotable.json()])
        promoted = self.client.post(f"/api/layer-presets/{preset_id}/promote")
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertEqual(promoted.json()["scope"], "shared")

        # Promotion detaches the owner (one-way, lab-wide) and writes the
        # audited provenance the repository promises.
        from web.repository import WebRepository

        repository = WebRepository(self.app.state.database)

        async def _verify_promotion() -> None:
            from sqlalchemy import select

            from web import database as db

            async with self.app.state.database.engine.connect() as connection:
                owner_scope = await connection.execute(
                    select(
                        db.layer_presets.c.owner_user_id,
                        db.layer_presets.c.scope,
                    ).where(db.layer_presets.c.id == preset_id)
                )
                row = owner_scope.one()
                self.assertIsNone(row.owner_user_id)
                self.assertEqual(row.scope, "shared")
            events = await repository.list_audit_events(
                action_prefix="layer_preset.promote", limit=10
            )
            matching = [e for e in events if e.entity_id == str(preset_id)]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].actor_username, "promote-instructor")

        asyncio.run(_verify_promotion())

        # Another student can now select it, and re-promotion conflicts.
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        visible = self.client.get("/api/layer-presets").json()
        self.assertIn(preset_id, [row["id"] for row in visible])
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        again = self.client.post(f"/api/layer-presets/{preset_id}/promote")
        self.assertEqual(again.status_code, 409, again.text)

    def test_promoting_layer_preset_with_shared_name_conflict_is_rejected(self) -> None:
        instructor_password = "collision instructor password 2026"
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        self.create_user("collision-instructor", instructor_password, UserRole.INSTRUCTOR)
        shared = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Colliding SAM",
                "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
                "deposition_process": None,
                "scope": "shared",
            },
        )
        self.assertEqual(shared.status_code, 201, shared.text)
        self.logout()

        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        personal = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Colliding SAM",
                "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
                "deposition_process": None,
                "scope": "personal",
            },
        )
        self.assertEqual(personal.status_code, 201, personal.text)
        self.logout()

        self.login("collision-instructor", instructor_password)
        promoted = self.client.post(
            f"/api/layer-presets/{int(personal.json()['id'])}/promote"
        )
        self.assertEqual(promoted.status_code, 409, promoted.text)
        self.assertIn("already exists", promoted.json()["detail"])

    def test_editor_config_serves_authoritative_valves(self) -> None:
        response = self.client.get("/api/editor-config")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["vcd_valves"], list(VCD_VALVES))

    def test_seeded_shared_perovskite_preset_is_complete(self) -> None:
        # The v1 seed shipped blank VCD valve names, which made every baseline
        # that copied the preset unsavable; the seed must stay complete.
        for preset in self.client.get("/api/layer-presets").json():
            process = preset["deposition_process"]
            if process is None:
                continue
            try:
                validate_deposition_process(process)
            except (TypeError, ValueError) as error:  # pragma: no cover - failure path
                self.fail(f"seeded preset {preset['name']} has an incomplete process: {error}")

    def test_perovskite_preset_rejects_incomplete_deposition_process(self) -> None:
        layer = deepcopy(LAYER_PRESETS["perovskite_spin_v1"]["layer"])
        process = deepcopy(LAYER_PRESETS["perovskite_spin_v1"]["deposition_process"])
        process["vcd_stages"][0]["valve"] = ""
        created = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Incomplete perovskite preset",
                "layer": layer,
                "deposition_process": process,
                "scope": "personal",
            },
        )
        self.assertEqual(created.status_code, 400, created.text)
        self.assertIn("VCD stage 1 valve", created.json()["detail"])

    def test_student_cannot_read_history_of_inactive_shared_preset(self) -> None:
        # No factory catalog exists, so the test creates its own shared preset.
        created = self.client.post(
            "/api/layer-presets",
            json={
                "name": "Inactive-history shared SAM",
                "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
                "deposition_process": None,
                "scope": "shared",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        shared = created.json()
        deactivated = self.client.delete(
            f"/api/layer-presets/{shared['id']}"
        )
        self.assertEqual(deactivated.status_code, 204, deactivated.text)
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)

        response = self.client.get(
            f"/api/layer-presets/{shared['id']}/versions"
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.assertIn("unknown layer preset", response.json()["detail"])

    def test_baseline_detail_requires_login_and_hides_archived_records_from_students(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        created = self.client.post(
            "/api/baselines",
            json={
                "name": "Phase 2 archived baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        baseline_id = int(created.json()["id"])
        archived = self.client.delete(f"/api/baselines/{baseline_id}")
        self.assertEqual(archived.status_code, 204, archived.text)

        self.logout()
        anonymous = self.client.get(f"/api/baselines/{baseline_id}")
        anonymous_history = self.client.get(
            f"/api/baselines/{baseline_id}/versions"
        )
        self.assertEqual(anonymous.status_code, 401, anonymous.text)
        self.assertEqual(anonymous_history.status_code, 401, anonymous_history.text)

        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        detail = self.client.get(f"/api/baselines/{baseline_id}")
        history = self.client.get(f"/api/baselines/{baseline_id}/versions")
        self.assertEqual(detail.status_code, 404, detail.text)
        self.assertEqual(history.status_code, 404, history.text)

        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        staff_history = self.client.get(
            f"/api/baselines/{baseline_id}/versions"
        )
        self.assertEqual(staff_history.status_code, 200, staff_history.text)
        self.assertIsInstance(staff_history.json()[0]["created_by_id"], int)

    def test_user_json_api_is_administrator_only_and_never_returns_hashes(self) -> None:
        listed = self.client.get("/api/users")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertTrue(listed.json())
        self.assertNotIn("password_hash", listed.json()[0])
        self.assertNotIn("failed_login_count", listed.json()[0])

        created = self.client.post(
            "/api/users",
            json={
                "username": "phase2-instructor",
                "display_name": "Phase 2 Instructor",
                "password": "Phase 2 instructor password 2026",
                "role": "instructor",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        account_id = int(created.json()["id"])
        updated = self.client.patch(
            f"/api/users/{account_id}",
            json={"role": "student", "is_active": True},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["role"], "student")
        reset = self.client.post(
            f"/api/users/{account_id}/password",
            json={"password": "Replacement account password 2026"},
        )
        self.assertEqual(reset.status_code, 204, reset.text)

        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        self.assertEqual(self.client.get("/api/users").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/users",
                json={
                    "username": "forbidden-user",
                    "display_name": "Forbidden User",
                    "password": "Forbidden user password 2026",
                    "role": "student",
                },
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
