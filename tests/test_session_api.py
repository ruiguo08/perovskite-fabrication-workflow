"""JSON session/authentication endpoints and SPA serving for the React app."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from web import create_app
from web.repository import UserRole

TEST_USERNAME = "session-admin"
TEST_PASSWORD = "correct horse battery staple"

STATIC_APP_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "web" / "static-app"
)


class SessionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "session.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        import asyncio

        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _json_login(self) -> None:
        token = self.client.get("/api/auth/login-csrf").json()[
            "login_csrf_token"
        ]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": token,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get(
            "perovskite_csrf"
        )

    def test_session_requires_authentication(self) -> None:
        response = self.client.get("/api/session")
        self.assertEqual(response.status_code, 401)

    def test_session_returns_current_user(self) -> None:
        self._json_login()
        response = self.client.get("/api/session")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["username"], TEST_USERNAME)
        self.assertEqual(body["role"], "administrator")
        self.assertTrue(body["csrf_available"])
        self.assertIn("display_name", body)

    def test_login_csrf_sets_cookie_and_returns_token(self) -> None:
        response = self.client.get("/api/auth/login-csrf")
        self.assertEqual(response.status_code, 200)
        token = response.json()["login_csrf_token"]
        self.assertGreater(len(token), 0)
        self.assertEqual(
            self.client.cookies.get("perovskite_login_csrf"), token
        )

    def test_json_login_sets_session_cookies(self) -> None:
        self._json_login()
        self.assertIsNotNone(self.client.cookies.get("perovskite_session"))
        self.assertIsNotNone(self.client.cookies.get("perovskite_csrf"))

    def test_json_login_rejects_bad_password(self) -> None:
        token = self.client.get("/api/auth/login-csrf").json()[
            "login_csrf_token"
        ]
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": "wrong-password",
                "login_csrf": token,
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.client.cookies.get("perovskite_session"))

    def test_json_login_rejects_missing_login_csrf(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": "not-the-cookie-token",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.client.cookies.get("perovskite_session"))

    def test_json_logout_clears_session(self) -> None:
        self._json_login()
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.client.cookies.get("perovskite_session"))
        self.assertEqual(self.client.get("/api/session").status_code, 401)

    def test_state_changing_request_without_csrf_is_rejected(self) -> None:
        self._json_login()
        self.client.headers.pop("X-CSRF-Token", None)
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 403)

    @unittest.skipUnless(
        STATIC_APP_DIR.joinpath("index.html").is_file(),
        "frontend production build is not present",
    )
    def test_spa_entry_point_is_served_unauthenticated(self) -> None:
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn('<div id="root"></div>', response.text)

    @unittest.skipUnless(
        STATIC_APP_DIR.joinpath("index.html").is_file(),
        "frontend production build is not present",
    )
    def test_spa_deep_link_falls_back_to_entry_point(self) -> None:
        response = self.client.get("/app/experiments/42/deep/link")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<div id="root"></div>', response.text)

    @unittest.skipUnless(
        STATIC_APP_DIR.joinpath("index.html").is_file(),
        "frontend production build is not present",
    )
    def test_spa_assets_are_served_from_package_resource_directory(self) -> None:
        assets_dir = STATIC_APP_DIR / "assets"
        hashed_files = sorted(file.name for file in assets_dir.iterdir())
        self.assertTrue(hashed_files, "expected hashed bundle files")
        response = self.client.get(f"/app/assets/{hashed_files[0]}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("cache-control"),
            "public, max-age=31536000, immutable",
        )

    def test_api_and_static_paths_are_not_shadowed(self) -> None:
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_missing_spa_asset_is_not_cached_as_immutable(self) -> None:
        response = self.client.get("/app/assets/does-not-exist.js")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("immutable", response.headers.get("cache-control", ""))
        self.assertEqual(self.client.get("/static/experiment-builder.js").status_code, 404)


if __name__ == "__main__":
    unittest.main()
