"""Administration CLI maintenance subcommands: expired-session cleanup,
audit-event export, and status summary."""

import asyncio
import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web import create_app
from web.admin_cli import parser as admin_parser, run_command
from web.repository import UserRole

TEST_USERNAME = "maintenance-admin"
TEST_PASSWORD = "correct horse battery staple"

CSV_HEADER = [
    "id",
    "created_at",
    "actor_username",
    "action",
    "entity_type",
    "entity_id",
    "client_ip",
    "details",
]


class AdminMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "maintenance.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.database = self.app.state.database
        asyncio.run(self.database.initialize())
        from web.auth import hash_password, normalize_username
        from web.repository import WebRepository

        self.test_username = normalize_username(TEST_USERNAME)
        repository = WebRepository(self.database)
        asyncio.run(
            repository.create_user(
                username=self.test_username,
                display_name="Maintenance Admin",
                password_hash=hash_password(
                    TEST_PASSWORD, username=self.test_username
                ),
                role=UserRole.ADMINISTRATOR,
            )
        )

    def tearDown(self) -> None:
        asyncio.run(self.database.dispose())
        self.tmp.cleanup()

    def _run(self, *argv: str) -> str:
        args = admin_parser().parse_args(list(argv))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            asyncio.run(run_command(args, self.database))
        return output.getvalue()

    def _create_session(self, token_hash: str, *, expires_at: dt.datetime) -> None:
        from web.repository import WebRepository

        repository = WebRepository(self.database)
        user = asyncio.run(repository.get_user_by_username(self.test_username))
        assert user is not None
        asyncio.run(
            repository.create_session(
                token_hash=token_hash,
                csrf_token_hash=f"csrf-{token_hash}",
                user_id=user.id,
                expires_at=expires_at,
                client_ip=None,
                user_agent=None,
                password_changed_at=user.password_changed_at,
            )
        )

    def test_cleanup_sessions_deletes_only_expired_sessions(self) -> None:
        from web.repository import WebRepository

        now = dt.datetime.now(dt.timezone.utc)
        self._create_session(
            "expired-token-hash-0001", expires_at=now - dt.timedelta(minutes=1)
        )
        self._create_session(
            "valid-token-hash-0002", expires_at=now + dt.timedelta(hours=1)
        )

        output = self._run("cleanup-sessions")

        self.assertIn("Deleted 1 expired session", output)
        repository = WebRepository(self.database)
        self.assertIsNone(
            asyncio.run(repository.get_session("expired-token-hash-0001"))
        )
        self.assertIsNotNone(
            asyncio.run(repository.get_session("valid-token-hash-0002"))
        )

    def test_export_audit_json_filters_by_action_prefix(self) -> None:
        from web.repository import WebRepository

        now = dt.datetime.now(dt.timezone.utc)
        self._create_session(
            "audit-token-hash-0001", expires_at=now + dt.timedelta(hours=1)
        )
        repository = WebRepository(self.database)
        user = asyncio.run(repository.get_user_by_username(self.test_username))
        assert user is not None
        asyncio.run(
            repository.delete_session(
                "audit-token-hash-0001",
                actor_user_id=user.id,
                client_ip=None,
            )
        )

        login_output = self._run(
            "export-audit", "--format", "json", "--action", "session.login"
        )
        login_records = [
            json.loads(line) for line in login_output.splitlines() if line.strip()
        ]
        self.assertEqual(len(login_records), 1)
        self.assertEqual(login_records[0]["action"], "session.login")
        self.assertEqual(login_records[0]["actor_username"], TEST_USERNAME)
        self.assertIn("created_at", login_records[0])
        self.assertIn("details", login_records[0])

        logout_output = self._run(
            "export-audit", "--format", "json", "--action", "session.logout"
        )
        logout_records = [
            json.loads(line) for line in logout_output.splitlines() if line.strip()
        ]
        self.assertEqual(len(logout_records), 1)
        self.assertEqual(logout_records[0]["action"], "session.logout")

    def test_export_audit_csv_has_header_and_rows(self) -> None:
        import csv

        now = dt.datetime.now(dt.timezone.utc)
        self._create_session(
            "csv-token-hash-0001", expires_at=now + dt.timedelta(hours=1)
        )

        output = self._run(
            "export-audit", "--format", "csv", "--action", "session.login"
        )
        rows = list(csv.reader(io.StringIO(output)))
        self.assertEqual(rows[0], CSV_HEADER)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], "session.login")
        self.assertEqual(rows[1][2], self.test_username)

    def test_export_audit_honors_since_and_until(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        self._create_session(
            "window-token-hash-0001", expires_at=now + dt.timedelta(hours=1)
        )

        future = (now + dt.timedelta(minutes=5)).isoformat()
        excluded = self._run("export-audit", "--format", "json", "--since", future)
        self.assertEqual(
            [line for line in excluded.splitlines() if line.strip()], []
        )

        past = (now - dt.timedelta(minutes=5)).isoformat()
        included = self._run("export-audit", "--format", "json", "--since", past)
        records = [
            json.loads(line) for line in included.splitlines() if line.strip()
        ]
        self.assertGreaterEqual(len(records), 1)

    def test_export_audit_rejects_unknown_actor(self) -> None:
        args = admin_parser().parse_args(["export-audit", "--actor", "nobody"])
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                asyncio.run(run_command(args, self.database))
        self.assertNotEqual(int(context.exception.code or 0), 0)

    def test_status_reports_expected_counters(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        self._create_session(
            "status-token-hash-0001", expires_at=now + dt.timedelta(hours=1)
        )

        output = self._run("status")

        self.assertIn("users: 1", output)
        self.assertIn("active_sessions: 1", output)
        self.assertIn("experiments: 0", output)
        self.assertIn("fabrication_batches: 0", output)
        self.assertIn("result_files: 0", output)
        self.assertIn("audit_events_last_24h: 2", output)


class AdminCatalogTransferTests(unittest.TestCase):
    """export-catalog / import-catalog: the test-to-production catalog lift."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.source_path = Path(self.tmp.name) / "source.sqlite3"
        self.target_path = Path(self.tmp.name) / "target.sqlite3"
        self.app = create_app(
            self.source_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.database = self.app.state.database
        asyncio.run(self.database.initialize())
        from web.auth import hash_password, normalize_username
        from web.repository import WebRepository

        self.test_username = normalize_username(TEST_USERNAME)
        repository = WebRepository(self.database)
        self.admin = asyncio.run(
            repository.create_user(
                username=self.test_username,
                display_name="Catalog Admin",
                password_hash=hash_password(
                    TEST_PASSWORD, username=self.test_username
                ),
                role=UserRole.ADMINISTRATOR,
            )
        )
        self.export_path = Path(self.tmp.name) / "catalog-export.json"

    def tearDown(self) -> None:
        asyncio.run(self.database.dispose())
        self.tmp.cleanup()

    def _run(self, *argv: str) -> str:
        args = admin_parser().parse_args(list(argv))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            asyncio.run(run_command(args, self.database))
        return output.getvalue()

    def _seed_source_catalog(self) -> None:
        from decimal import Decimal

        from web.repository import WebRepository
        from web.services.catalog_service import create_device_layout

        repository = WebRepository(self.database)
        asyncio.run(
            repository.create_material(
                category="solvent",
                name="IPA",
                formula="C3H8O",
                cas_number="67-63-0",
                specification={},
                actor_user_id=self.admin.id,
            )
        )
        material = asyncio.run(
            repository.create_material(
                category="chemical",
                name="PEAI",
                formula="C6H5NH3I",
                cas_number="486-07-9",
                specification={"purity": "99%"},
                actor_user_id=self.admin.id,
            )
        )
        asyncio.run(
            repository.create_material_product(
                material["id"],
                vendor="Example vendor",
                catalog_number="PEAI-100",
                specification={},
                actor_user_id=self.admin.id,
            )
        )
        asyncio.run(
            repository.create_layer_preset(
                name="Imported NiOx preset",
                layer={
                    "layer_type": "niox",
                    "role": "htl",
                    "name": "NiOx",
                    "preset_id": None,
                    "solution": None,
                    "process": None,
                },
                deposition_process=None,
                scope="shared",
                actor_user_id=self.admin.id,
            )
        )
        async def _create_layout() -> None:
            async with self.database.begin() as connection:
                await create_device_layout(
                    connection,
                    code="15x15_dual_005",
                    version=1,
                    substrate_width_mm=Decimal("15"),
                    substrate_length_mm=Decimal("15"),
                    devices_per_substrate=2,
                    device_active_area_cm2=Decimal("0.05"),
                    total_active_area_cm2=Decimal("0.1"),
                    description="15 x 15 mm dual device",
                )

        asyncio.run(_create_layout())

    def _export_to_file(self) -> dict:
        self._run("export-catalog", "--output", str(self.export_path))
        return json.loads(self.export_path.read_text(encoding="utf-8"))

    def test_export_catalog_round_trips_into_a_fresh_database(self) -> None:
        from web.repository import WebRepository
        from web.services.catalog_service import list_device_layouts

        self._seed_source_catalog()
        document = self._export_to_file()

        self.assertEqual(document["export_schema_version"], 1)
        self.assertEqual(len(document["device_layouts"]), 1)
        self.assertEqual(len(document["materials"]), 2)
        self.assertEqual(len(document["layer_presets"]), 1)
        self.assertEqual(
            document["device_layouts"][0]["substrate_width_mm"], "15.0000"
        )
        # Material products ride along with their material.
        peai = next(
            material
            for material in document["materials"]
            if material["name"] == "PEAI"
        )
        self.assertEqual(len(peai["products"]), 1)
        self.assertEqual(peai["products"][0]["catalog_number"], "PEAI-100")

        # Import into a second, empty database.
        target_app = create_app(
            self.target_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        target_database = target_app.state.database
        asyncio.run(target_database.initialize())
        try:
            # The import records an acting user, so the target database
            # needs the administrator account to exist there too.
            from web.auth import hash_password
            from web.repository import WebRepository as TargetRepository

            target_repository = TargetRepository(target_database)
            asyncio.run(
                target_repository.create_user(
                    username=self.test_username,
                    display_name="Catalog Admin",
                    password_hash=hash_password(
                        TEST_PASSWORD, username=self.test_username
                    ),
                    role=UserRole.ADMINISTRATOR,
                )
            )
            args = admin_parser().parse_args(
                [
                    "import-catalog",
                    str(self.export_path),
                    "--actor",
                    self.test_username,
                ]
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                asyncio.run(run_command(args, target_database))
            result = output.getvalue()
            self.assertIn("'layer_presets': 1", result)
            self.assertIn("'baselines': 0", result)
            self.assertIn("Skipped 0", result)

            async def _verify() -> None:
                async with target_database.engine.connect() as connection:
                    imported_layouts = await list_device_layouts(connection)
                self.assertEqual(len(imported_layouts), 1)
                self.assertEqual(imported_layouts[0].code, "15x15_dual_005")

            asyncio.run(_verify())

            repository = WebRepository(target_database)
            materials = asyncio.run(
                repository.list_materials(actor_user_id=self.admin.id)
            )
            names = {material["name"] for material in materials}
            self.assertIn("IPA", names)
            self.assertIn("PEAI", names)
            peai_target = next(
                material
                for material in materials
                if material["name"] == "PEAI"
            )
            self.assertEqual(len(peai_target["products"]), 1)
            self.assertEqual(peai_target["products"][0]["catalog_number"], "PEAI-100")

            presets = asyncio.run(
                repository.list_layer_presets(
                    actor_user_id=self.admin.id, include_inactive=True
                )
            )
            self.assertTrue(
                any(
                    preset["name"] == "Imported NiOx preset"
                    for preset in presets
                )
            )
        finally:
            asyncio.run(target_database.dispose())

    def test_export_catalog_excludes_pending_materials_and_products(self) -> None:
        """A student's pending proposal must not ride the transfer path:
        import runs as an instructor/administrator and would auto-activate
        it, bypassing the review gate."""
        from web.auth import hash_password
        from web.repository import WebRepository

        repository = WebRepository(self.database)
        # Administrator-created materials are active immediately.
        asyncio.run(
            repository.create_material(
                category="chemical",
                name="Approved FAI",
                formula="",
                cas_number="",
                specification={},
                actor_user_id=self.admin.id,
            )
        )
        student = asyncio.run(
            repository.create_user(
                username="pending-student",
                display_name="Pending Student",
                password_hash=hash_password(
                    "student password!", username="pending-student"
                ),
                role=UserRole.STUDENT,
            )
        )
        asyncio.run(
            repository.create_material(
                category="chemical",
                name="Unreviewed EDADI",
                formula="",
                cas_number="",
                specification={},
                actor_user_id=student.id,
            )
        )

        document = self._export_to_file()

        exported_names = {
            material["name"] for material in document["materials"]
        }
        self.assertIn("Approved FAI", exported_names)
        self.assertNotIn("Unreviewed EDADI", exported_names)

    def test_import_catalog_is_idempotent_for_existing_records(self) -> None:
        self._seed_source_catalog()
        self._export_to_file()

        # Re-import into the SAME source database: every record already
        # exists, so all rows should be skipped without errors.
        output = self._run(
            "import-catalog", str(self.export_path), "--actor", self.test_username
        )

        self.assertIn("Skipped", output)
        self.assertIn("'layer_presets': 0", output)
        self.assertIn("'materials': 0", output)
        self.assertIn("'device_layouts': 0", output)

    def test_import_catalog_rejects_non_catalog_input(self) -> None:
        bad_path = Path(self.tmp.name) / "not-a-catalog.json"
        bad_path.write_text('{"hello": "world"}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                self._run(
                    "import-catalog",
                    str(bad_path),
                    "--actor",
                    self.test_username,
                )
        self.assertTrue(context.exception.code)

    def test_import_catalog_rejects_unknown_actor(self) -> None:
        self._seed_source_catalog()
        self._export_to_file()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                self._run(
                    "import-catalog",
                    str(self.export_path),
                    "--actor",
                    "does-not-exist",
                )
        self.assertNotEqual(int(context.exception.code or 0), 0)


if __name__ == "__main__":
    unittest.main()
