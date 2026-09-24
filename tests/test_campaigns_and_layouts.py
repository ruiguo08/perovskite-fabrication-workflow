"""Tests for the device layout catalog and campaign management."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from web import create_app
from web.device_layouts import expected_device_count
from web.repository import UserRole
from layout_fixtures import fixture_layout, fixture_layouts, seed_standard_layouts
from test_web_app import VALID_RECIPE

TEST_USERNAME = "admin"
TEST_PASSWORD = "Adm1n!password"


def _layout(code: str):
    return fixture_layout(code)


class DeviceLayoutCatalogTests(unittest.TestCase):
    """Pure-Python tests for the seeded device layout catalog."""

    def test_standard_catalog_defines_four_layouts(self) -> None:
        self.assertEqual(len(fixture_layouts()), 4)

    def test_layout_codes_match_spec(self) -> None:
        codes = {layout.code for layout in fixture_layouts()}
        self.assertEqual(
            codes,
            {
                "15x15_dual_005",
                "20x20_single_1cm2",
                "25x25_six_010",
                "25x25_single_1cm2",
            },
        )

    def test_15x15_dual_values(self) -> None:
        layout = _layout("15x15_dual_005")
        self.assertEqual(layout.substrate_width_mm, Decimal("15"))
        self.assertEqual(layout.substrate_length_mm, Decimal("15"))
        self.assertEqual(layout.devices_per_substrate, 2)
        self.assertEqual(layout.device_active_area_cm2, Decimal("0.05"))
        self.assertEqual(layout.total_active_area_cm2, Decimal("0.10"))

    def test_20x20_single_values(self) -> None:
        layout = _layout("20x20_single_1cm2")
        self.assertEqual(layout.devices_per_substrate, 1)
        self.assertEqual(layout.device_active_area_cm2, Decimal("1.00"))
        self.assertEqual(layout.total_active_area_cm2, Decimal("1.00"))

    def test_25x25_six_values(self) -> None:
        layout = _layout("25x25_six_010")
        self.assertEqual(layout.devices_per_substrate, 6)
        self.assertEqual(layout.device_active_area_cm2, Decimal("0.10"))
        self.assertEqual(layout.total_active_area_cm2, Decimal("0.60"))

    def test_25x25_single_values(self) -> None:
        layout = _layout("25x25_single_1cm2")
        self.assertEqual(layout.devices_per_substrate, 1)
        self.assertEqual(layout.device_active_area_cm2, Decimal("1.017"))
        self.assertEqual(layout.total_active_area_cm2, Decimal("1.017"))
        self.assertEqual(layout.version, 2)

    def test_expected_device_count(self) -> None:
        layout = _layout("25x25_six_010")
        self.assertEqual(expected_device_count(3, layout), 18)
        self.assertEqual(expected_device_count(1, layout), 6)

    def test_expected_device_count_rejects_zero(self) -> None:
        with self.assertRaises(ValueError):
            expected_device_count(0, _layout("15x15_dual_005"))

    def test_non_catalog_code_rejected(self) -> None:
        from web.device_layouts import DeviceLayout

        def _unknown(code: str) -> DeviceLayout:
            matches = [layout for layout in fixture_layouts() if layout.code == code]
            if not matches:
                raise ValueError(f"device layout must be one of the catalog entries, not {code!r}")
            return matches[0]

        with self.assertRaises(ValueError):
            _unknown("99x99_bogus")

    def test_areas_are_decimal_not_float(self) -> None:
        for layout in fixture_layouts():
            self.assertIsInstance(layout.device_active_area_cm2, Decimal)
            self.assertIsInstance(layout.total_active_area_cm2, Decimal)


class CampaignApiTests(unittest.TestCase):
    """Campaign and device-layout API with authentication."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "campaigns.sqlite3"
        app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self._login(TEST_USERNAME, TEST_PASSWORD)
        seed_standard_layouts(self.client)

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        # Windows keeps the SQLite file locked while pooled connections are
        # open, so dispose before TemporaryDirectory.cleanup() removes it.
        asyncio.run(self.client.app.state.database.dispose())
        self.tmp.cleanup()

    def _login(self, username: str, password: str) -> None:
        login_csrf = self.client.get("/api/auth/login-csrf").json()["login_csrf_token"]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": password,
                "login_csrf": login_csrf,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def _create_user(self, username: str, role: UserRole, password: str) -> None:
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

    def _logout(self) -> None:
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204, response.text)
        self.client.headers.pop("X-CSRF-Token", None)

    # -- Device layouts ------------------------------------------------

    def test_device_layouts_seeded(self) -> None:
        response = self.client.get("/api/device-layouts")
        self.assertEqual(response.status_code, 200)
        layouts = response.json()
        self.assertEqual(len(layouts), 4)
        codes = {item["code"] for item in layouts}
        self.assertIn("15x15_dual_005", codes)
        self.assertIn("25x25_six_010", codes)
        versions = {item["code"]: item["version"] for item in layouts}
        self.assertEqual(versions["15x15_dual_005"], 1)
        self.assertEqual(versions["25x25_single_1cm2"], 2)

    def test_device_layout_areas_are_strings_not_floats(self) -> None:
        response = self.client.get("/api/device-layouts")
        layouts = response.json()
        for layout in layouts:
            self.assertIsInstance(layout["device_active_area_cm2"], str)

    def test_admin_can_create_layout_version_and_latest_wins(self) -> None:
        created = self.client.post(
            "/api/device-layouts",
            json={
                "code": "15x15_dual_005",
                "version": 2,
                "substrate_width_mm": "15",
                "substrate_length_mm": "15",
                "devices_per_substrate": 4,
                "device_active_area_cm2": "0.04",
                "total_active_area_cm2": "0.16",
                "description": "15 × 15 mm substrate, 4 devices, 0.04 cm² each",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        layouts = self.client.get("/api/device-layouts").json()
        by_code = {layout["code"]: layout for layout in layouts}
        self.assertEqual(by_code["15x15_dual_005"]["version"], 2)
        self.assertEqual(by_code["15x15_dual_005"]["devices_per_substrate"], 4)

    def test_create_returns_the_inserted_version(self) -> None:
        # v2 exists; creating the older v1 must return v1 (not the catalog's
        # latest version for the code).
        newest = self.client.post(
            "/api/device-layouts",
            json={
                "code": "backfill_probe",
                "version": 2,
                "substrate_width_mm": "10",
                "substrate_length_mm": "10",
                "devices_per_substrate": 4,
                "device_active_area_cm2": "0.04",
                "total_active_area_cm2": "0.16",
                "description": "backfill probe v2",
            },
        )
        self.assertEqual(newest.status_code, 201, newest.text)
        self.assertEqual(newest.json()["version"], 2)
        older = self.client.post(
            "/api/device-layouts",
            json={
                "code": "backfill_probe",
                "version": 1,
                "substrate_width_mm": "10",
                "substrate_length_mm": "10",
                "devices_per_substrate": 1,
                "device_active_area_cm2": "0.05",
                "total_active_area_cm2": "0.05",
                "description": "backfilled v1 geometry",
            },
        )
        self.assertEqual(older.status_code, 201, older.text)
        self.assertEqual(older.json()["version"], 1)
        self.assertEqual(older.json()["devices_per_substrate"], 1)
        # The catalog keeps serving the latest version to students.
        layouts = self.client.get("/api/device-layouts").json()
        by_code = {layout["code"]: layout for layout in layouts}
        self.assertEqual(by_code["backfill_probe"]["version"], 2)

    def test_huge_decimal_values_are_rejected_not_500(self) -> None:
        response = self.client.post(
            "/api/device-layouts",
            json={
                "code": "huge_probe",
                "version": 1,
                "substrate_width_mm": "1e30",
                "substrate_length_mm": "10",
                "devices_per_substrate": 1,
                "device_active_area_cm2": "0.05",
                "total_active_area_cm2": "0.05",
                "description": "huge probe",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("must be below 1000000", response.json()["detail"])

    def test_precision_beyond_numeric_scale_is_rejected(self) -> None:
        response = self.client.post(
            "/api/device-layouts",
            json={
                "code": "precision_probe",
                "version": 1,
                "substrate_width_mm": "10",
                "substrate_length_mm": "10",
                "devices_per_substrate": 1,
                "device_active_area_cm2": "0.00001",
                "total_active_area_cm2": "0.05",
                "description": "precision probe",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("4 decimal places", response.json()["detail"])

    def test_duplicate_layout_code_version_is_rejected(self) -> None:
        response = self.client.post(
            "/api/device-layouts",
            json={
                "code": "15x15_dual_005",
                "version": 1,
                "substrate_width_mm": "15",
                "substrate_length_mm": "15",
                "devices_per_substrate": 2,
                "device_active_area_cm2": "0.05",
                "total_active_area_cm2": "0.10",
                "description": "duplicate",
            },
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("already exists", response.json()["detail"])

    def test_every_decimal_field_rejects_range_and_precision_faults(self) -> None:
        """All four NUMERIC(10,4) fields share one validation loop; drive
        both fault classes through each field so a regression in the loop
        (or an accidental field-specific bypass) fails loudly."""
        base = {
            "code": "boundary_probe",
            "version": 1,
            "substrate_width_mm": "10",
            "substrate_length_mm": "10",
            "devices_per_substrate": 1,
            "device_active_area_cm2": "0.05",
            "total_active_area_cm2": "0.05",
            "description": "boundary probe",
        }
        for field in (
            "substrate_width_mm",
            "substrate_length_mm",
            "device_active_area_cm2",
            "total_active_area_cm2",
        ):
            for bad, expected_detail in (
                ("1e30", "must be below 1000000"),
                ("1000000", "must be below 1000000"),
                ("0.00001", "4 decimal places"),
            ):
                with self.subTest(field=field, value=bad):
                    payload = {**base, field: bad}
                    payload["code"] = f"boundary_{field}_{bad}"
                    response = self.client.post(
                        "/api/device-layouts", json=payload
                    )
                    self.assertEqual(response.status_code, 400, response.text)
                    self.assertIn(expected_detail, response.json()["detail"])

    def test_layout_integer_and_text_validations_reject_input(self) -> None:
        base = {
            "code": "integrity_probe",
            "version": 1,
            "substrate_width_mm": "10",
            "substrate_length_mm": "10",
            "devices_per_substrate": 1,
            "device_active_area_cm2": "0.05",
            "total_active_area_cm2": "0.05",
            "description": "integrity probe",
        }
        # Integer and code-length faults are caught by the payload schema
        # (422); a blank description reaches the service validator (400).
        # Both are rejections — the point is none of them is a 500.
        for field, bad, expected_status in (
            ("version", 0, 422),
            ("devices_per_substrate", 0, 422),
            ("code", "", 422),
            ("code", "x" * 41, 422),
            ("description", "  ", 400),
        ):
            with self.subTest(field=field, value=bad):
                payload = {**base, field: bad}
                response = self.client.post("/api/device-layouts", json=payload)
                self.assertEqual(
                    response.status_code, expected_status, response.text
                )

    def test_students_cannot_create_layouts(self) -> None:
        self._create_user("layout-student", UserRole.STUDENT, "layout student password 2026")
        self._logout()
        self._login("layout-student", "layout student password 2026")
        response = self.client.post(
            "/api/device-layouts",
            json={
                "code": "student_layout",
                "version": 1,
                "substrate_width_mm": "10",
                "substrate_length_mm": "10",
                "devices_per_substrate": 1,
                "device_active_area_cm2": "0.05",
                "total_active_area_cm2": "0.05",
                "description": "student attempt",
            },
        )
        self.assertEqual(response.status_code, 403, response.text)

    # -- Campaign creation ---------------------------------------------

    def test_admin_can_create_campaign(self) -> None:
        response = self.client.post(
            "/api/campaigns",
            json={
                "code": "SAM_mix_ADH",
                "display_name": "SAM mix ADH campaign",
                "description": "Evaluating ADH in SAM solution",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["code"], "SAM_mix_ADH")
        self.assertEqual(body["status"], "active")

    def test_instructor_can_manage_campaigns_with_json_api(self) -> None:
        self._create_user(
            "campaign-instructor",
            UserRole.INSTRUCTOR,
            "Instructor campaign password 2026",
        )
        self._logout()
        self._login(
            "campaign-instructor", "Instructor campaign password 2026"
        )

        created = self.client.post(
            "/api/campaigns",
            json={
                "code": "html-campaign",
                "display_name": "HTML Campaign",
                "description": "Created by an instructor in the browser",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["status"], "active")

        closed = self.client.patch(
            "/api/campaigns/html-campaign",
            json={"status": "closed"},
        )
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(closed.json()["status"], "closed")

    def test_student_can_open_but_not_mutate_campaign_directory(self) -> None:
        self._create_user("campaign-student", UserRole.STUDENT, "Stud3nt!pass")
        self._logout()
        self._login("campaign-student", "Stud3nt!pass")

        created = self.client.post(
            "/api/campaigns",
            json={
                "code": "student-html",
                "display_name": "Student Campaign",
                "description": "",
            },
        )
        self.assertEqual(created.status_code, 403)

    def test_duplicate_campaign_code_conflict(self) -> None:
        self.client.post(
            "/api/campaigns",
            json={"code": "dup", "display_name": "First", "description": ""},
        )
        response = self.client.post(
            "/api/campaigns",
            json={"code": "dup", "display_name": "Second", "description": ""},
        )
        self.assertEqual(response.status_code, 409)

    def test_campaign_mutation_requires_csrf(self) -> None:
        response = self.client.post(
            "/api/campaigns",
            json={"code": "no-csrf", "display_name": "No CSRF", "description": ""},
            headers={"X-CSRF-Token": ""},
        )
        self.assertEqual(response.status_code, 403)

    def test_experiment_requires_an_existing_active_campaign(self) -> None:
        missing = self.client.post(
            "/api/experiments",
            json={"campaign_id": "missing", "recipe": VALID_RECIPE},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("does not exist", missing.json()["detail"])

        self.client.post(
            "/api/campaigns",
            json={"code": "closed", "display_name": "Closed", "description": ""},
        )
        self.client.patch("/api/campaigns/closed", json={"status": "closed"})
        closed = self.client.post(
            "/api/experiments",
            json={"campaign_id": "closed", "recipe": VALID_RECIPE},
        )
        self.assertEqual(closed.status_code, 400)
        self.assertIn("not active", closed.json()["detail"])

    def test_student_cannot_create_campaign(self) -> None:
        self._create_user("stu1", UserRole.STUDENT, "Stud3nt!pass")
        self._logout()
        self._login("stu1", "Stud3nt!pass")
        response = self.client.post(
            "/api/campaigns",
            json={"code": "student-made", "display_name": "X", "description": ""},
        )
        self.assertEqual(response.status_code, 403)

    # -- Campaign listing and status -----------------------------------

    def test_student_sees_only_active_campaigns(self) -> None:
        self.client.post(
            "/api/campaigns",
            json={"code": "active1", "display_name": "Active", "description": ""},
        )
        self.client.post(
            "/api/campaigns",
            json={"code": "closed1", "display_name": "Closed", "description": ""},
        )
        self.client.patch(
            "/api/campaigns/closed1",
            json={"status": "closed"},
        )
        self._create_user("stu2", UserRole.STUDENT, "Stud3nt!pass")
        self._logout()
        self._login("stu2", "Stud3nt!pass")
        response = self.client.get("/api/campaigns")
        self.assertEqual(response.status_code, 200)
        codes = {item["code"] for item in response.json()}
        self.assertIn("active1", codes)
        self.assertNotIn("closed1", codes)

    def test_admin_sees_all_campaign_statuses(self) -> None:
        self.client.post(
            "/api/campaigns",
            json={"code": "c1", "display_name": "C1", "description": ""},
        )
        self.client.patch("/api/campaigns/c1", json={"status": "archived"})
        response = self.client.get("/api/campaigns")
        codes = {item["code"] for item in response.json()}
        self.assertIn("c1", codes)

    def test_campaign_status_transition_to_closed(self) -> None:
        self.client.post(
            "/api/campaigns",
            json={"code": "c2", "display_name": "C2", "description": ""},
        )
        response = self.client.patch(
            "/api/campaigns/c2", json={"status": "closed"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "closed")
        self.assertIsNotNone(response.json()["closed_at"])

    def test_update_nonexistent_campaign_404(self) -> None:
        response = self.client.patch(
            "/api/campaigns/bogus", json={"status": "closed"}
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_status_rejected(self) -> None:
        self.client.post(
            "/api/campaigns",
            json={"code": "c3", "display_name": "C3", "description": ""},
        )
        response = self.client.patch(
            "/api/campaigns/c3", json={"status": "bogus"}
        )
        self.assertEqual(response.status_code, 400)


class BaselineVersioningTests(unittest.TestCase):
    """Reference versioning: updates create immutable revisions."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "refs.sqlite3"
        app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(app)
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
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        asyncio.run(self.client.app.state.database.dispose())
        self.tmp.cleanup()

    def _create_reference(self, name: str = "ref1") -> dict:
        from test_web_app import complete_guided_setup
        device_recipe, deposition_process = complete_guided_setup()
        response = self.client.post(
            "/api/baselines",
            json={
                "name": name,
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_initial_reference_has_revision_1(self) -> None:
        ref = self._create_reference()
        self.assertEqual(ref["current_revision_number"], 1)
        self.assertIsNotNone(ref["canonical_hash"])

    def test_update_creates_new_revision_not_overwrite(self) -> None:
        self._create_reference("vref")
        from test_web_app import complete_guided_setup
        device_recipe, deposition_process = complete_guided_setup()
        updated = self.client.put(
            "/api/baselines/1",
            json={
                "name": "vref",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(body["current_revision_number"], 2)

    def test_old_revision_preserved_after_update(self) -> None:
        self._create_reference("href")
        from test_web_app import complete_guided_setup
        device_recipe, deposition_process = complete_guided_setup()
        self.client.put(
            "/api/baselines/1",
            json={
                "name": "href",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        versions = self.client.get("/api/baselines/1/versions").json()
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0]["revision_number"], 1)
        self.assertEqual(versions[1]["revision_number"], 2)

    def test_canonical_hash_is_deterministic(self) -> None:
        ref1 = self._create_reference("dref1")
        ref2 = self._create_reference("dref2")
        self.assertEqual(ref1["canonical_hash"], ref2["canonical_hash"])

    def test_archiving_preserves_immutable_revisions(self) -> None:
        ref = self._create_reference("archive-me")
        before = self.client.get(
            f"/api/baselines/{ref['id']}/versions"
        ).json()

        response = self.client.delete(f"/api/baselines/{ref['id']}")

        self.assertEqual(response.status_code, 204)
        archived = self.client.get(f"/api/baselines/{ref['id']}").json()
        after = self.client.get(
            f"/api/baselines/{ref['id']}/versions"
        ).json()
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(after, before)

    def test_versions_of_unknown_reference_return_404(self) -> None:
        response = self.client.get("/api/baselines/999/versions")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
