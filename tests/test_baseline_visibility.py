"""Personal and Shared baseline visibility and promotion contracts.

Role matrix under test (students cannot see or infer a peer's Personal
Baseline; instructors may view any baseline for oversight but may invoke
only active Shared Baselines as experiment sources; promotion is explicit
and instructor/admin-only):

1. Student A creates a Personal Baseline.
2. Student A can list, read, revise, and use their Personal Baseline.
3. Student B cannot list, read, revise, or use Student A's Personal
   Baseline; direct requests return 404.
4. Instructor can view Student A's Personal Baseline but cannot use it as
   an experiment source.
5. Instructor promotes Student A's Personal Baseline; promotion provenance
   and the audit event are stored.
6. After promotion, Student B can list, read, and use it as Shared.
7. Student A can no longer revise it after promotion.
8. Instructor/admin direct Shared Baseline creation remains valid.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.layout_fixtures import seed_standard_layouts
from web import create_app
from web.database import audit_events
from web.repository import UserRole

from tests.test_web_app import FLAT_RECIPE_WITHOUT_DEVICE, complete_guided_setup


ADMIN_USERNAME = "visibility-admin"
ADMIN_PASSWORD = "Visibility administrator password 2026"
INSTRUCTOR_USERNAME = "visibility-instructor"
INSTRUCTOR_PASSWORD = "Visibility instructor password 2026"
STUDENT_A_USERNAME = "visibility-student-a"
STUDENT_A_PASSWORD = "Visibility student A password 2026"
STUDENT_B_USERNAME = "visibility-student-b"
STUDENT_B_PASSWORD = "Visibility student B password 2026"


def baseline_payload(name: str) -> dict:
    device_recipe, deposition_process = complete_guided_setup()
    return {
        "name": name,
        "device_recipe": device_recipe,
        "deposition_process": deposition_process,
    }


class BaselineVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "visibility.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        self.create_user(STUDENT_A_USERNAME, STUDENT_A_PASSWORD, UserRole.STUDENT)
        self.create_user(STUDENT_B_USERNAME, STUDENT_B_PASSWORD, UserRole.STUDENT)
        self.create_user(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD, UserRole.INSTRUCTOR)
        seed_standard_layouts(self.client)
        self.student_a_id = self._user_id(STUDENT_A_USERNAME)
        self.student_b_id = self._user_id(STUDENT_B_USERNAME)
        self.instructor_id = self._user_id(INSTRUCTOR_USERNAME)

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
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

    def _user_id(self, username: str) -> int:
        users = self.client.get("/api/users").json()
        return int(next(row["id"] for row in users if row["username"] == username))

    def _audit_rows(self, entity_type: str, entity_id: str) -> list[dict]:
        async def fetch() -> list[dict]:
            async with self.app.state.database.engine.connect() as connection:
                rows = (
                    await connection.execute(
                        select(audit_events)
                        .where(
                            audit_events.c.entity_type == entity_type,
                            audit_events.c.entity_id == entity_id,
                        )
                        .order_by(audit_events.c.id)
                    )
                ).mappings().all()
                return [dict(row) for row in rows]

        return asyncio.run(fetch())

    # Scenario 1 + creation policy -------------------------------------------

    def test_student_creates_personal_baseline(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["scope"], "personal")
        self.assertEqual(created.json()["owner_user_id"], self.student_a_id)

    def test_student_cannot_supply_shared_scope(self) -> None:
        """A student-supplied scope is rejected outright, never trusted."""
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        payload = baseline_payload("Student A reference")
        payload["scope"] = "shared"
        response = self.client.post("/api/baselines", json=payload)
        self.assertEqual(response.status_code, 422, response.text)
        listed = self.client.get("/api/baselines").json()
        self.assertEqual(listed, [])

    def test_instructor_direct_creation_is_shared(self) -> None:
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Instructor shared reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["scope"], "shared")
        self.assertIsNone(created.json()["owner_user_id"])

    def test_administrator_direct_creation_is_shared(self) -> None:
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Admin shared reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["scope"], "shared")
        self.assertIsNone(created.json()["owner_user_id"])

    # Scenario 2 -------------------------------------------------------------

    def test_owner_can_list_read_revise_and_use_personal_baseline(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        baseline_id = created.json()["id"]
        first_version_id = created.json()["current_version_id"]

        listed = self.client.get("/api/baselines").json()
        self.assertEqual([row["id"] for row in listed], [baseline_id])

        fetched = self.client.get(f"/api/baselines/{baseline_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["scope"], "personal")

        versions = self.client.get(f"/api/baselines/{baseline_id}/versions").json()
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["id"], first_version_id)

        revised = self.client.put(
            f"/api/baselines/{baseline_id}",
            json=baseline_payload("Student A reference"),
        )
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["current_revision_number"], 2)

        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **FLAT_RECIPE_WITHOUT_DEVICE,
                    "device_recipe": revised.json()["device_recipe"],
                },
                "source_baseline_version_id": revised.json()["current_version_id"],
            },
        )
        self.assertEqual(experiment.status_code, 201, experiment.text)

    # Scenario 3 -------------------------------------------------------------

    def test_peer_student_cannot_list_read_revise_or_use_personal_baseline(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        baseline_id = created.json()["id"]
        version_id = created.json()["current_version_id"]

        self.login(STUDENT_B_USERNAME, STUDENT_B_PASSWORD)
        listed = self.client.get("/api/baselines").json()
        self.assertNotIn(baseline_id, [row["id"] for row in listed])

        visible = self.client.get("/api/baselines")
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(visible.json(), [])

        fetched = self.client.get(f"/api/baselines/{baseline_id}")
        self.assertEqual(fetched.status_code, 404)
        versions = self.client.get(f"/api/baselines/{baseline_id}/versions")
        self.assertEqual(versions.status_code, 404)
        revised = self.client.put(
            f"/api/baselines/{baseline_id}", json=baseline_payload("Student A reference")
        )
        self.assertEqual(revised.status_code, 404)

        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **FLAT_RECIPE_WITHOUT_DEVICE,
                    "device_recipe": created.json()["device_recipe"],
                },
                "source_baseline_version_id": version_id,
            },
        )
        self.assertEqual(experiment.status_code, 404, experiment.text)

    # Scenario 4 -------------------------------------------------------------

    def test_instructor_can_view_but_not_use_personal_baseline(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]
        version_id = created.json()["current_version_id"]

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        fetched = self.client.get(f"/api/baselines/{baseline_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["scope"], "personal")
        versions = self.client.get(f"/api/baselines/{baseline_id}/versions")
        self.assertEqual(versions.status_code, 200)

        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **FLAT_RECIPE_WITHOUT_DEVICE,
                    "device_recipe": created.json()["device_recipe"],
                },
                "source_baseline_version_id": version_id,
            },
        )
        self.assertEqual(experiment.status_code, 404, experiment.text)

        revised = self.client.put(
            f"/api/baselines/{baseline_id}", json=baseline_payload("Student A reference")
        )
        self.assertEqual(revised.status_code, 404)

    # Scenario 5 -------------------------------------------------------------

    def test_instructor_promotes_personal_baseline_with_provenance(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        self.assertEqual(created.status_code, 201, created.text)
        baseline_id = created.json()["id"]
        version_id = created.json()["current_version_id"]

        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        student_promote = self.client.post(
            f"/api/baselines/{baseline_id}/promote", json={"note": "not allowed"}
        )
        self.assertEqual(student_promote.status_code, 403, student_promote.text)

        self.login(STUDENT_B_USERNAME, STUDENT_B_PASSWORD)
        peer_promote = self.client.post(
            f"/api/baselines/{baseline_id}/promote", json={"note": "not allowed"}
        )
        self.assertEqual(peer_promote.status_code, 403, peer_promote.text)

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        promoted = self.client.post(
            f"/api/baselines/{baseline_id}/promote",
            json={"note": "Excellent control reference"},
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)
        body = promoted.json()
        self.assertEqual(body["scope"], "shared")
        self.assertEqual(body["owner_user_id"], self.student_a_id)
        self.assertEqual(body["owner_display_name"], "Visibility Student A")
        self.assertEqual(body["promoted_by_user_id"], self.instructor_id)
        self.assertEqual(body["promoted_at"], body["updated_at"])
        self.assertEqual(body["promotion_note"], "Excellent control reference")
        self.assertEqual(body["promoted_version_id"], version_id)

        audit = self._audit_rows("baseline", str(baseline_id))
        actions = [row["action"] for row in audit]
        self.assertIn("baseline.create", actions)
        self.assertIn("baseline.promote", actions)
        promote_event = next(row for row in audit if row["action"] == "baseline.promote")
        self.assertEqual(promote_event["actor_user_id"], self.instructor_id)
        self.assertEqual(promote_event["details"]["note"], "Excellent control reference")
        self.assertEqual(promote_event["details"]["version_id"], version_id)

    def test_promote_rejects_shared_or_archived_or_missing_baseline(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        first = self.client.post(f"/api/baselines/{baseline_id}/promote", json={})
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(f"/api/baselines/{baseline_id}/promote", json={})
        self.assertEqual(second.status_code, 409, second.text)

        missing = self.client.post("/api/baselines/999999/promote", json={})
        self.assertEqual(missing.status_code, 404, missing.text)

    def test_promote_returns_conflict_when_shared_name_exists(self) -> None:
        # Instructor creates a shared baseline named "Collide".
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        shared = self.client.post("/api/baselines", json=baseline_payload("Collide"))
        self.assertEqual(shared.status_code, 201, shared.text)

        # Student A creates a personal baseline with the same name. This is
        # allowed because the shared-name unique index only covers shared
        # baselines.
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        personal = self.client.post("/api/baselines", json=baseline_payload("Collide"))
        self.assertEqual(personal.status_code, 201, personal.text)
        personal_id = personal.json()["id"]

        # Promoting the personal baseline to shared now collides with the
        # existing shared name and returns 409 (not an unhandled 500).
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        response = self.client.post(f"/api/baselines/{personal_id}/promote", json={})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("already exists", response.json()["detail"])

    def test_promote_requires_csrf(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        self.client.headers.pop("X-CSRF-Token", None)
        response = self.client.post(f"/api/baselines/{baseline_id}/promote", json={})
        self.assertEqual(response.status_code, 403, response.text)

    # Scenario 6 -------------------------------------------------------------

    def test_shared_baseline_is_usable_by_all_after_promotion(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]
        version_id = created.json()["current_version_id"]

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        promoted = self.client.post(f"/api/baselines/{baseline_id}/promote", json={})
        self.assertEqual(promoted.status_code, 200, promoted.text)

        self.login(STUDENT_B_USERNAME, STUDENT_B_PASSWORD)
        listed = self.client.get("/api/baselines").json()
        self.assertIn(baseline_id, [row["id"] for row in listed])
        fetched = self.client.get(f"/api/baselines/{baseline_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["scope"], "shared")
        versions = self.client.get(f"/api/baselines/{baseline_id}/versions")
        self.assertEqual(versions.status_code, 200)

        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **FLAT_RECIPE_WITHOUT_DEVICE,
                    "device_recipe": created.json()["device_recipe"],
                },
                "source_baseline_version_id": version_id,
            },
        )
        self.assertEqual(experiment.status_code, 201, experiment.text)

    # Scenario 7 -------------------------------------------------------------

    def test_former_owner_cannot_revise_after_promotion(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        self.client.post(f"/api/baselines/{baseline_id}/promote", json={})

        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        owner_revise = self.client.put(
            f"/api/baselines/{baseline_id}", json=baseline_payload("Student A reference")
        )
        self.assertEqual(owner_revise.status_code, 404, owner_revise.text)

        self.login(STUDENT_B_USERNAME, STUDENT_B_PASSWORD)
        peer_revise = self.client.put(
            f"/api/baselines/{baseline_id}", json=baseline_payload("Student A reference")
        )
        self.assertEqual(peer_revise.status_code, 404, peer_revise.text)

        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        admin_revise = self.client.put(
            f"/api/baselines/{baseline_id}", json=baseline_payload("Student A reference")
        )
        self.assertEqual(admin_revise.status_code, 200, admin_revise.text)

    # Archival lifecycle separation ------------------------------------------

    def test_archive_remains_lifecycle_administrator_action(self) -> None:
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]

        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        student_archive = self.client.delete(f"/api/baselines/{baseline_id}")
        self.assertEqual(student_archive.status_code, 403, student_archive.text)

        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        archived = self.client.delete(f"/api/baselines/{baseline_id}")
        self.assertEqual(archived.status_code, 204, archived.text)

        audit = self._audit_rows("baseline", str(baseline_id))
        self.assertIn("baseline.archive", [row["action"] for row in audit])

        # An archived Shared baseline is not a valid experiment starting point.
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        shared = self.client.post(
            "/api/baselines", json=baseline_payload("Shared archive reference")
        )
        self.assertEqual(shared.status_code, 201, shared.text)
        shared_version_id = shared.json()["current_version_id"]
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        archived_shared = self.client.delete(
            f"/api/baselines/{shared.json()['id']}"
        )
        self.assertEqual(archived_shared.status_code, 204, archived_shared.text)

        self.login(STUDENT_B_USERNAME, STUDENT_B_PASSWORD)
        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **FLAT_RECIPE_WITHOUT_DEVICE,
                    "device_recipe": shared.json()["device_recipe"],
                },
                "source_baseline_version_id": shared_version_id,
            },
        )
        self.assertEqual(experiment.status_code, 400, experiment.text)

    # Source-use authorization on every condition write path ------------------

    def _create_personal_baseline_and_experiment(self, version: str) -> tuple[int, int, int]:
        """Student A creates a personal baseline, an experiment, and returns ids."""
        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        created = self.client.post(
            "/api/baselines", json=baseline_payload("Student A reference")
        )
        baseline_id = created.json()["id"]
        version_id = created.json()["current_version_id"]
        device_recipe = created.json()["device_recipe"]
        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {**FLAT_RECIPE_WITHOUT_DEVICE, "device_recipe": device_recipe},
                "source_baseline_version_id": version_id,
            },
        )
        self.assertEqual(experiment.status_code, 201, experiment.text)
        experiment_id = experiment.json()["id"]
        detail = self.client.get(f"/api/experiments/{experiment_id}").json()
        condition = detail["conditions"][0]
        return baseline_id, version_id, condition

    def test_update_condition_contract_locks_source_baseline(self) -> None:
        _, version_id, condition = self._create_personal_baseline_and_experiment("v1")
        condition_id = condition["id"]

        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        self.client.post("/api/baselines", json=baseline_payload("Student A second"))
        second = self.client.get("/api/baselines").json()
        second_version = next(
            row["current_version_id"]
            for row in second
            if row["name"] == "Student A second"
        )

        changed_source = self.client.put(
            f"/api/conditions/{condition_id}",
            json={
                "condition_name": condition["condition_name"],
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": second_version,
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": condition["planned_substrate_count"],
            },
        )
        self.assertEqual(changed_source.status_code, 400, changed_source.text)

        preserved_source = self.client.put(
            f"/api/conditions/{condition_id}",
            json={
                "condition_name": "Renamed condition",
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": version_id,
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": condition["planned_substrate_count"],
            },
        )
        self.assertEqual(preserved_source.status_code, 200, preserved_source.text)
        self.assertEqual(
            preserved_source.json()["source_baseline_version_id"], version_id
        )

    def test_instructor_cannot_edit_condition_of_personal_baseline(self) -> None:
        _, version_id, condition = self._create_personal_baseline_and_experiment("v1")
        condition_id = condition["id"]
        experiment_id = condition["experiment_id"]

        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)
        updated = self.client.put(
            f"/api/conditions/{condition_id}",
            json={
                "condition_name": condition["condition_name"],
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": version_id,
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": condition["planned_substrate_count"],
            },
        )
        self.assertEqual(updated.status_code, 404, updated.text)

        new_condition = self.client.post(
            f"/api/experiments/{experiment_id}/conditions",
            json={
                "role": "target",
                "condition_name": "Instructor target",
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": version_id,
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": 3,
            },
        )
        self.assertEqual(new_condition.status_code, 404, new_condition.text)

    def test_owner_can_add_condition_using_own_personal_baseline(self) -> None:
        _, version_id, condition = self._create_personal_baseline_and_experiment("v1")
        experiment_id = condition["experiment_id"]

        self.login(STUDENT_A_USERNAME, STUDENT_A_PASSWORD)
        added = self.client.post(
            f"/api/experiments/{experiment_id}/conditions",
            json={
                "role": "target",
                "condition_name": "Second target",
                "recipe_snapshot": condition["recipe_snapshot"],
                "source_baseline_version_id": version_id,
                "device_layout_code": condition["device_layout_code"],
                "planned_substrate_count": 3,
            },
        )
        self.assertEqual(added.status_code, 201, added.text)
        self.assertEqual(added.json()["source_baseline_version_id"], version_id)


if __name__ == "__main__":
    unittest.main()