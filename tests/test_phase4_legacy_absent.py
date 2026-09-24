"""Phase 4C guardrails for the removed Jinja-era application surface."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from web import create_app
from web.repository import UserRole


ROOT = Path(__file__).resolve().parents[1]


class LegacyAssetAbsenceTests(unittest.TestCase):
    """The installed React application must not retain legacy browser assets."""

    def setUp(self) -> None:
        self.client_context = TestClient(
            create_app(
                ROOT / ".phase4-legacy-absence.sqlite3",
                secure_cookies=False,
                _test_user=("phase4-assets", "Phase 4 assets password!", UserRole.ADMINISTRATOR),
            )
        )
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        database_path = ROOT / ".phase4-legacy-absence.sqlite3"
        if database_path.exists():
            database_path.unlink()

    def test_legacy_templates_and_javascript_are_absent(self) -> None:
        self.assertFalse(list((ROOT / "src" / "web" / "templates").glob("*.html")))
        self.assertFalse(list((ROOT / "src" / "web" / "static").glob("*.js")))
        self.assertEqual(self.client.get("/static/experiment-builder.js").status_code, 404)

    def test_spa_entry_references_immutable_self_hosted_assets(self) -> None:
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)
        assets = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', response.text)
        self.assertGreaterEqual(len(assets), 2)
        for asset in assets:
            asset_response = self.client.get(asset)
            self.assertEqual(asset_response.status_code, 200, asset)
            self.assertEqual(
                asset_response.headers.get("cache-control"),
                "public, max-age=31536000, immutable",
            )

    def test_package_and_csp_do_not_reference_jinja_or_a_cdn(self) -> None:
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn('"jinja2', project)
        self.assertNotIn('"templates/*.html"', project)
        self.assertNotIn('"static/*.js"', project)
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)
        csp = response.headers["content-security-policy"]
        self.assertNotIn("cdn.jsdelivr.net", csp)
        self.assertNotIn("'unsafe-inline'", csp)


if __name__ == "__main__":
    unittest.main()
