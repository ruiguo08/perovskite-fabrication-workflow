import asyncio
import hashlib
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from perovskite_bo import deposition_recipe_from_process
from tests.recipe_fixtures import FACTORY_LAYER_PRESETS as LAYER_PRESETS


def _create_shared_preset(client, name: str) -> dict:
    """Create an active shared SAM preset as the logged-in administrator."""
    from copy import deepcopy

    created = client.post(
        "/api/layer-presets",
        json={
            "name": name,
            "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
            "deposition_process": None,
            "scope": "shared",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _create_active_material(client, name: str) -> dict:
    """Create an active substrate material as the logged-in administrator."""
    created = client.post(
        "/api/materials", json={"category": "substrate", "name": name}
    )
    assert created.status_code == 201, created.text
    material = created.json()
    if material["status"] != "active":
        activated = client.patch(
            f"/api/materials/{material['id']}", json={"status": "active"}
        )
        assert activated.status_code == 200, activated.text
        material = activated.json()
    return material
from tests.layout_fixtures import seed_standard_layouts
from web import create_app
from web.auth import authenticate_credentials, issue_session, hash_password
from web.database import Database
from web.repository import UserRole, WebRepository

from tests.test_web_app import (
    TEST_PASSWORD,
    TEST_USERNAME,
    VALID_RECIPE,
    complete_guided_setup,
    releasable_result_recipe,
)


class AuthenticationSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "auth.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        # Seed the layout catalog as the administrator test user before any
        # per-test role switching.
        self.login()
        seed_standard_layouts(self.client)
        self.logout()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def login(self, username: str = TEST_USERNAME, password: str = TEST_PASSWORD) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        self.assertEqual(csrf.status_code, 200)
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
                "login_csrf": csrf.json()["login_csrf_token"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def logout(self) -> None:
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.client.headers.pop("X-CSRF-Token", None)

    def create_user(self, username: str, role: UserRole, password: str) -> None:
        response = self.client.post(
            "/api/users",
            json={
                "username": username,
                "display_name": username.title(),
                "password": password,
                "role": role.value,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def create_result_batch(self) -> tuple[int, int]:
        created = self.client.post(
            "/api/experiments", json={"recipe": releasable_result_recipe()}
        )
        self.assertEqual(created.status_code, 201, created.text)
        experiment_id = int(created.json()["id"])
        for status in ("pending_approval", "approved", "released"):
            transition = self.client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": status},
            )
            self.assertEqual(transition.status_code, 204, transition.text)
        batch = self.client.post(
            f"/api/experiments/{experiment_id}/fabrication-batches", json={}
        )
        self.assertEqual(batch.status_code, 201, batch.text)
        batch_id = int(batch.json()["id"])
        for status in ("ready", "in_progress"):
            response = self.client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={"status": status},
            )
            self.assertEqual(response.status_code, 204, response.text)
        return experiment_id, batch_id

    def test_unauthenticated_html_redirects_and_api_rejects(self) -> None:
        html_response = self.client.get("/experiments", follow_redirects=False)
        api_response = self.client.get("/api/experiments")

        self.assertEqual(html_response.status_code, 303)
        self.assertEqual(html_response.headers["location"], "/app/experiments")
        self.assertEqual(api_response.status_code, 401)

    def test_login_uses_opaque_protected_cookie_and_argon2_hash(self) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        login_csrf = csrf.json()["login_csrf_token"]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": login_csrf,
            },
        )

        self.assertEqual(response.status_code, 200)
        cookie_headers = response.headers.get_list("set-cookie")
        session_cookie = next(value for value in cookie_headers if value.startswith("perovskite_session="))
        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=strict", session_cookie)
        self.assertGreater(len(self.client.cookies.get("perovskite_session")), 50)
        with closing(sqlite3.connect(self.database_path)) as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM users WHERE username = ?", (TEST_USERNAME,)
            ).fetchone()[0]
            token_hash = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertTrue(password_hash.startswith("$argon2"))
        self.assertNotIn(TEST_PASSWORD, password_hash)
        self.assertEqual(
            token_hash,
            hashlib.sha256(self.client.cookies.get("perovskite_session").encode()).hexdigest(),
        )

    def test_authenticated_mutation_requires_csrf(self) -> None:
        self.login()
        self.client.headers.pop("X-CSRF-Token")

        response = self.client.post("/api/experiments", json={"recipe": VALID_RECIPE})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/experiments").json(), [])

    def test_student_plans_require_complete_recipe_and_cannot_manage_users(self) -> None:
        student_password = "laboratory student password 2026"
        self.login()
        self.create_user("student-one", UserRole.STUDENT, student_password)
        device_recipe, deposition_process = complete_guided_setup()
        saved_baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "Instructor-owned baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        ).json()
        self.logout()
        self.login("student-one", student_password)

        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
                "source_baseline_version_id": saved_baseline["current_version_id"],
            },
        )
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "Student baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )

        self.assertEqual(experiment.status_code, 201, experiment.text)
        # A baseline reference is provenance only: a student may plan the same
        # complete recipe from scratch without referencing any baseline.
        from_scratch = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
            },
        )
        self.assertEqual(from_scratch.status_code, 201, from_scratch.text)
        # A student may create their own Personal baseline (created-by role
        # no longer gates creation) but still cannot manage accounts.
        self.assertEqual(baseline.status_code, 201, baseline.text)
        self.assertEqual(baseline.json()["scope"], "personal")
        self.assertEqual(self.client.get("/api/users").status_code, 403)

    def test_instructor_can_create_baselines(self) -> None:
        instructor_password = "laboratory instructor password 2026"
        self.login()
        self.create_user("instructor-one", UserRole.INSTRUCTOR, instructor_password)
        self.logout()
        self.login("instructor-one", instructor_password)
        device_recipe, deposition_process = complete_guided_setup()

        response = self.client.post(
            "/api/baselines",
            json={
                "name": "Instructor baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get("/api/users").status_code, 403)

    def test_student_campaign_directory_is_read_only(self) -> None:
        student_password = "campaign directory student password 2026"
        self.login()
        self.create_user(
            "campaign-directory-student",
            UserRole.STUDENT,
            student_password,
        )
        created = self.client.post(
            "/api/campaigns",
            json={
                "code": "student-visible-campaign",
                "display_name": "Student-visible campaign",
                "description": "Read-only directory entry",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        closed = self.client.post(
            "/api/campaigns",
            json={
                "code": "student-hidden-campaign",
                "display_name": "Student-hidden campaign",
                "description": "Closed directory entry",
            },
        )
        self.assertEqual(closed.status_code, 201, closed.text)
        updated = self.client.patch(
            "/api/campaigns/student-hidden-campaign",
            json={"status": "closed"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.logout()

        self.login("campaign-directory-student", student_password)
        response = self.client.get("/api/campaigns")

        self.assertEqual(response.status_code, 200, response.text)
        campaigns = response.json()
        self.assertIn(
            "student-visible-campaign",
            {campaign["code"] for campaign in campaigns},
        )
        self.assertNotIn(
            "student-hidden-campaign",
            {campaign["code"] for campaign in campaigns},
        )
        forbidden = self.client.post(
            "/api/campaigns",
            json={
                "code": "student-created-campaign",
                "display_name": "Student-created campaign",
                "description": "",
            },
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    def test_students_can_only_access_experiments_they_created(self) -> None:
        owner_password = "experiment owner password 2026"
        other_password = "other student password 2026"
        instructor_password = "experiment instructor password 2026"
        self.login()
        self.create_user("experiment-owner", UserRole.STUDENT, owner_password)
        self.create_user("other-student", UserRole.STUDENT, other_password)
        self.create_user(
            "experiment-instructor",
            UserRole.INSTRUCTOR,
            instructor_password,
        )
        campaign = self.client.post(
            "/api/campaigns",
            json={
                "code": "owner-private-series",
                "display_name": "Private ownership test",
                "description": "",
            },
        )
        self.assertEqual(campaign.status_code, 201, campaign.text)
        device_recipe, deposition_process = complete_guided_setup()
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "Ownership baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(baseline.status_code, 201, baseline.text)
        baseline_version_id = baseline.json()["current_version_id"]
        self.logout()

        self.login("experiment-owner", owner_password)
        created = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
                "campaign_id": "owner-private-series",
                "source_baseline_version_id": baseline_version_id,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        experiment_id = created.json()["id"]
        self.assertEqual(
            self.client.get(f"/api/experiments/{experiment_id}").status_code,
            200,
        )
        self.logout()

        self.login("other-student", other_password)
        self.assertEqual(self.client.get("/api/experiments").json(), [])
        self.assertEqual(
            self.client.get(
                f"/api/experiments/{experiment_id}",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/experiments/{experiment_id}/conditions"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"/experiments/{experiment_id}/upload",
                follow_redirects=False,
            ).status_code,
            303,
        )
        foreign_upload = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "result.csv",
                    b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n",
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": "1"},
        )
        self.assertEqual(foreign_upload.status_code, 404)
        self.logout()

        self.login("experiment-instructor", instructor_password)
        visible = self.client.get("/api/experiments")
        self.assertEqual([record["id"] for record in visible.json()], [experiment_id])
        self.assertEqual(
            self.client.get(f"/experiments/{experiment_id}").status_code,
            200,
        )
        conditions = self.client.get(
            f"/api/experiments/{experiment_id}/conditions"
        )
        self.assertEqual(conditions.status_code, 200)
        self.assertGreaterEqual(len(conditions.json()), 2)

    def test_students_manage_only_their_own_layer_presets(self) -> None:
        first_password = "first preset student password 2026"
        second_password = "second preset student password 2026"
        self.login()
        self.create_user("preset-student-one", UserRole.STUDENT, first_password)
        self.create_user("preset-student-two", UserRole.STUDENT, second_password)
        self.logout()

        self.login()
        _create_shared_preset(self.client, "Catalog SAM baseline")
        self.logout()

        payload = {
            "name": "My SAM process",
            "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
            "deposition_process": None,
        }
        self.login("preset-student-one", first_password)
        created = self.client.post("/api/layer-presets", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        preset_id = created.json()["id"]
        first_version_id = created.json()["current_version_id"]
        payload["layer"]["name"] = "Updated SAM"
        updated = self.client.put(f"/api/layer-presets/{preset_id}", json=payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["current_revision_number"], 2)
        self.assertNotEqual(updated.json()["current_version_id"], first_version_id)
        self.logout()

        self.login("preset-student-two", second_password)
        second_visible = self.client.get("/api/layer-presets").json()
        self.assertTrue(second_visible)
        self.assertTrue(all(item["scope"] == "shared" for item in second_visible))
        self.assertNotIn(preset_id, [item["id"] for item in second_visible])
        self.assertEqual(
            self.client.put(f"/api/layer-presets/{preset_id}", json=payload).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"/api/layer-presets/{preset_id}").status_code,
            404,
        )
        same_name = self.client.post("/api/layer-presets", json=payload)
        self.assertEqual(same_name.status_code, 201, same_name.text)
        self.logout()

        self.login("preset-student-one", first_password)
        deactivated = self.client.delete(f"/api/layer-presets/{preset_id}")
        self.assertEqual(deactivated.status_code, 204, deactivated.text)
        active = self.client.get("/api/layer-presets").json()
        self.assertTrue(active)
        self.assertTrue(all(item["scope"] == "shared" for item in active))
        inactive = self.client.get(
            "/api/layer-presets", params={"include_inactive": "true"}
        ).json()
        own_inactive = next(item for item in inactive if item["id"] == preset_id)
        self.assertEqual(own_inactive["status"], "inactive")

    def test_material_directory_proposals_require_staff_review(self) -> None:
        student_password = "material student password 2026"
        other_password = "other material student password 2026"
        instructor_password = "material instructor password 2026"
        self.login()
        self.create_user("material-student", UserRole.STUDENT, student_password)
        self.create_user("other-material-student", UserRole.STUDENT, other_password)
        self.create_user("material-instructor", UserRole.INSTRUCTOR, instructor_password)
        self.logout()

        self.login()
        _create_active_material(self.client, "ITO")
        self.logout()

        self.login("material-student", student_password)
        directory_page = self.client.get("/api/materials")
        self.assertEqual(directory_page.status_code, 200, directory_page.text)
        self.assertEqual(directory_page.status_code, 200)
        initial_catalog = self.client.get("/api/materials")
        self.assertEqual(initial_catalog.status_code, 200, initial_catalog.text)
        ito = next(item for item in initial_catalog.json() if item["name"] == "ITO")
        proposal = self.client.post(
            "/api/materials",
            json={"category": "chemical", "name": "Student additive"},
        )
        self.assertEqual(proposal.status_code, 201, proposal.text)
        self.assertEqual(proposal.json()["status"], "pending")
        material_id = proposal.json()["id"]
        product = self.client.post(
            f"/api/materials/{ito['id']}/products",
            json={"vendor": "Student Supplier", "catalog_number": "ADD-001"},
        )
        self.assertEqual(product.status_code, 201, product.text)
        product_id = next(
            item["id"]
            for item in product.json()["products"]
            if item["catalog_number"] == "ADD-001"
        )
        self.assertEqual(
            self.client.patch(
                f"/api/materials/{material_id}", json={"status": "active"}
            ).status_code,
            403,
        )
        self.logout()

        self.login("other-material-student", other_password)
        other_catalog = self.client.get("/api/materials").json()
        self.assertNotIn("Student additive", [item["name"] for item in other_catalog])
        other_ito = next(item for item in other_catalog if item["name"] == "ITO")
        self.assertNotIn(
            "ADD-001", [item["catalog_number"] for item in other_ito["products"]]
        )
        self.logout()

        self.login("material-instructor", instructor_password)
        approved_material = self.client.patch(
            f"/api/materials/{material_id}", json={"status": "active"}
        )
        approved_product = self.client.patch(
            f"/api/material-products/{product_id}", json={"status": "active"}
        )
        self.assertEqual(approved_material.status_code, 200, approved_material.text)
        self.assertEqual(approved_product.status_code, 200, approved_product.text)
        self.logout()

        self.login("other-material-student", other_password)
        published_catalog = self.client.get("/api/materials").json()
        self.assertIn("Student additive", [item["name"] for item in published_catalog])
        published_ito = next(item for item in published_catalog if item["name"] == "ITO")
        self.assertIn(
            "ADD-001", [item["catalog_number"] for item in published_ito["products"]]
        )

    def test_student_cannot_add_product_to_own_inactive_material(self) -> None:
        student_password = "inactive material student password 2026"
        self.login()
        self.create_user("inactive-material-student", UserRole.STUDENT, student_password)
        self.logout()

        self.login("inactive-material-student", student_password)
        proposal = self.client.post(
            "/api/materials",
            json={"category": "chemical", "name": "Inactive parent material"},
        )
        self.assertEqual(proposal.status_code, 201, proposal.text)
        material_id = proposal.json()["id"]
        self.logout()

        self.login()
        deactivated = self.client.patch(
            f"/api/materials/{material_id}", json={"status": "inactive"}
        )
        self.assertEqual(deactivated.status_code, 200, deactivated.text)
        self.logout()

        self.login("inactive-material-student", student_password)
        rejected = self.client.post(
            f"/api/materials/{material_id}/products",
            json={"vendor": "Hidden Supplier", "catalog_number": "HIDDEN-001"},
        )
        self.assertEqual(rejected.status_code, 403, rejected.text)

        with closing(sqlite3.connect(self.database_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM material_products WHERE material_id = ?",
                (material_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_shared_layer_presets_are_visible_but_student_read_only(self) -> None:
        student_password = "shared preset student password 2026"
        self.login()
        self.create_user("shared-preset-student", UserRole.STUDENT, student_password)
        _create_shared_preset(self.client, "Shared SAM one")
        _create_shared_preset(self.client, "Shared SAM two")
        administrator_presets = self.client.get("/api/layer-presets").json()
        shared = next(item for item in administrator_presets if item["scope"] == "shared")
        inactive_shared = next(
            item
            for item in administrator_presets
            if item["scope"] == "shared" and item["id"] != shared["id"]
        )
        self.assertEqual(
            self.client.delete(
                f"/api/layer-presets/{inactive_shared['id']}"
            ).status_code,
            204,
        )
        self.logout()

        self.login("shared-preset-student", student_password)
        visible = self.client.get("/api/layer-presets").json()
        self.assertIn(shared["id"], [item["id"] for item in visible])
        include_inactive = self.client.get(
            "/api/layer-presets", params={"include_inactive": "true"}
        ).json()
        self.assertNotIn(
            inactive_shared["id"], [item["id"] for item in include_inactive]
        )
        self.assertEqual(
            self.client.put(
                f"/api/layer-presets/{shared['id']}",
                json={
                    "name": shared["name"],
                    "layer": shared["layer"],
                    "deposition_process": shared["deposition_process"],
                },
            ).status_code,
            404,
        )

    def test_layer_preset_current_version_must_belong_to_same_preset(self) -> None:
        self.login()
        first_payload = {
            "name": "Integrity preset one",
            "layer": deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"]),
            "deposition_process": None,
        }
        second_payload = {
            **first_payload,
            "name": "Integrity preset two",
        }
        first = self.client.post("/api/layer-presets", json=first_payload)
        second = self.client.post("/api/layer-presets", json=second_payload)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE layer_presets SET current_version_id = ? WHERE id = ?",
                    (second.json()["current_version_id"], first.json()["id"]),
                )

    def test_material_records_survive_restart_unchanged(self) -> None:
        # There is no factory material seed: user-created records are simply
        # persistent rows, so an app restart must not add or remove any.
        self.login()
        created = self.client.post(
            "/api/materials", json={"category": "substrate", "name": "ITO"}
        )
        self.assertEqual(created.status_code, 201, created.text)
        material_id = created.json()["id"]
        renamed = self.client.patch(
            f"/api/materials/{material_id}", json={"name": "ITO renamed by administrator"}
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.client_context.__exit__(None, None, None)

        self.app = create_app(self.database_path, secure_cookies=False)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.login()
        names = [item["name"] for item in self.client.get("/api/materials").json()]
        self.assertIn("ITO renamed by administrator", names)
        self.assertNotIn("ITO", names)

    def test_in_flight_login_cannot_survive_a_password_reset(self) -> None:
        """Deterministic interleaving of the login/reset race.

        The login coroutine has already read the old credential revision (the
        ``user`` record) when an administrator reset commits; issuing the
        session from that stale record must be rejected instead of yielding a
        session authenticated by the replaced password.
        """
        repository: WebRepository = self.app.state.repository
        settings = self.app.state.auth_settings
        stale_user = asyncio.run(repository.get_user_by_username(TEST_USERNAME))
        assert stale_user is not None

        asyncio.run(
            repository.reset_password(
                stale_user.id,
                password_hash=hash_password("a-brand-new-password-123"),
                actor_user_id=stale_user.id,
                client_ip=None,
            )
        )

        with self.assertRaises(PermissionError):
            asyncio.run(
                issue_session(
                    repository,
                    settings,
                    user=stale_user,
                    client_ip=None,
                    user_agent=None,
                )
            )

        # The new password issues a session normally.
        refreshed = asyncio.run(repository.get_user_by_username(TEST_USERNAME))
        assert refreshed is not None
        issued = asyncio.run(
            issue_session(
                repository,
                settings,
                user=refreshed,
                client_ip=None,
                user_agent=None,
            )
        )
        self.assertTrue(issued.session_token)

    def test_reset_during_verification_still_rejects_the_session(self) -> None:
        """A reset committing after the hash was read but before the session
        is issued must still be caught. authenticate_credentials must hand
        back the record it verified against — a fresh re-read would surface
        the reset's password_changed_at and defeat the currency predicate."""
        repository: WebRepository = self.app.state.repository
        settings = self.app.state.auth_settings
        original_lookup = repository.get_user_by_username

        async def lookup_then_reset(username: str):
            user = await original_lookup(username)
            await repository.reset_password(
                user.id,
                password_hash=hash_password("a-brand-new-password-123"),
                actor_user_id=user.id,
                client_ip=None,
            )
            # The caller verifies against this stale record.
            return user

        repository.get_user_by_username = lookup_then_reset  # type: ignore[method-assign]
        try:
            verified = asyncio.run(
                authenticate_credentials(
                    repository,
                    settings,
                    username=TEST_USERNAME,
                    password=TEST_PASSWORD,
                )
            )
        finally:
            repository.get_user_by_username = original_lookup  # type: ignore[method-assign]
        assert verified is not None
        with self.assertRaises(PermissionError):
            asyncio.run(
                issue_session(
                    repository,
                    settings,
                    user=verified,
                    client_ip=None,
                    user_agent=None,
                )
            )

    def test_password_reset_revokes_existing_sessions(self) -> None:
        self.login()
        repository: WebRepository = self.app.state.repository
        admin = asyncio.run(repository.get_user_by_username(TEST_USERNAME))
        assert admin is not None
        reset = self.client.post(
            f"/api/users/{admin.id}/password",
            json={"password": "a-brand-new-password-123"},
        )
        self.assertEqual(reset.status_code, 204, reset.text)

        # The reset wiped the sessions, so the old cookie is rejected...
        self.assertEqual(self.client.get("/api/experiments").status_code, 401)
        # ...and the new password works.
        self.login(password="a-brand-new-password-123")

    def test_sessions_predating_a_password_change_are_rejected(self) -> None:
        """Defense in depth: a session that escaped the reset's wipe must
        still fail resolution because it was created before the password
        change."""
        self.login()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE users SET password_changed_at = '2099-01-01 00:00:00.000000'"
            )
            connection.commit()

        self.assertEqual(self.client.get("/api/experiments").status_code, 401)
        with closing(sqlite3.connect(self.database_path)) as connection:
            session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        self.assertEqual(session_count, 0)

    def test_expired_session_is_rejected_and_logout_is_audited(self) -> None:
        self.login()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                "UPDATE sessions SET expires_at = '2000-01-01 00:00:00.000000'"
            )
            connection.commit()

        self.assertEqual(self.client.get("/api/experiments").status_code, 401)
        with closing(sqlite3.connect(self.database_path)) as connection:
            session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            actions = {
                row[0] for row in connection.execute("SELECT action FROM audit_events")
            }
        self.assertEqual(session_count, 0)
        self.assertIn("session.login", actions)
        self.assertIn("session.logout", actions)

    def test_upload_rejects_disguised_binary_and_non_csv_filename(self) -> None:
        self.login()
        experiment_id, batch_id = self.create_result_batch()

        binary = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": ("result.csv", b"voltage,current\n\x00data", "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )
        wrong_extension = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "result.exe",
                    b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n",
                    "application/octet-stream",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(binary.status_code, 400)
        self.assertEqual(wrong_extension.status_code, 400)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM result_files").fetchone()[0], 0)

    def test_upload_stores_sanitized_name_and_integrity_hash(self) -> None:
        self.login()
        experiment_id, batch_id = self.create_result_batch()
        content = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"

        response = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": ("../A001 Channel 1.csv", content, "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["filename"], "A001 Channel 1.csv")
        self.assertEqual(response.json()["sha256"], hashlib.sha256(content).hexdigest())

    def test_oversized_database_strings_are_rejected_before_persistence(self) -> None:
        self.login()

        campaign = self.client.post(
            "/api/experiments",
            json={"recipe": VALID_RECIPE, "campaign_id": "c" * 161},
        )
        device_recipe, deposition_process = complete_guided_setup()
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": "r" * 161,
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        user = self.client.post(
            "/api/users",
            json={
                "username": "bounded-user",
                "display_name": "d" * 121,
                "password": "bounded account password 2026",
                "role": UserRole.STUDENT.value,
            },
        )

        self.assertEqual(campaign.status_code, 422)
        self.assertEqual(baseline.status_code, 422)
        self.assertEqual(user.status_code, 422)
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM "baselines"').fetchone()[0], 0)
            self.assertIsNone(
                connection.execute(
                    "SELECT id FROM users WHERE username = 'bounded-user'"
                ).fetchone()
            )


    def test_batch_writes_enforce_student_ownership_and_privileged_cancellation(self) -> None:
        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        password = "batch ownership student password 2026"
        self.login()
        self.create_user("batch-owner", UserRole.STUDENT, password)
        owner = asyncio.run(
            self.app.state.repository.get_user_by_username("batch-owner")
        )
        self.assertIsNotNone(owner)
        own_experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.app.state.repository,
                "student-owned-batch",
                actor_user_id=1,
            )
        )
        from sqlalchemy import update
        from web.database import experiments

        async def assign_owner() -> None:
            async with self.app.state.database.begin() as connection:
                await connection.execute(
                    update(experiments)
                    .where(experiments.c.id == own_experiment_id)
                    .values(created_by_id=owner.id)
                )

        asyncio.run(assign_owner())
        own_batch = asyncio.run(
            self.app.state.repository.create_fabrication_batch(
                own_experiment_id, actor_user_id=owner.id
            )
        )
        foreign_experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.app.state.repository,
                "administrator-owned-batch",
                actor_user_id=1,
            )
        )
        foreign_batch = asyncio.run(
            self.app.state.repository.create_fabrication_batch(
                foreign_experiment_id, actor_user_id=1
            )
        )
        self.logout()
        self.login("batch-owner", password)

        self.assertEqual(
            self.client.get(f"/api/fabrication-batches/{own_batch.id}").status_code,
            200,
        )
        cancelled = self.client.patch(
            f"/api/fabrication-batches/{own_batch.id}/status",
            json={"status": "cancelled"},
        )
        self.assertEqual(cancelled.status_code, 403, cancelled.text)
        self.assertEqual(
            self.client.get(f"/api/fabrication-batches/{foreign_batch.id}").status_code,
            404,
        )
        foreign_preparation = self.client.post(
            f"/api/fabrication-batches/{foreign_batch.id}/solution-preparations",
            json={"planned_solution_snapshot": {"unauthorized": True}},
        )
        self.assertEqual(foreign_preparation.status_code, 404, foreign_preparation.text)
        foreign_deviation = self.client.post(
            f"/api/fabrication-batches/{foreign_batch.id}/deviations",
            json={
                "category": "other",
                "severity": "info",
                "description": "unauthorized",
            },
        )
        self.assertEqual(foreign_deviation.status_code, 404, foreign_deviation.text)


class LoginAttemptReservationTests(unittest.TestCase):
    def test_concurrent_attempts_are_atomically_limited(self) -> None:
        async def exercise(database_path: Path) -> None:
            database = Database(database_path, create_schema=True)
            repository = WebRepository(database)
            try:
                await database.initialize()
                user = await repository.create_user(
                    username="concurrent-user",
                    display_name="Concurrent User",
                    password_hash=hash_password("concurrent account password 2026"),
                    role=UserRole.STUDENT,
                )
                attempted_at = datetime.now(timezone.utc)
                reservations = await asyncio.gather(
                    *(
                        repository.reserve_login_attempt(
                            user.id,
                            attempted_at=attempted_at,
                            failure_limit=5,
                            lockout_until=attempted_at + timedelta(minutes=15),
                        )
                        for _ in range(20)
                    )
                )
                updated = await repository.get_user(user.id)

                self.assertEqual(sum(reservations), 5)
                self.assertEqual(updated.failed_login_count, 5)
                self.assertIsNotNone(updated.locked_until)
            finally:
                await database.dispose()

        with tempfile.TemporaryDirectory() as temporary_directory:
            asyncio.run(exercise(Path(temporary_directory) / "login-attempts.sqlite3"))

    def test_safe_next_path_rejects_backslashes_and_control_characters(self) -> None:
        from web.auth import safe_next_path, safe_next_path_or_none

        # Valid internal paths pass through both helpers.
        self.assertEqual(safe_next_path("/experiments/7"), "/experiments/7")
        self.assertEqual(safe_next_path_or_none("/app/overview"), "/app/overview")

        # Open-redirect vectors are rejected (back to the safe fallback/None).
        self.assertEqual(safe_next_path("/\\evil.example"), "/experiments")
        self.assertIsNone(safe_next_path_or_none("/\\evil.example"))
        self.assertIsNone(safe_next_path_or_none("//evil.example"))
        self.assertIsNone(safe_next_path_or_none("/\tevil"))
        self.assertIsNone(safe_next_path_or_none("javascript:alert(1)"))
        self.assertEqual(safe_next_path(None), "/experiments")
        self.assertIsNone(safe_next_path_or_none(None))


if __name__ == "__main__":
    unittest.main()
