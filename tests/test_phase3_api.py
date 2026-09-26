"""Role-scoped JSON contracts required by the Phase 3 React application.

Covers the Phase 3A backend contracts:

- GET /api/results/{file_id}          (result detail with provenance)
- GET /api/results/{file_id}/assignments
- POST /api/results/{file_id}/assignments
- GET /api/fabrication-batches        (global role-scoped list)
- GET /api/results                    (global role-scoped list)
- GET /api/fabrication-batches/{batch_id}/run-sheet
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from perovskite_bo import (
    MAX_SOLID_CHEMICALS,
    MAX_SOLVENTS,
    VCD_VALVES,
    deposition_recipe_from_process,
)
from web import create_app
from web.repository import ExecutionStatus, PreparationStatus, UserRole

from tests.test_jv_parser import channel_labeled_csv, instrument_named_csv, multi_device_csv
from tests.layout_fixtures import seed_standard_layouts
from tests.test_web_app import complete_guided_setup


ADMIN_USERNAME = "phase3-admin"
ADMIN_PASSWORD = "Phase 3 administrator password 2026"
INSTRUCTOR_USERNAME = "phase3-instructor"
INSTRUCTOR_PASSWORD = "Phase 3 instructor password 2026"
OWNER_USERNAME = "phase3-owner"
OWNER_PASSWORD = "Phase 3 owner password 2026"
OTHER_USERNAME = "phase3-other"
OTHER_PASSWORD = "Phase 3 other password 2026"

RESULT_CSV = multi_device_csv(
    [-20.0, -20.0, -22.0, -18.0],
    device_labels=["A001 Channel 1", "A002 Channel 1"],
)


class Phase3ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "phase3.sqlite3"
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
        self.create_user(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD, UserRole.INSTRUCTOR)
        seed_standard_layouts(self.client)
        self.owner_id = self._user_id(OWNER_USERNAME)
        self.other_id = self._user_id(OTHER_USERNAME)
        self.instructor_id = self._user_id(INSTRUCTOR_USERNAME)
        instructor_record = asyncio.run(
            self.app.state.repository.get_user_by_username(INSTRUCTOR_USERNAME)
        )
        self.assertIsNotNone(instructor_record)
        self.assertEqual(instructor_record.role, UserRole.INSTRUCTOR)

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

    def _create_released_experiment(
        self,
        username: str,
        password: str,
        code: str,
        device_layout_code: str = "15x15_dual_005",
    ) -> int:
        """Create an owner-scoped experiment with explicit conditions and release it.

        The baseline is created by the administrator; the experiment is created and
        released by the named actor (a student), so ownership semantics hold.
        """
        device_recipe, deposition_process = complete_guided_setup()
        if device_layout_code.startswith("25x25"):
            device_recipe["substrate"].update(
                {"width_mm": 25.0, "length_mm": 25.0, "type_number": "ITO-25"}
            )
        for group in device_recipe["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [dict(layer) for layer in device_recipe["layers"]]
                group["deposition_process"] = json.loads(json.dumps(deposition_process))
        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        baseline = self.client.post(
            "/api/baselines",
            json={
                "name": f"Phase 3 baseline {code}",
                "device_recipe": deepcopy(device_recipe),
                "deposition_process": deepcopy(deposition_process),
            },
        )
        self.assertEqual(baseline.status_code, 201, baseline.text)
        self.logout()
        self.login(username, password)
        experiment = self.client.post(
            "/api/experiments",
            json={
                "recipe": {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                },
                "source_baseline_version_id": baseline.json()["current_version_id"],
                "condition_plans": [
                    {
                        "group_id": group["group_id"],
                        "role": group["kind"],
                        "device_layout_code": device_layout_code,
                        "planned_substrate_count": 3,
                    }
                    for group in device_recipe["experimental_groups"]
                ],
            },
        )
        self.assertEqual(experiment.status_code, 201, experiment.text)
        experiment_id = int(experiment.json()["id"])
        submitted = self.client.patch(
            f"/api/experiments/{experiment_id}/plan-status",
            json={"status": "pending_approval"},
        )
        self.assertEqual(submitted.status_code, 204, submitted.text)
        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        approved = self.client.patch(
            f"/api/experiments/{experiment_id}/plan-status",
            json={"status": "approved"},
        )
        self.assertEqual(approved.status_code, 204, approved.text)
        released = self.client.patch(
            f"/api/experiments/{experiment_id}/plan-status",
            json={"status": "released"},
        )
        self.assertEqual(released.status_code, 204, released.text)
        return experiment_id

    def _create_owner_batch(self, experiment_id: int) -> int:
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        created = self.client.post(
            f"/api/experiments/{experiment_id}/fabrication-batches",
            json={"notes": "Phase 3 test batch"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = int(created.json()["id"])
        ready = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={"status": "ready"},
        )
        self.assertEqual(ready.status_code, 204, ready.text)
        in_progress = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={"status": "in_progress"},
        )
        self.assertEqual(in_progress.status_code, 204, in_progress.text)
        return batch_id

    def _create_completed_owner_batch(self, experiment_id: int) -> int:
        """Create a batch, drive it fully to completed (recording actual
        substrate counts and shortfall deviations), so result-CSV assignment
        can proceed (completion is a prerequisite for assignment)."""
        batch_id = self._create_owner_batch(experiment_id)
        import asyncio
        repo = self.app.state.repository
        for preparation in asyncio.run(repo.list_solution_preparations(batch_id)):
            asyncio.run(
                repo.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(repo.list_process_executions(batch_id)):
            asyncio.run(
                repo.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        conditions = asyncio.run(repo.get_fabrication_batch_conditions(batch_id))
        # The phase3 test CSV parses one substrate per condition (control and
        # target), so record actual = 1 per condition with an embedded
        # shortfall_deviation for the 2-substrate shortfall vs the 3 planned.
        actual_counts = {}
        shortfall_deviations = []
        for condition in conditions:
            actual_counts[str(condition.id)] = 1
            shortfall_deviations.append({
                "condition_id": condition.id,
                "description": (
                    "Test setup: only one substrate per condition was "
                    "measured; the remaining planned substrates were not made."
                ),
            })
        completed = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={
                "status": "completed",
                "actual_substrate_counts": actual_counts,
                "shortfall_deviations": shortfall_deviations,
            },
        )
        self.assertEqual(completed.status_code, 204, completed.text)
        return batch_id

    def _upload_result(self, experiment_id: int, batch_id: int) -> int:
        response = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "phase3_iv.csv",
                    RESULT_CSV.encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return int(response.json()["id"])

    def _owner_batch_and_result(self) -> tuple[int, int, int]:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        file_id = self._upload_result(experiment_id, batch_id)
        return experiment_id, batch_id, file_id

    # ------------------------------------------------------------------
    # GET /api/results/{file_id}
    # ------------------------------------------------------------------

    def _attempt_result_upload(self, experiment_id: int, batch_id: int):
        return self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "phase3_iv.csv",
                    RESULT_CSV.encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )

    def test_result_upload_rejects_another_students_batch(self) -> None:
        """A student may not attach another student's batch: the upload is
        rejected with 404 — before the file is read or parsed — and the
        response is indistinguishable from a nonexistent batch."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        owner_batch_id = self._create_owner_batch(experiment_id)
        # Another student now tries to upload onto their own experiment
        # using the owner's batch id.
        other_experiment_id = self._create_released_experiment(
            OTHER_USERNAME, OTHER_PASSWORD, "phase3-other"
        )
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        rejected = self._attempt_result_upload(other_experiment_id, owner_batch_id)

        self.assertEqual(rejected.status_code, 404, rejected.text)
        # Byte-identical response as a nonexistent batch: no existence leak.
        missing = self._attempt_result_upload(other_experiment_id, 999999)
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(rejected.json(), missing.json())
        # No result row was created.
        results = self.client.get(
            f"/api/results?experiment_id={other_experiment_id}"
        ).json()
        self.assertEqual(results, [])

    def test_result_upload_rejects_mismatched_batch_before_parsing(self) -> None:
        """The batch must belong to the target experiment: an otherwise
        accessible batch from a different experiment is rejected with 404
        before any CSV parsing or area resolution."""
        # Two experiments, both owned by OWNER (so access is granted and the
        # mismatch is the only reason for rejection).
        first_experiment = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        second_experiment = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner-2"
        )
        first_batch = self._create_owner_batch(first_experiment)

        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        rejected = self._attempt_result_upload(second_experiment, first_batch)

        self.assertEqual(rejected.status_code, 404, rejected.text)
        # Same fixed body as the other rejection paths (no way to tell an
        # existing-but-mismatched batch from a missing one).
        self.assertEqual(rejected.json(), {"detail": "fabrication batch not found"})
        results = self.client.get(
            f"/api/results?experiment_id={second_experiment}"
        ).json()
        self.assertEqual(results, [])

    def test_result_upload_accepts_own_batch_total_current(self) -> None:
        """The authorized happy path keeps working end to end, including the
        total-current conversion that depends on the batch's device area."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        batch_id = self._create_owner_batch(experiment_id)
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        accepted = self._attempt_result_upload(experiment_id, batch_id)
        self.assertEqual(accepted.status_code, 201, accepted.text)
        self.assertEqual(accepted.json()["experiment_id"], experiment_id)
        self.assertEqual(accepted.json()["fabrication_batch_id"], batch_id)

    def test_result_detail_requires_login(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        response = self.client.get(f"/api/results/{file_id}")
        self.assertEqual(response.status_code, 401, response.text)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Matplotlib is not installed")
    def test_result_figure_returns_authenticated_publication_formats(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        detail = self.client.get(f"/api/results/{file_id}").json()
        device_id = detail["analysis"]["devices"][0]["device_id"]
        payload, _, _ = self._assignment_payload(file_id)
        assigned = self.client.post(f"/api/results/{file_id}/assignments", json=payload)
        self.assertEqual(assigned.status_code, 200, assigned.text)
        svg = self.client.get(
            f"/api/results/{file_id}/figures/jv",
            params=[("format", "svg"), ("device_id", device_id)],
        )
        self.assertEqual(svg.status_code, 200, svg.text)
        self.assertEqual(svg.headers["content-type"], "image/svg+xml")
        self.assertIn(b"<svg", svg.content[:1000])
        self.assertTrue(svg.headers["content-disposition"].startswith("inline"))
        self.assertIn("no-store", svg.headers["cache-control"])
        compressed = self.client.get(
            f"/api/results/{file_id}/figures/jv",
            params={"format": "svg"},
            headers={"accept-encoding": "gzip"},
        )
        self.assertEqual(compressed.status_code, 200, compressed.text)
        self.assertEqual(compressed.headers["content-encoding"], "gzip")
        self.assertIn(b"<svg", compressed.content[:1000])

        tiff = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"format": "tiff", "metric": "pce", "download": "true"},
        )
        self.assertEqual(tiff.status_code, 200, tiff.text)
        self.assertEqual(tiff.headers["content-type"], "image/tiff")
        self.assertTrue(tiff.headers["content-disposition"].startswith("attachment"))

        forward = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "pce", "direction": "forward"},
        )
        reverse = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "pce", "direction": "reverse"},
        )
        self.assertEqual(forward.status_code, 200, forward.text)
        self.assertEqual(reverse.status_code, 200, reverse.text)
        self.assertIn(b"Forward", forward.content)
        self.assertIn(b"Reverse", reverse.content)
        self.assertNotEqual(forward.content, reverse.content)
        custom_scale = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "voc", "scale_min": 1.0, "scale_max": 1.15, "threshold": 1.10},
        )
        self.assertEqual(custom_scale.status_code, 200, custom_scale.text)
        self.assertIn(b"Problem threshold: 1.100 V", custom_scale.content)
        invalid_scale = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "voc", "scale_min": 1.15, "scale_max": 1.0},
        )
        self.assertEqual(invalid_scale.status_code, 400, invalid_scale.text)
        rainbow = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "pce", "palette": "rainbow"},
        )
        self.assertEqual(rainbow.status_code, 200, rainbow.text)
        self.assertNotEqual(forward.content, rainbow.content)
        unknown_palette = self.client.get(
            f"/api/results/{file_id}/figures/uniformity",
            params={"metric": "pce", "palette": "unknown"},
        )
        self.assertEqual(unknown_palette.status_code, 400, unknown_palette.text)

        preview = self.client.get(
            f"/api/results/{file_id}/figures/boxplot",
            params={
                "format": "svg",
                "metric": "pce",
                "preview_exclusions": "true",
                "excluded_device_id": device_id,
            },
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.content.count(b"n=1"), 2)

        restored = self.client.get(
            f"/api/results/{file_id}/figures/boxplot",
            params={"format": "svg", "metric": "pce", "preview_exclusions": "true"},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.content.count(b"n=1"), 4)

        self.logout()
        denied = self.client.get(
            f"/api/results/{file_id}/figures/jv",
            params=[("device_id", device_id)],
        )
        self.assertEqual(denied.status_code, 401, denied.text)

    def test_instrument_names_are_manually_assigned_without_physical_mark(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-instrument-names"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        content = multi_device_csv(
            [-20.0, -20.0, -22.0, -18.0],
            device_labels=["A001 Channel 1", "A002 Channel 1"],
        )
        for mark, name in (("A001", "T1-1-1"), ("A002", "Control-2-1")):
            for direction in ("Forward", "Reverse"):
                content = content.replace(
                    f"{mark} Channel 1.{direction}",
                    f"18-1 3 ({name}.CH_Ref.{direction}(1))",
                )
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": ("instrument.csv", content.encode(), "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        self.assertEqual(
            [row["substrate_id"] for row in detail["analysis"]["substrates"]],
            ["T1-1", "Control-2"],
        )
        control_id = next(g["batch_condition_id"] for g in detail["groups"] if g["kind"] == "control")
        target_id = next(g["batch_condition_id"] for g in detail["groups"] if g["kind"] == "target")
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={"assignments": [
                {"analysis_substrate_id": "T1-1", "batch_condition_id": control_id},
                {"analysis_substrate_id": "Control-2", "batch_condition_id": target_id},
            ]},
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(
            {row["substrate_id"]: row["group_id"] for row in assigned.json()["analysis"]["substrates"]},
            {"T1-1": str(control_id), "Control-2": str(target_id)},
        )
        rows = self._assignment_rows(file_id)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["fabrication_device_id"] is None for row in rows))
        self.assertTrue(all(mark is None for mark in self._batch_substrate_marks(batch_id)))

    def test_result_detail_returns_complete_provenance_and_groups(self) -> None:
        experiment_id, batch_id, file_id = self._owner_batch_and_result()
        response = self.client.get(f"/api/results/{file_id}")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["id"], file_id)
        self.assertEqual(body["experiment_id"], experiment_id)
        self.assertEqual(body["fabrication_batch_id"], batch_id)
        self.assertEqual(body["filename"], "phase3_iv.csv")
        self.assertEqual(body["content_type"], "text/csv")
        self.assertGreater(body["size_bytes"], 0)
        self.assertEqual(len(body["sha256"]), 64)
        self.assertEqual(body["group_assignment"], "")
        self.assertLessEqual({"voc", "jsc", "ff", "pce"}, set(body["metrics"]))
        self.assertEqual(body["analysis"]["schema_version"], 7)
        self.assertEqual(len(body["analysis"]["devices"]), 2)
        self.assertEqual(len(body["analysis"]["substrates"]), 2)
        self.assertEqual(body["analysis_schema_version"], 7)
        # v7 stores no aggregate summaries in the analysis JSON.
        self.assertNotIn("summary", body["analysis"])
        # New acquisition fields survive database storage and the detail API.
        trace = body["analysis"]["devices"][0]["traces"][0]
        self.assertEqual(trace["raw_data"]["units"], ["V", "mA", "mA/cm^2"])
        self.assertEqual(len(trace["raw_data"]["points"]), len(trace["points"]))
        self.assertTrue(any(row["label"] == "Name" for row in trace["metadata_rows"]))
        self.assertEqual(body["created_by_id"], self.owner_id)
        self.assertEqual(body["created_at"], str(body["created_at"]))
        self.assertEqual(len(body["groups"]), 2)
        self.assertEqual(
            {group["kind"] for group in body["groups"]},
            {"control", "target"},
        )
        for group in body["groups"]:
            self.assertEqual(group["group_id"], str(group["batch_condition_id"]))
            self.assertTrue(group["condition_code"])
        self.assertEqual(body["assignments"], [])

    def test_result_detail_hides_another_students_result(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)

        detail = self.client.get(f"/api/results/{file_id}")
        assignments = self.client.get(f"/api/results/{file_id}/assignments")
        respond = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": "sample-1.forward",
                        "batch_condition_id": 1,
                    }
                ]
            },
        )
        self.assertEqual(detail.status_code, 404, detail.text)
        self.assertEqual(assignments.status_code, 404, assignments.text)
        self.assertEqual(respond.status_code, 404, respond.text)

    def test_result_assignments_require_login(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        payload, _, _ = self._assignment_payload(file_id)
        self.logout()

        read = self.client.get(f"/api/results/{file_id}/assignments")
        write = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        self.assertEqual(read.status_code, 401, read.text)
        self.assertEqual(write.status_code, 401, write.text)

    def test_instructor_can_assign_a_students_result(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)

        detail = self.client.get(f"/api/results/{file_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        payload, _, _ = self._assignment_payload(file_id)
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertTrue(assigned.json()["analysis"]["statistics"]["groups"])
        self.assertEqual(len(assigned.json()["assignments"]), 2)

    def _long_device_label_csv(
        self, label: str, trace_order: tuple[int, ...] = (1, 2)
    ) -> bytes:
        rows = [[], [], [], [], []]
        for trace_index in trace_order:
            rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
            rows[1].extend(
                [
                    "[Information]",
                    "",
                    "[Volt (V)]",
                    "[Current (mA)]",
                    "[J (mA/cm^2)]",
                    "",
                    "",
                ]
            )
            rows[2].extend(["Name", label, "0", "-2", "20", "", ""])
            rows[3].extend(["", "", "0.5", "-2", "20", "", ""])
            rows[4].extend(["", "", "1", "0", "0", "", ""])
        return ("\n".join(",".join(row) for row in rows) + "\n").encode("utf-8")

    def test_assignment_writes_back_laser_mark(self) -> None:
        """A laser-mark substrate ID is accepted and written back to the
        database substrate. Non-laser-mark IDs are rejected under the unified
        laser-mark rule."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-long"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "laser_mark.csv",
                    self._long_device_label_csv("A001 Channel 1"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        substrate_id = str(detail["analysis"]["substrates"][0]["substrate_id"])
        self.assertEqual(substrate_id, "A001")
        control_id = next(
            group["batch_condition_id"]
            for group in detail["groups"]
            if group["kind"] == "control"
        )
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertTrue(assigned.json()["analysis"]["statistics"]["groups"])
        # The laser mark is written back to the database substrate.
        import asyncio
        repo = self.app.state.repository
        substrates = asyncio.run(repo.get_fabrication_substrates_for_batch(batch_id))
        written = [s.substrate_mark for s in substrates if s.substrate_mark == "A001"]
        self.assertEqual(len(written), 1, f"laser mark not written back: {substrates}")

    def test_corrects_saved_laser_mark_assignment_with_reason(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-mark-correction"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": (
                "marked.csv", self._long_device_label_csv("A001 Channel 1"), "text/csv"
            )},
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        control_id = next(group["batch_condition_id"] for group in detail["groups"] if group["kind"] == "control")
        target_id = next(group["batch_condition_id"] for group in detail["groups"] if group["kind"] == "target")
        def assign(condition_id: int, reason: str | None = None):
            payload = {"assignments": [{"analysis_substrate_id": "A001", "batch_condition_id": condition_id}]}
            if reason:
                payload["correction_reason"] = reason
            return self.client.post(f"/api/results/{file_id}/assignments", json=payload)

        first = assign(control_id)
        self.assertEqual(first.status_code, 200, first.text)
        corrected = assign(target_id, "Corrected laboratory condition log")
        self.assertEqual(corrected.status_code, 200, corrected.text)
        self.assertEqual(corrected.json()["analysis"]["substrates"][0]["batch_condition_id"], target_id)
        substrates = asyncio.run(self.app.state.repository.get_fabrication_substrates_for_batch(batch_id))
        marked = [substrate for substrate in substrates if substrate.substrate_mark == "A001"]
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0].batch_condition_id, target_id)

    def test_rejects_laser_mark_already_associated_with_another_condition(self) -> None:
        """A laser mark already bound to a condition substrate cannot be
        associated with a different condition's substrate (one glass mark maps
        to exactly one database substrate within a batch)."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-collide"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)

        def upload(name: str) -> int:
            uploaded = self.client.post(
                f"/api/experiments/{experiment_id}/results",
                files={
                    "result_file": (name, self._long_device_label_csv("A001 Channel 1"), "text/csv")
                },
                data={"fabrication_batch_id": str(batch_id)},
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            return int(uploaded.json()["id"])

        def assign(file_id: int, substrate_id: str, condition_id: int):
            return self.client.post(
                f"/api/results/{file_id}/assignments",
                json={
                    "assignments": [
                        {
                            "analysis_substrate_id": substrate_id,
                            "batch_condition_id": condition_id,
                        }
                    ]
                },
            )

        first_id = upload("first.csv")
        detail = self.client.get(f"/api/results/{first_id}").json()
        substrate_id = str(detail["analysis"]["substrates"][0]["substrate_id"])
        control_id = next(
            group["batch_condition_id"]
            for group in detail["groups"]
            if group["kind"] == "control"
        )
        target_id = next(
            group["batch_condition_id"]
            for group in detail["groups"]
            if group["kind"] == "target"
        )

        first_assign = assign(first_id, substrate_id, control_id)
        self.assertEqual(first_assign.status_code, 200, first_assign.text)

        # second.csv swaps the two A001 traces so the bytes differ (the upload
        # guard rejects a resubmission of identical content) while the laser
        # mark stays the same.
        second_id = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "second.csv",
                    self._long_device_label_csv("A001 Channel 1", trace_order=(2, 1)),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(second_id.status_code, 201, second_id.text)
        second_id = int(second_id.json()["id"])
        detail2 = self.client.get(f"/api/results/{second_id}").json()
        substrate_id_2 = str(detail2["analysis"]["substrates"][0]["substrate_id"])
        self.assertEqual(substrate_id_2, "A001")
        collided = assign(second_id, substrate_id_2, target_id)
        self.assertEqual(collided.status_code, 400, collided.text)
        self.assertIn("already associated", collided.text)

    def _upload_channel_result(
        self, experiment_id: int, batch_id: int, filename: str, content: bytes
    ) -> tuple[int, str]:
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": (filename, content, "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        control_id = next(
            group["batch_condition_id"]
            for group in detail["groups"]
            if group["kind"] == "control"
        )
        return file_id, control_id

    def _batch_substrate_marks(self, batch_id: int) -> list[str | None]:
        repo = self.app.state.repository
        substrates = asyncio.run(repo.get_fabrication_substrates_for_batch(batch_id))
        return [substrate.substrate_mark for substrate in substrates]

    def _assignment_rows(self, file_id: int) -> list[dict]:
        repo = self.app.state.repository
        return asyncio.run(repo.list_result_device_assignments(file_id))

    def test_partial_channel_csv_binds_to_matching_device_ordinals(self) -> None:
        """Channels 2 and 5 of one substrate bind to database devices with
        device_ordinal 2 and 5, never to the first two devices encountered."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME,
            OWNER_PASSWORD,
            "phase3-channel",
            device_layout_code="25x25_six_010",
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        file_id, control_id = self._upload_channel_result(
            experiment_id,
            batch_id,
            "partial-channels.csv",
            channel_labeled_csv("A001", [2, 5]).encode("utf-8"),
        )
        detail = self.client.get(f"/api/results/{file_id}").json()
        substrate_id = str(detail["analysis"]["substrates"][0]["substrate_id"])
        self.assertEqual(substrate_id, "A001")

        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        rows = self._assignment_rows(file_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["device_code"][-3:] for row in rows}, {"D02", "D05"},
            f"channels must bind to layout ordinals 2 and 5: {rows}",
        )

    def test_rejects_simple_csv_without_physical_filename(self) -> None:
        """A simple (non-multi-device) CSV whose filename lacks a physical
        laser mark and channel is rejected at upload, before any result
        file is created."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-placeholder"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "simple.csv",
                    b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n",
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 400, uploaded.text)
        self.assertIn("exactly one substrate laser mark", uploaded.text)

    def test_rejects_missing_channel_in_instrument_label(self) -> None:
        """A device label without a channel number is ambiguous and must be
        rejected at upload, before any result file is created."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-nochannel"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "missing-channel.csv",
                    multi_device_csv(
                        [20.0, 20.0, 21.0, 21.0], device_labels=["A001 Channel 2", "A001"]
                    ).encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 400, uploaded.text)
        self.assertIn("channel", uploaded.text)

    def test_rejects_out_of_layout_channel_ordinal(self) -> None:
        """Channel 5 on a two-device layout has no matching database device.
        The upload succeeds (the CSV is well-formed); the assignment is rejected."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-outlayout"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        file_id, control_id = self._upload_channel_result(
            experiment_id,
            batch_id,
            "out-of-layout.csv",
            channel_labeled_csv("A001", [5]).encode("utf-8"),
        )
        detail = self.client.get(f"/api/results/{file_id}").json()
        substrate_id = str(detail["analysis"]["substrates"][0]["substrate_id"])

        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 400, assigned.text)
        self.assertIn("5", assigned.text)
        self.assertEqual(self._assignment_rows(file_id), [])
        self.assertTrue(
            all(mark is None for mark in self._batch_substrate_marks(batch_id))
        )

    def test_rejects_duplicate_channel_ordinal_within_substrate(self) -> None:
        """Two distinct labels resolving to the same channel are a duplicate
        physical device and must be rejected at upload, before any result
        file is created."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME,
            OWNER_PASSWORD,
            "phase3-dupchannel",
            device_layout_code="25x25_six_010",
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "duplicate-channel.csv",
                    multi_device_csv(
                        [20.0, 20.0, 21.0, 21.0],
                        device_labels=["A001 Channel 2", "A001 channel 02"],
                    ).encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 400, uploaded.text)
        self.assertIn("duplicate", uploaded.text.lower())

    def test_extra_substrates_can_receive_result_assignments(self) -> None:
        """Substrates materialized by an actual>planned completion can later
        receive result-CSV assignments (the old code dead-ended here)."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-extra"
        )
        batch_id = self._create_owner_batch(experiment_id)
        repo = self.app.state.repository
        for preparation in asyncio.run(repo.list_solution_preparations(batch_id)):
            asyncio.run(
                repo.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(repo.list_process_executions(batch_id)):
            asyncio.run(
                repo.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        conditions = asyncio.run(repo.get_fabrication_batch_conditions(batch_id))
        completed = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={
                "status": "completed",
                "actual_substrate_counts": {
                    str(condition.id): 5 for condition in conditions
                },
            },
        )
        self.assertEqual(completed.status_code, 204, completed.text)

        uploaded = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={
                "result_file": (
                    "five-extra.csv",
                    multi_device_csv(
                        [
                            -20.0, -20.0,
                            -21.0, -21.0,
                            -22.0, -22.0,
                            -23.0, -23.0,
                            -24.0, -24.0,
                        ],
                        device_labels=[
                            "A001 Channel 1",
                            "A002 Channel 1",
                            "A003 Channel 1",
                            "A004 Channel 1",
                            "A005 Channel 1",
                        ],
                    ).encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        substrate_ids = [
            str(substrate["substrate_id"])
            for substrate in detail["analysis"]["substrates"]
        ]
        self.assertEqual(
            substrate_ids, ["A001", "A002", "A003", "A004", "A005"]
        )
        control_id = next(
            group["batch_condition_id"]
            for group in detail["groups"]
            if group["kind"] == "control"
        )

        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                    for substrate_id in substrate_ids
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(len(assigned.json()["assignments"]), 5)
        marks = sorted(
            mark
            for mark in self._batch_substrate_marks(batch_id)
            if mark is not None
        )
        self.assertEqual(marks, ["A001", "A002", "A003", "A004", "A005"])

    def test_measurement_shortfall_gate_on_csv_assignment(self) -> None:
        """A CSV that measures fewer substrates than were made requires a
        measurement_shortfall deviation targeted at that condition; general or
        absent deviations do not unlock it."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-measgate"
        )
        batch_id = self._create_owner_batch(experiment_id)
        repo = self.app.state.repository
        for preparation in asyncio.run(repo.list_solution_preparations(batch_id)):
            asyncio.run(
                repo.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(repo.list_process_executions(batch_id)):
            asyncio.run(
                repo.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        conditions = asyncio.run(repo.get_fabrication_batch_conditions(batch_id))
        # Complete with actual = 2 per condition (embedded fabrication
        # shortfall), so a one-substrate CSV is a measurement shortfall.
        completed = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={
                "status": "completed",
                "actual_substrate_counts": {
                    str(condition.id): 2 for condition in conditions
                },
                "shortfall_deviations": [
                    {
                        "condition_id": condition.id,
                        "description": f"{condition.condition_name} made two substrates.",
                    }
                    for condition in conditions
                ],
            },
        )
        self.assertEqual(completed.status_code, 204, completed.text)

        def upload_and_assign() -> tuple[int, str, int]:
            uploaded = self.client.post(
                f"/api/experiments/{experiment_id}/results",
                files={
                    "result_file": (
                        "one-substrate.csv",
                        multi_device_csv(
                            [-20.0, -20.0], device_labels=["A001 Channel 1"]
                        ).encode("utf-8"),
                        "text/csv",
                    )
                },
                data={"fabrication_batch_id": str(batch_id)},
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            file_id = int(uploaded.json()["id"])
            detail = self.client.get(f"/api/results/{file_id}").json()
            substrate_id = str(detail["analysis"]["substrates"][0]["substrate_id"])
            control_id = next(
                group["batch_condition_id"]
                for group in detail["groups"]
                if group["kind"] == "control"
            )
            return file_id, substrate_id, control_id

        # No deviation: rejected.
        file_id, substrate_id, control_id = upload_and_assign()
        rejected = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("measurement_shortfall", rejected.text)

        # A general condition deviation does not unlock the gate.
        declared = self.client.post(
            f"/api/fabrication-batches/{batch_id}/deviations",
            json={
                "category": "operator",
                "severity": "info",
                "description": "General note, not a measurement declaration.",
                "condition_id": control_id,
            },
        )
        self.assertEqual(declared.status_code, 201, declared.text)
        still_rejected = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(still_rejected.status_code, 400, still_rejected.text)
        self.assertIn("measurement_shortfall", still_rejected.text)

        # A typed measurement shortfall targeted at the condition unlocks it.
        measured = self.client.post(
            f"/api/fabrication-batches/{batch_id}/deviations",
            json={
                "category": "substrate",
                "severity": "warning",
                "description": "Second substrate was not measured.",
                "condition_id": control_id,
                "deviation_type": "measurement_shortfall",
            },
        )
        self.assertEqual(measured.status_code, 201, measured.text)
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": substrate_id,
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

    def test_deviation_rejects_condition_combined_with_other_targets(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-targets"
        )
        batch_id = self._create_owner_batch(experiment_id)
        repo = self.app.state.repository
        conditions = asyncio.run(repo.get_fabrication_batch_conditions(batch_id))
        control_id = next(c.id for c in conditions if c.role == "control")
        substrate_id = asyncio.run(
            repo.get_fabrication_substrates_for_batch(batch_id)
        )[0].id

        rejected = self.client.post(
            f"/api/fabrication-batches/{batch_id}/deviations",
            json={
                "category": "substrate",
                "severity": "warning",
                "description": "Invalid multi-target deviation",
                "condition_id": control_id,
                "substrate_id": substrate_id,
            },
        )
        self.assertIn(rejected.status_code, (400, 422), rejected.text)
        self.assertIn("one specific", rejected.text)

    def test_repository_rejects_nonpositive_device_ordinals(self) -> None:
        """Crafted analyses with zero/negative/missing device ordinals are
        rejected by the repository layer itself (defense against any caller)."""
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-badordinal"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        file_id, control_id = self._upload_channel_result(
            experiment_id,
            batch_id,
            "bad-ordinal.csv",
            channel_labeled_csv("A001", [1]).encode("utf-8"),
        )
        detail = self.client.get(f"/api/results/{file_id}").json()
        base_analysis = detail["analysis"]
        repo = self.app.state.repository

        for bad_ordinal in (0, -3, None):
            with self.subTest(device_ordinal=bad_ordinal):
                mutated = deepcopy(base_analysis)
                mutated["devices"][0]["device_ordinal"] = bad_ordinal
                with self.assertRaisesRegex(ValueError, "channel"):
                    asyncio.run(
                        repo.update_result_analysis_and_complete(
                            file_id,
                            mutated,
                            substrate_assignments={"A001": control_id},
                            group_assignment="bad ordinal test",
                            actor_user_id=1,
                        )
                    )
        self.assertEqual(self._assignment_rows(file_id), [])
        self.assertTrue(
            all(mark is None for mark in self._batch_substrate_marks(batch_id))
        )


    def test_instructor_can_read_any_result_detail(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        self.login(INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD)

        response = self.client.get(f"/api/results/{file_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["created_by_id"], self.owner_id)

    def test_administrator_can_read_any_result_detail(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)

        response = self.client.get(f"/api/results/{file_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["created_by_id"], self.owner_id)

    def test_experiment_detail_results_list_still_works_with_created_by_id(self) -> None:
        experiment_id, _, file_id = self._owner_batch_and_result()
        response = self.client.get(f"/api/experiments/{experiment_id}")

        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()["results"]
        self.assertEqual([row["id"] for row in results], [file_id])
        self.assertEqual(results[0]["filename"], "phase3_iv.csv")
        self.assertEqual(len(results[0]["sha256"]), 64)

    # ------------------------------------------------------------------
    # POST /api/results/{file_id}/assignments
    # ------------------------------------------------------------------

    def _assignment_payload(self, file_id: int) -> tuple[dict, str, str]:
        detail = self.client.get(f"/api/results/{file_id}").json()
        groups = detail["groups"]
        control_id = next(
            group["batch_condition_id"] for group in groups if group["kind"] == "control"
        )
        target_id = next(
            group["batch_condition_id"] for group in groups if group["kind"] == "target"
        )
        substrates = [
            str(substrate["substrate_id"])
            for substrate in detail["analysis"]["substrates"]
        ]
        payload = {
            "assignments": [
                {"analysis_substrate_id": substrates[0], "batch_condition_id": control_id},
                {"analysis_substrate_id": substrates[1], "batch_condition_id": target_id},
            ]
        }
        return payload, substrates[0], substrates[1]

    def test_assignment_post_requires_csrf(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        payload, _, _ = self._assignment_payload(file_id)
        self.client.headers.pop("X-CSRF-Token", None)

        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_assignment_rejects_duplicate_substrate(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        payload, substrate_id, _ = self._assignment_payload(file_id)
        duplicate = payload["assignments"][0]
        payload["assignments"].append(
            {"analysis_substrate_id": substrate_id, "batch_condition_id": duplicate["batch_condition_id"]}
        )

        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("duplicate", response.json()["detail"])

    def test_reassignment_requires_reason_and_audits_old_and_new_conditions(self) -> None:
        from sqlalchemy import select
        from web.database import audit_events

        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-correction"
        )
        batch_id = self._create_completed_owner_batch(experiment_id)
        upload = self.client.post(
            f"/api/experiments/{experiment_id}/results",
            files={"result_file": ("instrument-names.csv", instrument_named_csv(
                ["Control1", "Target1"], [1],
            ).encode("utf-8"), "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        file_id = int(upload.json()["id"])
        payload, substrate_id, _ = self._assignment_payload(file_id)
        initial = self.client.post(f"/api/results/{file_id}/assignments", json=payload)
        self.assertEqual(initial.status_code, 200, initial.text)
        old_condition = payload["assignments"][0]["batch_condition_id"]
        new_condition = payload["assignments"][1]["batch_condition_id"]
        payload["assignments"][0]["batch_condition_id"] = new_condition
        payload["assignments"][1]["batch_condition_id"] = old_condition
        rejected = self.client.post(f"/api/results/{file_id}/assignments", json=payload)
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("correction reason", rejected.json()["detail"])

        payload["correction_reason"] = "Corrected mislabeled substrate"
        corrected = self.client.post(f"/api/results/{file_id}/assignments", json=payload)
        self.assertEqual(corrected.status_code, 200, corrected.text)

        async def audit_details():
            async with self.app.state.database.begin() as connection:
                return (await connection.execute(select(audit_events.c.details).where(
                    audit_events.c.action == "result.assign_groups",
                    audit_events.c.entity_id == str(file_id),
                ).order_by(audit_events.c.id.desc()).limit(1))).scalar_one()

        details = asyncio.run(audit_details())
        self.assertEqual(details["correction_reason"], "Corrected mislabeled substrate")
        self.assertIn({"analysis_substrate_id": substrate_id,
                       "from_batch_condition_id": old_condition,
                       "to_batch_condition_id": new_condition}, details["assignment_changes"])

    def test_assignment_rejects_missing_substrate(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        payload, _, _ = self._assignment_payload(file_id)
        self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        # A result with no assignments yet; submit only one of two substrates.
        detail = self.client.get(f"/api/results/{file_id}").json()
        groups = detail["groups"]
        control_id = next(
            group["batch_condition_id"] for group in groups if group["kind"] == "control"
        )
        substrate = detail["analysis"]["substrates"][0]["substrate_id"]
        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {"analysis_substrate_id": substrate, "batch_condition_id": control_id},
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_assignment_rejects_extra_substrate(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        payload, _, _ = self._assignment_payload(file_id)
        payload["assignments"].append(
            {"analysis_substrate_id": "nonexistent-substrate", "batch_condition_id": 1}
        )

        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_assignment_rejects_condition_from_another_batch(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        other_experiment = self._create_released_experiment(
            OTHER_USERNAME, OTHER_PASSWORD, "phase3-other"
        )
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        other_batch = self.client.post(
            f"/api/experiments/{other_experiment}/fabrication-batches",
            json={},
        )
        self.assertEqual(other_batch.status_code, 201, other_batch.text)
        other_conditions = self.client.get(
            f"/api/fabrication-batches/{other_batch.json()['id']}/conditions"
        ).json()
        foreign_condition_id = int(other_conditions[0]["id"])

        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        detail = self.client.get(f"/api/results/{file_id}").json()
        substrates = [
            str(substrate["substrate_id"])
            for substrate in detail["analysis"]["substrates"]
        ]
        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {"analysis_substrate_id": substrates[0], "batch_condition_id": foreign_condition_id},
                    {"analysis_substrate_id": substrates[1], "batch_condition_id": foreign_condition_id},
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_assignment_success_returns_complete_detail_and_persists_rows(self) -> None:
        experiment_id, batch_id, file_id = self._owner_batch_and_result()
        payload, _, _ = self._assignment_payload(file_id)

        response = self.client.post(
            f"/api/results/{file_id}/assignments",
            json=payload,
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["id"], file_id)
        self.assertEqual(body["created_by_id"], self.owner_id)
        statistics = body["analysis"]["statistics"]
        self.assertEqual(len(statistics["groups"]), 2)
        self.assertEqual(
            {group["kind"] for group in statistics["groups"]},
            {"control", "target"},
        )
        self.assertIn("substrates", body["group_assignment"])
        self.assertEqual(len(body["assignments"]), 2)
        for row in body["assignments"]:
            self.assertEqual(row["result_file_id"], file_id)
            self.assertTrue(row["condition_code"])
            # Under substrate-level association, each parsed device maps to a
            # database device by ordinal, so device_code is populated.
            self.assertTrue(row["device_code"], f"expected device_code, got {row}")
        for substrate in body["analysis"]["substrates"]:
            self.assertTrue(substrate["batch_condition_id"])
            self.assertTrue(substrate["condition_code"])
        for device in body["analysis"]["devices"]:
            self.assertTrue(device["batch_condition_id"])

        assignments = self.client.get(
            f"/api/results/{file_id}/assignments"
        )
        self.assertEqual(assignments.status_code, 200, assignments.text)
        self.assertEqual(len(assignments.json()), 2)
        self.assertEqual(
            {row["analysis_substrate_id"] for row in assignments.json()},
            {
                str(substrate["substrate_id"])
                for substrate in body["analysis"]["substrates"]
            },
        )

        experiment = self.client.get(f"/api/experiments/{experiment_id}")
        self.assertEqual(experiment.status_code, 200, experiment.text)
        self.assertEqual(experiment.json()["experiment"]["status"], "completed")
        self.assertEqual(
            experiment.json()["results"][0]["fabrication_batch_id"],
            batch_id,
        )

    # ------------------------------------------------------------------
    # GET /api/results (global list)
    # ------------------------------------------------------------------

    def test_global_result_list_requires_login(self) -> None:
        _, _, file_id = self._owner_batch_and_result()
        self.logout()
        response = self.client.get("/api/results")
        self.assertEqual(response.status_code, 401, response.text)

    def test_global_result_list_is_role_scoped(self) -> None:
        experiment_id, batch_id, file_id = self._owner_batch_and_result()
        other_experiment_id = self._create_released_experiment(
            OTHER_USERNAME, OTHER_PASSWORD, "phase3-other"
        )

        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        other_batch = self.client.post(
            f"/api/experiments/{other_experiment_id}/fabrication-batches",
            json={},
        )
        self.assertEqual(other_batch.status_code, 201, other_batch.text)
        other_batch_id = int(other_batch.json()["id"])
        self.client.patch(
            f"/api/fabrication-batches/{other_batch_id}/status",
            json={"status": "ready"},
        )
        self.client.patch(
            f"/api/fabrication-batches/{other_batch_id}/status",
            json={"status": "in_progress"},
        )
        other_file = self._upload_result(other_experiment_id, other_batch_id)
        other_list = self.client.get("/api/results").json()
        self.assertEqual([row["id"] for row in other_list], [other_file])
        self.assertEqual(other_list[0]["batch_code"], other_batch.json()["batch_code"])

        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        owner_list = self.client.get("/api/results").json()
        self.assertEqual([row["id"] for row in owner_list], [file_id])
        self.assertTrue(owner_list[0]["experiment_code"])
        self.assertTrue(owner_list[0]["batch_code"])
        self.assertNotIn("analysis", owner_list[0])
        self.assertNotIn("created_by_id", owner_list[0])

        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        admin_list = self.client.get("/api/results").json()
        self.assertEqual({row["id"] for row in admin_list}, {file_id, other_file})

    def test_global_result_list_filters(self) -> None:
        experiment_id, batch_id, file_id = self._owner_batch_and_result()
        by_experiment = self.client.get("/api/results", params={"experiment_id": experiment_id})
        self.assertEqual(by_experiment.status_code, 200, by_experiment.text)
        self.assertEqual([row["id"] for row in by_experiment.json()], [file_id])
        by_batch = self.client.get("/api/results", params={"fabrication_batch_id": batch_id})
        self.assertEqual([row["id"] for row in by_batch.json()], [file_id])
        unknown = self.client.get("/api/results", params={"fabrication_batch_id": 999999})
        self.assertEqual(unknown.status_code, 404, unknown.text)

    def test_global_result_list_query_projection_is_lightweight(self) -> None:
        """The list query must never project the analysis document or provenance id.

        Inspecting the SQLAlchemy column collection proves the SELECT shape
        directly, independent of Pydantic response-model filtering.
        """

        from web.database import result_files
        from web.repository import _result_summary_statement

        statement = _result_summary_statement(owner_user_id=None)
        selected = set(statement.selected_columns.keys())
        self.assertIn("analysis_schema_version", selected)
        self.assertNotIn("analysis", selected)
        self.assertNotIn("created_by_id", selected)
        self.assertNotIn("content", selected)

        _, _, file_id = self._owner_batch_and_result()
        records = asyncio.run(
            self.app.state.repository.list_results_for_actor(self.owner_id)
        )
        self.assertEqual([record["id"] for record in records], [file_id])
        record = records[0]
        self.assertEqual(
            set(record),
            {
                "id",
                "experiment_id",
                "experiment_code",
                "fabrication_batch_id",
                "batch_code",
                "filename",
                "content_type",
                "size_bytes",
                "sha256",
                "group_assignment",
                "metrics",
                "analysis_schema_version",
                "created_at",
            },
        )
        self.assertNotIn("analysis", record)
        self.assertNotIn("created_by_id", record)

    def test_global_result_list_filter_outside_scope_is_404(self) -> None:
        experiment_id, _, _ = self._owner_batch_and_result()
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        response = self.client.get("/api/results", params={"experiment_id": experiment_id})
        self.assertEqual(response.status_code, 404, response.text)

    # ------------------------------------------------------------------
    # GET /api/fabrication-batches (global list)
    # ------------------------------------------------------------------

    def test_global_batch_list_requires_login(self) -> None:
        self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        self.logout()
        response = self.client.get("/api/fabrication-batches")
        self.assertEqual(response.status_code, 401, response.text)

    def test_global_batch_list_is_role_scoped(self) -> None:
        owner_experiment = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        self._create_owner_batch(owner_experiment)
        other_experiment = self._create_released_experiment(
            OTHER_USERNAME, OTHER_PASSWORD, "phase3-other"
        )
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        other_batch = self.client.post(
            f"/api/experiments/{other_experiment}/fabrication-batches",
            json={},
        )
        self.assertEqual(other_batch.status_code, 201, other_batch.text)

        other_list = self.client.get("/api/fabrication-batches").json()
        self.assertEqual(
            [row["id"] for row in other_list],
            [other_batch.json()["id"]],
        )
        self.assertTrue(other_list[0]["experiment_code"])
        self.assertEqual(other_list[0]["status"], "draft")

        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)
        owner_list = self.client.get("/api/fabrication-batches").json()
        self.assertEqual(len(owner_list), 1)
        self.assertTrue(owner_list[0]["experiment_code"])

        self.logout()
        self.login(ADMIN_USERNAME, ADMIN_PASSWORD)
        admin_list = self.client.get("/api/fabrication-batches").json()
        self.assertEqual(len(admin_list), 2)

    def test_global_batch_list_status_filter(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        self._create_owner_batch(experiment_id)
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)

        in_progress = self.client.get(
            "/api/fabrication-batches",
            params={"status": "in_progress"},
        )
        self.assertEqual(in_progress.status_code, 200, in_progress.text)
        self.assertEqual(len(in_progress.json()), 1)
        draft = self.client.get(
            "/api/fabrication-batches",
            params={"status": "draft"},
        )
        self.assertEqual(draft.json(), [])

    def test_global_batch_list_experiment_filter(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        self._create_owner_batch(experiment_id)
        self.logout()
        self.login(OWNER_USERNAME, OWNER_PASSWORD)

        scoped = self.client.get(
            "/api/fabrication-batches",
            params={"experiment_id": experiment_id},
        )
        self.assertEqual(scoped.status_code, 200, scoped.text)
        self.assertEqual(len(scoped.json()), 1)
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)
        outside = self.client.get(
            "/api/fabrication-batches",
            params={"experiment_id": experiment_id},
        )
        self.assertEqual(outside.status_code, 404, outside.text)

    # ------------------------------------------------------------------
    # GET /api/fabrication-batches/{batch_id}/run-sheet
    # ------------------------------------------------------------------

    def test_run_sheet_requires_login(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        batch_id = self._create_owner_batch(experiment_id)
        self.logout()
        response = self.client.get(f"/api/fabrication-batches/{batch_id}/run-sheet")
        self.assertEqual(response.status_code, 401, response.text)

    def test_run_sheet_returns_complete_aggregate(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        batch_id = self._create_owner_batch(experiment_id)

        response = self.client.get(
            f"/api/fabrication-batches/{batch_id}/run-sheet"
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["batch"]["id"], batch_id)
        self.assertEqual(body["batch"]["status"], "in_progress")
        self.assertEqual(len(body["batch"]["condition_set_hash"]), 64)
        self.assertGreaterEqual(len(body["conditions"]), 1)
        for condition in body["conditions"]:
            self.assertEqual(condition["fabrication_batch_id"], batch_id)
            self.assertIn("recipe_snapshot", condition)
            self.assertEqual(len(condition["source_condition_hash"]), 64)
        self.assertGreaterEqual(len(body["substrates"]), 1)
        self.assertIn("substrate_code", body["substrates"][0])
        self.assertGreaterEqual(len(body["devices"]), 1)
        self.assertIn("device_code", body["devices"][0])
        self.assertTrue(body["preparations"])
        for preparation in body["preparations"]:
            self.assertEqual(len(preparation["preparation"]["planned_canonical_hash"]), 64)
            self.assertGreaterEqual(len(preparation["uses"]), 1)
            for use in preparation["uses"]:
                self.assertIn("layer_ordinal", use)
                self.assertIn("layer_snapshot_hash", use)
        self.assertTrue(body["executions"])
        for execution in body["executions"]:
            self.assertEqual(len(execution["execution"]["planned_canonical_hash"]), 64)
            self.assertGreaterEqual(len(execution["members"]), 1)
            for member in execution["members"]:
                self.assertIn("layer_ordinal", member)
        self.assertEqual(body["deviations"], [])
        self.assertEqual(body["editor_config"]["max_solid_chemicals"], MAX_SOLID_CHEMICALS)
        self.assertEqual(body["editor_config"]["max_solvents"], MAX_SOLVENTS)
        self.assertEqual(body["editor_config"]["vcd_valves"], list(VCD_VALVES))

    def test_run_sheet_hides_another_students_batch(self) -> None:
        experiment_id = self._create_released_experiment(
            OWNER_USERNAME, OWNER_PASSWORD, "phase3-owner"
        )
        batch_id = self._create_owner_batch(experiment_id)
        self.logout()
        self.login(OTHER_USERNAME, OTHER_PASSWORD)

        response = self.client.get(f"/api/fabrication-batches/{batch_id}/run-sheet")
        self.assertEqual(response.status_code, 404, response.text)

    def test_run_sheet_unknown_batch_is_404(self) -> None:
        response = self.client.get(
            "/api/fabrication-batches/999999/run-sheet"
        )
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
