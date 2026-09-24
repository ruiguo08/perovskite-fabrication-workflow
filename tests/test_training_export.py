"""Read-only (X, y) training-data extraction from the web registry.

Wires the perovskite_bo.web_adapter onto stored PostgreSQL/SQLite rows:
completed fabrication batches yield one row per frozen condition with the
recipe features, aggregated device metrics, and batch provenance.
"""

import asyncio
import contextlib
import io
import json
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from web import create_app
from web.admin_cli import parser as admin_parser, run_command
from web.jv_parser import _flat_metrics_from_analysis
from web.repository import (
    BatchStatus,
    ExecutionStatus,
    PreparationStatus,
    UserRole,
)

from tests.test_fabrication_batches import _create_released_experiment_with_conditions
from tests.test_jv_parser import channel_labeled_csv, multi_device_csv

TEST_USERNAME = "training-export-admin"
TEST_PASSWORD = "correct horse battery staple"


class TrainingExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "training.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self.repository = self.app.state.repository
        self._login()
        from tests.layout_fixtures import seed_standard_layouts

        seed_standard_layouts(self.client)
        self.experiment_id = asyncio.run(
            _create_released_experiment_with_conditions(
                self.repository, "training-export"
            )
        )

    def tearDown(self) -> None:
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _login(self) -> None:
        token = self.client.get("/api/auth/login-csrf").json()["login_csrf_token"]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": token,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def _completed_batch(self) -> int:
        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
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
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
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
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 1 for c in conditions},
                shortfall_deviations=[
                    (c.id, "Test setup: one substrate per condition.")
                    for c in conditions
                ],
                actor_user_id=1,
            )
        )
        return batch.id

    def _upload_and_assign_control(self, batch_id: int) -> tuple[int, int]:
        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001 Channel 1.csv",
                    channel_labeled_csv("A001", [1]).encode("utf-8"),
                    "text/csv",
                )
            },
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
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": "A001",
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)
        return file_id, control_id

    def test_completed_batch_yields_one_row_per_condition(self) -> None:
        batch_id = self._completed_batch()
        file_id, control_id = self._upload_and_assign_control(batch_id)

        rows = asyncio.run(
            self.repository.build_training_dataset(
                experiment_id=self.experiment_id
            )
        )

        self.assertEqual(len(rows), 2)
        by_condition = {row["batch_condition_id"]: row for row in rows}
        control = by_condition[control_id]
        self.assertEqual(control["role"], "control")
        self.assertEqual(control["experiment_id"], self.experiment_id)
        self.assertEqual(control["batch_id"], batch_id)
        self.assertIn("B01", control["batch_code"])
        self.assertEqual(control["result_file_ids"], [file_id])
        self.assertEqual(len(control["source_condition_hash"]), 64)
        # Features come from the frozen recipe snapshot in search-space order.
        from perovskite_bo.web_adapter import search_space_parameter_names

        self.assertEqual(
            tuple(control["features"].keys()), search_space_parameter_names()
        )
        self.assertIsInstance(control["features"]["spin_cast_rpm"], int)
        # Aggregated device metrics exist for the measured condition only.
        self.assertEqual(control["metrics"]["device_count"], 1)
        self.assertIsNotNone(control["metrics"]["pce"])
        target = next(
            row for row in rows if row["batch_condition_id"] != control_id
        )
        self.assertEqual(target["role"], "target")
        self.assertIsNone(target["metrics"])
        self.assertEqual(target["result_file_ids"], [])

    def test_unfinished_batches_are_excluded_unless_named(self) -> None:
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

        self.assertEqual(
            asyncio.run(self.repository.build_training_dataset()), []
        )
        explicit = asyncio.run(
            self.repository.build_training_dataset(batch_id=batch.id)
        )
        self.assertEqual(len(explicit), 2)
        self.assertTrue(all(row["metrics"] is None for row in explicit))

    def test_excluded_devices_do_not_seed_training_metrics(self) -> None:
        batch_id = self._completed_batch()
        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001 Channel 1.csv",
                    channel_labeled_csv("A001", [1, 2]).encode("utf-8"),
                    "text/csv",
                )
            },
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
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": "A001",
                        "batch_condition_id": control_id,
                    }
                ],
                "exclusions": [
                    {
                        "analysis_device_id": "device-002",
                        "reason": "Shunted device excluded before training export.",
                    }
                ],
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        rows = asyncio.run(
            self.repository.build_training_dataset(
                experiment_id=self.experiment_id
            )
        )
        control = next(
            row for row in rows if row["batch_condition_id"] == control_id
        )
        # Only the non-excluded device feeds the training target.
        self.assertEqual(control["metrics"]["device_count"], 1)
        self.assertEqual(control["excluded_device_count"], 1)

    def test_hysteresis_index_flows_into_training_export(self) -> None:
        batch_id = self._completed_batch()
        content = (
            "No.,1,,,,,,No.,2,,,,,\n"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,,"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
            "Name,A001 Channel 1.Forward,0,-2,-20,,,Name,A001 Channel 1.Reverse,0,-2,-16,,\n"
            ",,0.5,-2,-20,,,,,0.5,-2,-16,,\n"
            ",,1,0,0,,,,,1,0,0,,\n"
        )
        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001 Channel 1.csv",
                    content.encode("utf-8"),
                    "text/csv",
                )
            },
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
        assigned = self.client.post(
            f"/api/results/{file_id}/assignments",
            json={
                "assignments": [
                    {
                        "analysis_substrate_id": "A001",
                        "batch_condition_id": control_id,
                    }
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        rows = asyncio.run(
            self.repository.build_training_dataset(
                experiment_id=self.experiment_id
            )
        )
        control = next(
            row for row in rows if row["batch_condition_id"] == control_id
        )
        self.assertAlmostEqual(control["metrics"]["hysteresis_index"], -0.25)

    def test_total_current_upload_converts_with_batch_layout_area(self) -> None:
        batch_id = self._completed_batch()
        content = "voltage,current\n0.0,-1.0\n0.5,-1.0\n1.0,0.0\n"
        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001 Channel 1.csv",
                    content.encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        # 1 mA over the layout's 0.05 cm2 device area is 20 mA/cm2.
        self.assertAlmostEqual(uploaded.json()["metrics"]["jsc"], 20.0)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
        self.assertEqual(
            detail["analysis"]["unit_conversion"]["device_active_area_cm2"], 0.05
        )


class TrainingExportCliTests(TrainingExportTests):
    def _run_cli(self, *argv: str) -> str:
        args = admin_parser().parse_args(list(argv))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            asyncio.run(run_command(args, self.app.state.database))
        return output.getvalue()

    def test_cli_exports_json_lines_and_csv(self) -> None:
        batch_id = self._completed_batch()
        self._upload_and_assign_control(batch_id)

        json_output = self._run_cli(
            "export-training-data",
            "--experiment-id",
            str(self.experiment_id),
            "--format",
            "json",
        )
        lines = [line for line in json_output.splitlines() if line.strip()]
        # One self-description header plus one line per condition.
        self.assertEqual(len(lines), 3)
        records = [json.loads(line) for line in lines]
        header, rows = records[0], records[1:]
        self.assertEqual(header["record_type"], "header")
        self.assertEqual(header["export_schema_version"], 2)
        self.assertIn("units", header)
        self.assertTrue(all(row["record_type"] == "data" for row in rows))
        self.assertEqual(
            {row["batch_id"] for row in rows}, {batch_id}
        )
        measured = [r for r in rows if r["metrics"]]
        self.assertEqual(len(measured), 1)

        csv_output = self._run_cli(
            "export-training-data",
            "--experiment-id",
            str(self.experiment_id),
            "--format",
            "csv",
        )
        import csv as csv_module

        table = list(csv_module.reader(io.StringIO(csv_output)))
        self.assertEqual(len(table), 3)
        header = table[0]
        self.assertIn("batch_condition_id", header)
        self.assertIn("spin_cast_rpm", header)
        self.assertIn("pce", header)
        self.assertIn("hysteresis_index", header)
        self.assertIn("export_schema_version", header)
        self.assertEqual(table[1][header.index("batch_id")], str(batch_id))
        self.assertEqual(
            table[1][header.index("export_schema_version")], "2"
        )


    def _completed_batch_with_recorded_actuals(self, adjusted_rpm: int | None = None) -> int:
        """Complete a batch whose perovskite executions carry actual snapshots.

        Every perovskite execution is recorded as matching the plan; when
        ``adjusted_rpm`` is given, the spin-coating execution instead records
        an adjusted actual snapshot with that first-step rpm.
        """
        import json as json_module

        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
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
            if (
                execution.layer_type == "perovskite"
                and execution.method in ("spin_coating", "vcd", "annealing")
            ):
                if adjusted_rpm is not None and execution.method == "spin_coating":
                    adjusted = json_module.loads(
                        json_module.dumps(execution.planned_process_snapshot)
                    )
                    adjusted["spin_steps"][0]["rpm"] = adjusted_rpm
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_process_snapshot=adjusted,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
                else:
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_matches_planned=True,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
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
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 1 for c in conditions},
                shortfall_deviations=[
                    (c.id, "Test setup: one substrate per condition.")
                    for c in conditions
                ],
                actor_user_id=1,
            )
        )
        return batch.id

    def test_actual_execution_snapshots_drive_features(self) -> None:
        """Recorded actual snapshots — not the frozen plan — become X, so a
        condition spun at a different speed than planned exports the actual
        speed."""
        batch_id = self._completed_batch_with_recorded_actuals(adjusted_rpm=1234)
        file_id, control_id = self._upload_and_assign_control(batch_id)

        rows = asyncio.run(
            self.repository.build_training_dataset(
                experiment_id=self.experiment_id
            )
        )

        control = next(
            row for row in rows if row["batch_condition_id"] == control_id
        )
        self.assertEqual(control["feature_source"], "actual")
        self.assertEqual(control["features"]["spin_cast_rpm"], 1234)
        self.assertTrue(control["substrate_ids"])

        # A condition whose perovskite executions carry no actual snapshots
        # (cancelled blank, like the legacy helper) keeps the planned
        # features and says so.
        planned_batch_id = self._completed_batch()
        planned_rows = asyncio.run(
            self.repository.build_training_dataset(batch_id=planned_batch_id)
        )
        self.assertTrue(
            all(row["feature_source"] == "planned" for row in planned_rows)
        )
        self.assertEqual(planned_rows[0]["features"]["spin_cast_rpm"], 1000)

    def test_split_actual_variants_split_rows_and_csv_carries_provenance(self) -> None:
        """One condition fabricated under two actual parameter variants
        exports one row per variant plus a planned row for the substrate
        whose executions carry no actual snapshot; CSV rows carry
        feature_source / variant_index / substrate_ids."""
        import csv as csv_module
        import io as io_module
        import json as json_module

        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
        )
        control = next(
            c for c in conditions if c.role == "control"
        )
        substrates = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(batch.id)
        )
        control_substrates = sorted(
            (s for s in substrates if s.batch_condition_id == control.id),
            key=lambda s: s.substrate_ordinal,
        )
        first_substrate_id = control_substrates[0].id

        def perovskite_executions():
            return [
                execution
                for execution in asyncio.run(
                    self.repository.list_process_executions(batch.id)
                )
                if execution.layer_type == "perovskite"
                and execution.method in ("spin_coating", "vcd", "annealing")
            ]

        # Split the first substrate's membership off every perovskite
        # execution while the batch is still a draft, so that substrate can
        # later be completed without an actual snapshot while its siblings
        # record one.
        for execution in perovskite_executions():
            members = asyncio.run(
                self.repository.list_process_execution_members(execution.id)
            )
            first_member = next(
                member
                for member in members
                if int(member["substrate_id"]) == first_substrate_id
            )
            asyncio.run(
                self.repository.split_process_execution(
                    execution.id,
                    member_ids=[int(first_member["id"])],
                    actor_user_id=1,
                )
            )

        for execution in perovskite_executions():
            members = asyncio.run(
                self.repository.list_process_execution_members(execution.id)
            )
            holds_first = any(
                int(member["substrate_id"]) == first_substrate_id
                for member in members
            )
            if not holds_first:
                if execution.method == "spin_coating":
                    adjusted = json_module.loads(
                        json_module.dumps(execution.planned_process_snapshot)
                    )
                    adjusted["spin_steps"][0]["rpm"] = 1234
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_process_snapshot=adjusted,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
                else:
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_matches_planned=True,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        # Cancel the remaining (non-perovskite) executions exactly once.
        handled = {execution.id for execution in perovskite_executions()}
        for execution in asyncio.run(
            self.repository.list_process_executions(batch.id)
        ):
            if execution.id in handled:
                continue
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
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
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 2 for c in conditions},
                shortfall_deviations=[
                    (c.id, "Test setup: two substrates per condition.")
                    for c in conditions
                ],
                actor_user_id=1,
            )
        )

        # One CSV carrying both control substrates; assignment maps A001 to
        # the split (no-actual) substrate and A002 to the recorded one.
        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001-A002 Channel 1.csv",
                    multi_device_csv(
                        [20, 20, 20, 20],
                        device_labels=["A001 Channel 1", "A002 Channel 1"],
                    ).encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch.id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
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
                    for substrate_id in ("A001", "A002")
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        rows = asyncio.run(
            self.repository.build_training_dataset(batch_id=batch.id)
        )
        control_rows = [
            row for row in rows if row["batch_condition_id"] == control.id
        ]
        self.assertEqual(len(control_rows), 2)
        actual_row = next(
            row for row in control_rows if row["feature_source"] == "actual"
        )
        planned_row = next(
            row for row in control_rows if row["feature_source"] == "planned"
        )
        # The recorded variant carries the adjusted actual rpm; the substrate
        # whose executions have no actual snapshot stays on the plan.
        self.assertEqual(actual_row["features"]["spin_cast_rpm"], 1234)
        self.assertNotIn(first_substrate_id, actual_row["substrate_ids"])
        self.assertEqual(planned_row["features"]["spin_cast_rpm"], 1000)
        self.assertEqual(planned_row["substrate_ids"], [first_substrate_id])
        # Metrics follow the substrate grouping: each measured device lands
        # on exactly one row. Under schema 6 both scan directions of the
        # device are independent samples, so the recorded variant's single
        # device contributes two samples.
        self.assertEqual(actual_row["metrics"]["device_count"], 2)
        self.assertEqual(planned_row["metrics"]["device_count"], 2)

        # The list API reads the write-time flat cache pooled from the
        # stored, non-excluded valid traces (v7 keeps no aggregate summaries
        # in the analysis JSON — list and detail must never disagree).
        listed = asyncio.run(
            self.repository.list_results_for_experiment(self.experiment_id)
        )
        self.assertTrue(listed)
        for result_row in listed:
            detail = asyncio.run(self.repository.get_result(result_row["id"]))
            expected = _flat_metrics_from_analysis(detail["analysis"])
            self.assertEqual(result_row["metrics"], expected)
            trace_pces = sorted(
                trace["metrics"]["pce"]
                for device in detail["analysis"]["devices"]
                if not device.get("excluded")
                for trace in device["traces"]
                if trace["valid"] and "pce" in trace["metrics"]
            )
            if trace_pces:
                self.assertEqual(
                    result_row["metrics"]["pce"], statistics.median(trace_pces)
                )

        csv_output = self._run_cli(
            "export-training-data",
            "--batch-id",
            str(batch.id),
            "--format",
            "csv",
        )
        table = list(csv_module.reader(io_module.StringIO(csv_output)))
        header = table[0]
        for column in ("feature_source", "variant_index", "substrate_ids"):
            self.assertIn(column, header)
        feature_column = header.index("feature_source")
        self.assertEqual(
            {row[feature_column] for row in table[1:] if row},
            {"actual", "planned"},
        )
        substrate_column = header.index("substrate_ids")
        self.assertTrue(
            any(";" in row[substrate_column] for row in table[1:] if row)
        )


    def test_per_variant_method_fallback_uses_each_variants_own_methods(self) -> None:
        """Two variants of one condition recording different method sets: the
        plan fallback must be decided by the row's own variant. The variant
        missing a VCD record backfills the planned VCD (mixed) while the
        fully recorded variant stays actual — regardless of variant iteration
        order."""
        import json as json_module

        from perovskite_bo.web_adapter import extract_condition_features

        batch = asyncio.run(
            self.repository.create_fabrication_batch(
                self.experiment_id, actor_user_id=1
            )
        )
        conditions = asyncio.run(
            self.repository.get_fabrication_batch_conditions(batch.id)
        )
        control = next(
            c for c in conditions if c.role == "control"
        )
        substrates = asyncio.run(
            self.repository.get_fabrication_substrates_for_batch(batch.id)
        )
        control_substrates = sorted(
            (s for s in substrates if s.batch_condition_id == control.id),
            key=lambda s: s.substrate_ordinal,
        )
        first_substrate_id = control_substrates[0].id
        sibling_ids = [s.id for s in control_substrates[1:]]

        def perovskite_executions():
            return [
                execution
                for execution in asyncio.run(
                    self.repository.list_process_executions(batch.id)
                )
                if execution.layer_type == "perovskite"
                and execution.method in ("spin_coating", "vcd", "annealing")
            ]

        for execution in perovskite_executions():
            members = asyncio.run(
                self.repository.list_process_execution_members(execution.id)
            )
            first_member = next(
                member
                for member in members
                if int(member["substrate_id"]) == first_substrate_id
            )
            asyncio.run(
                self.repository.split_process_execution(
                    execution.id,
                    member_ids=[int(first_member["id"])],
                    actor_user_id=1,
                )
            )

        for execution in perovskite_executions():
            members = asyncio.run(
                self.repository.list_process_execution_members(execution.id)
            )
            holds_first = any(
                int(member["substrate_id"]) == first_substrate_id
                for member in members
            )
            if not holds_first:
                # Siblings: all three methods recorded, spin adjusted.
                if execution.method == "spin_coating":
                    adjusted = json_module.loads(
                        json_module.dumps(execution.planned_process_snapshot)
                    )
                    adjusted["spin_steps"][0]["rpm"] = 1234
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_process_snapshot=adjusted,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
                else:
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_matches_planned=True,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
            else:
                # First substrate: spin + anneal recorded, VCD left blank.
                if execution.method == "spin_coating":
                    adjusted = json_module.loads(
                        json_module.dumps(execution.planned_process_snapshot)
                    )
                    adjusted["spin_steps"][0]["rpm"] = 4321
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_process_snapshot=adjusted,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
                elif execution.method == "annealing":
                    asyncio.run(
                        self.repository.update_process_execution(
                            execution.id,
                            actual_matches_planned=True,
                            fabrication_batch_id=batch.id,
                            actor_user_id=1,
                        )
                    )
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
                )
            )
        handled = {execution.id for execution in perovskite_executions()}
        for execution in asyncio.run(
            self.repository.list_process_executions(batch.id)
        ):
            if execution.id in handled:
                continue
            asyncio.run(
                self.repository.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch.id,
                    actor_user_id=1,
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
        asyncio.run(
            self.repository.update_fabrication_batch_status(
                batch.id,
                BatchStatus.COMPLETED,
                actual_substrate_counts={c.id: 2 for c in conditions},
                shortfall_deviations=[
                    (c.id, "Test setup: two substrates per condition.")
                    for c in conditions
                ],
                actor_user_id=1,
            )
        )

        uploaded = self.client.post(
            f"/api/experiments/{self.experiment_id}/results",
            files={
                "result_file": (
                    "A001-A002 Channel 1.csv",
                    multi_device_csv(
                        [20, 20, 20, 20],
                        device_labels=["A001 Channel 1", "A002 Channel 1"],
                    ).encode("utf-8"),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch.id)},
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        file_id = int(uploaded.json()["id"])
        detail = self.client.get(f"/api/results/{file_id}").json()
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
                    for substrate_id in ("A001", "A002")
                ]
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        rows = asyncio.run(
            self.repository.build_training_dataset(batch_id=batch.id)
        )
        control_rows = [
            row for row in rows if row["batch_condition_id"] == control.id
        ]
        # Both measured substrates are covered by their own variant rows; no
        # planned leftover row appears.
        rows_by_substrates = {
            frozenset(row["substrate_ids"]): row for row in control_rows
        }
        self.assertEqual(len(rows_by_substrates), 2)
        planned_features = extract_condition_features(control.recipe_snapshot)

        first_row = rows_by_substrates[frozenset({first_substrate_id})]
        self.assertEqual(first_row["feature_source"], "mixed")
        self.assertEqual(first_row["features"]["spin_cast_rpm"], 4321)
        # VCD was never recorded for this variant: the planned pressure is
        # backfilled (mixed), not left as None from a sibling's method set.
        self.assertEqual(
            first_row["features"]["vcd_stage1_pressure_pa"],
            planned_features["vcd_stage1_pressure_pa"],
        )

        siblings_row = rows_by_substrates[frozenset(sibling_ids)]
        self.assertEqual(siblings_row["feature_source"], "actual")
        self.assertEqual(siblings_row["features"]["spin_cast_rpm"], 1234)
        self.assertEqual(
            siblings_row["features"]["vcd_stage1_pressure_pa"],
            planned_features["vcd_stage1_pressure_pa"],
        )


if __name__ == "__main__":
    unittest.main()
