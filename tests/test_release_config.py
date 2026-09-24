import sys
import tomllib
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from web.version import __version__


class ReleaseConfigurationTests(unittest.TestCase):
    def test_package_uses_the_shared_dynamic_version(self) -> None:
        with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as project_file:
            project = tomllib.load(project_file)

        self.assertIn("version", project["project"]["dynamic"])
        self.assertEqual(
            project["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "web.version.__version__",
        )
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_production_database_does_not_bootstrap_as_the_app_role(self) -> None:
        compose = (REPOSITORY_ROOT / "deploy" / "postgresql.compose.yaml").read_text()
        role_setup = (
            REPOSITORY_ROOT
            / "deploy"
            / "postgres-init"
            / "00-create-application-roles.sh"
        ).read_text()

        self.assertIn("POSTGRES_USER:-perovskite_bootstrap", compose)
        self.assertNotIn("POSTGRES_USER:-perovskite_app", compose)
        self.assertIn("ALTER DATABASE", role_setup)
        self.assertIn("OWNER TO perovskite_migrator", role_setup)
        self.assertIn("NOSUPERUSER NOCREATEDB NOCREATEROLE", role_setup)
        self.assertIn("GRANT USAGE ON SCHEMA public TO perovskite_app", role_setup)

    def test_production_service_is_supervised_and_unprivileged(self) -> None:
        service = (REPOSITORY_ROOT / "deploy" / "perovskite-web.service").read_text()

        self.assertIn("User=perovskite", service)
        self.assertIn("ExecStartPre=", service)
        self.assertIn("Restart=on-failure", service)
        self.assertIn("NoNewPrivileges=true", service)

    def test_ubuntu_deployment_has_separate_migration_and_backup_services(self) -> None:
        migration = (
            REPOSITORY_ROOT / "deploy" / "perovskite-migrate.service"
        ).read_text()
        backup = (REPOSITORY_ROOT / "deploy" / "perovskite-backup.service").read_text()
        timer = (REPOSITORY_ROOT / "deploy" / "perovskite-backup.timer").read_text()
        script = (REPOSITORY_ROOT / "deploy" / "backup-postgresql.sh").read_text()

        self.assertIn("User=perovskite-migrator", migration)
        self.assertIn("upgrade head", migration)
        self.assertIn("User=root", backup)
        self.assertIn("OnCalendar=", timer)
        self.assertIn("pg_dump", script)
        self.assertIn("sha256sum", script)

    def test_web_service_requires_and_starts_after_the_migration_unit(self) -> None:
        service = (REPOSITORY_ROOT / "deploy" / "perovskite-web.service").read_text()
        migration = (
            REPOSITORY_ROOT / "deploy" / "perovskite-migrate.service"
        ).read_text()

        self.assertIn("Requires=perovskite-migrate.service", service)
        self.assertIn("perovskite-migrate.service", service.split("After=", 1)[1])
        self.assertIn("RemainAfterExit=yes", migration)

    def test_expired_session_cleanup_timer_and_service_exist(self) -> None:
        service = (
            REPOSITORY_ROOT / "deploy" / "perovskite-session-cleanup.service"
        ).read_text()
        timer = (
            REPOSITORY_ROOT / "deploy" / "perovskite-session-cleanup.timer"
        ).read_text()

        self.assertIn("cleanup-sessions", service)
        self.assertIn("User=perovskite", service)
        self.assertIn("/etc/perovskite/perovskite.env", service)
        self.assertIn("OnCalendar=", timer)
        self.assertIn("Persistent=true", timer)
        self.assertEqual(timer.split("Unit=", 1)[1].splitlines()[0], "perovskite-session-cleanup.service")

    def test_check_database_detects_a_behind_revision_and_exits_nonzero(self) -> None:
        import asyncio
        import os

        test_url = os.environ.get("PEROVSKITE_TEST_POSTGRESQL_URL")
        if not test_url:
            self.skipTest("set PEROVSKITE_TEST_POSTGRESQL_URL to run this check")

        from alembic import command
        from alembic.config import Config as AlembicConfig
        from web.admin_cli import parser as admin_parser, run_command
        from web.database import Database

        previous_url = os.environ.get("PEROVSKITE_DATABASE_URL")
        os.environ["PEROVSKITE_DATABASE_URL"] = test_url
        config = AlembicConfig(str(REPOSITORY_ROOT / "alembic.ini"))
        config.set_main_option(
            "script_location", str(REPOSITORY_ROOT / "migrations")
        )
        command.upgrade(config, "head")
        command.downgrade(config, "0013_substrate_laser_marks")

        database = Database(test_url)
        args = admin_parser().parse_args(["check-database"])
        try:
            with self.assertRaises(SystemExit) as context:
                asyncio.run(run_command(args, database))
            self.assertNotEqual(int(context.exception.code or 0), 0)
        finally:
            asyncio.run(database.dispose())
            command.upgrade(config, "head")
            if previous_url is None:
                os.environ.pop("PEROVSKITE_DATABASE_URL", None)
            else:
                os.environ["PEROVSKITE_DATABASE_URL"] = previous_url

    def test_chrome_discovery_includes_linux_paths(self) -> None:
        from tests.test_browser_builder import CHROME_PATHS

        paths = [str(path) for path in CHROME_PATHS]
        self.assertTrue(any("google-chrome" in path.lower() for path in paths))
        self.assertTrue(any("chromium" in path.lower() for path in paths))

    def test_version_remains_the_owner_release_checkpoint(self) -> None:
        self.assertEqual(__version__, "0.4.0")


if __name__ == "__main__":
    unittest.main()
