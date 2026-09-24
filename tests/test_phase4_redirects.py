"""Phase 4B canonical redirect tests."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from web import create_app
from web.repository import UserRole


class Phase4RedirectTests(unittest.TestCase):
    """Verify legacy GET URLs redirect to their React equivalents."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        database_path = Path(cls.temporary_directory.name) / "phase4.sqlite3"
        cls.app = create_app(
            database_path,
            secure_cookies=False,
            _test_user=("phase4-admin", "Phase 4 admin password 2026!", UserRole.ADMINISTRATOR),
        )
        cls._context = TestClient(cls.app)
        cls._context.__enter__()
        cls.client = cls._context
        cls._login()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._context.__exit__(None, None, None)
        cls.temporary_directory.cleanup()

    @classmethod
    def _login(cls) -> None:
        csrf = cls.client.get("/api/auth/login-csrf")
        assert csrf.status_code == 200
        token = csrf.json()["login_csrf_token"]
        result = cls.client.post(
            "/api/auth/login",
            json={
                "username": "phase4-admin",
                "password": "Phase 4 admin password 2026!",
                "login_csrf": token,
            },
        )
        assert result.status_code == 200, result.text
        cls.client.headers["X-CSRF-Token"] = cls.client.cookies.get("perovskite_csrf")

    def test_root_redirects_to_app(self) -> None:
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/")

    def test_experiments_redirects(self) -> None:
        response = self.client.get("/experiments", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments")

    def test_new_experiment_redirects(self) -> None:
        response = self.client.get("/experiments/new", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments/new")

    def test_experiment_detail_redirects(self) -> None:
        response = self.client.get("/experiments/42", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments/42")

    def test_upload_redirects(self) -> None:
        response = self.client.get("/experiments/42/upload", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments/42/upload")

    def test_result_analysis_redirects(self) -> None:
        response = self.client.get(
            "/experiments/42/results/99/analysis", follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/results/99")

    def test_batch_dashboard_redirects(self) -> None:
        response = self.client.get(
            "/experiments/42/batches/7", follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"], "/app/experiments/42/batches/7"
        )

    def test_campaigns_redirects(self) -> None:
        response = self.client.get("/campaigns", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/campaigns")

    def test_materials_redirects(self) -> None:
        response = self.client.get("/materials", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/materials")

    def test_admin_users_redirects(self) -> None:
        response = self.client.get("/admin/users", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/users")

    def test_login_redirects_with_next(self) -> None:
        response = self.client.get(
            "/login", params={"next": "/experiments/42"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertIn("/app/login", response.headers["location"])
        self.assertIn("next=%2Fexperiments%2F42", response.headers["location"])

    def test_login_preserves_explicit_experiments_destination(self) -> None:
        """Explicit /experiments must be preserved, not treated as a fallback."""
        response = self.client.get(
            "/login", params={"next": "/experiments"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        location = response.headers["location"]
        self.assertIn("/app/login", location)
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(location).query)
        self.assertIn("next", params)
        self.assertEqual(params["next"][0], "/experiments")

    def test_login_redirects_without_next(self) -> None:
        response = self.client.get("/login", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/login")

    def test_login_rejects_protocol_relative_next(self) -> None:
        response = self.client.get(
            "/login", params={"next": "//evil.example"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("evil", response.headers["location"])

    def test_login_preserves_nested_query_in_next(self) -> None:
        response = self.client.get(
            "/login", params={"next": "/experiments/42?tab=plan&view=full"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        location = response.headers["location"]
        self.assertIn("/app/login", location)
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        self.assertIn("next", params)
        self.assertEqual(params["next"][0], "/experiments/42?tab=plan&view=full")

    def test_export_routes_not_redirected(self) -> None:
        """Export routes must remain as-is, not 303 redirects."""
        response = self.client.get(
            "/experiments/42/export.json", follow_redirects=False
        )
        self.assertNotEqual(response.status_code, 303)

    def test_api_not_redirected(self) -> None:
        """API routes must not be redirected."""
        response = self.client.get("/api/session")
        self.assertNotEqual(response.status_code, 303)

    def test_healthz_not_redirected(self) -> None:
        response = self.client.get("/healthz")
        self.assertNotEqual(response.status_code, 303)

    def test_app_spa_not_redirected(self) -> None:
        response = self.client.get("/app/")
        self.assertNotEqual(response.status_code, 303)

    def test_unauthenticated_legacy_get_redirects_to_app_login(self) -> None:
        """Unauthenticated GET /experiments → 303 /app/experiments (direct, no auth)."""
        client = TestClient(self.app)
        response = client.get("/experiments", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments")

    def test_unauthenticated_root_redirects_directly(self) -> None:
        """Unauthenticated GET / → 303 /app/ (direct, no login hop)."""
        client = TestClient(self.app)
        response = client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/")

    def test_unauthenticated_experiment_detail_redirects_directly(self) -> None:
        """Unauthenticated GET /experiments/42 → 303 /app/experiments/42."""
        client = TestClient(self.app)
        response = client.get("/experiments/42", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/experiments/42")

    def test_unauthenticated_admin_users_redirects_directly(self) -> None:
        """Unauthenticated GET /admin/users → 303 /app/users (no role check on redirect)."""
        client = TestClient(self.app)
        response = client.get("/admin/users", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/app/users")


if __name__ == "__main__":
    unittest.main()
