"""Ensure the React API is the only mutable browser-facing interface."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from web import create_app
from web.repository import UserRole


ROOT = Path(__file__).resolve().parents[1]
LEGACY_POST_PATHS = (
    "/login",
    "/logout",
    "/experiments",
    "/experiments/1/substrate-exceptions",
    "/experiments/1/substrate-exceptions/1/decision",
    "/experiments/1/plan-status",
    "/experiments/1/results",
    "/experiments/1/results/1/assignments",
    "/experiments/1/fabrication-batches",
    "/campaigns",
    "/campaigns/update",
    "/materials",
    "/materials/1/products",
    "/materials/1/update",
    "/material-products/1/update",
    "/admin/users",
    "/admin/users/1/access",
    "/admin/users/1/password",
)


class LegacyMutationAbsenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(
                Path(self.tmp.name) / ".phase4-no-legacy.sqlite3",
                secure_cookies=False,
                _test_user=("phase4-routes", "Phase 4 routes password!", UserRole.ADMINISTRATOR),
            )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        # Windows keeps the SQLite file locked while pooled connections are
        # open, so dispose before TemporaryDirectory.cleanup() removes it.
        asyncio.run(self.app.state.database.dispose())
        self.tmp.cleanup()

    def test_legacy_form_mutations_are_not_routable(self) -> None:
        for path in LEGACY_POST_PATHS:
            with self.subTest(path=path):
                self.assertIn(self.client.post(path).status_code, {404, 405})

    def test_json_mutation_contracts_reject_unauthenticated_requests(self) -> None:
        paths = {
            "/api/auth/login": 422,
            "/api/auth/logout": 401,
            "/api/users": 401,
            "/api/experiments": 401,
            "/api/experiments/1/results": 401,
            "/api/experiments/1/fabrication-batches": 401,
            "/api/results/1/assignments": 401,
        }
        for path, expected_status in paths.items():
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, expected_status)

    @staticmethod
    def _routes_module_sources() -> str:
        """Concatenated source of every module in the web.routes package."""

        routes_dir = ROOT / "src" / "web" / "routes"
        return chr(10).join(
            child.read_text(encoding="utf-8")
            for child in sorted(routes_dir.glob("*.py"))
        )

    def test_jinja_form_implementation_is_absent(self) -> None:
        source = self._routes_module_sources()
        self.assertNotIn("Jinja2Templates", source)
        self.assertNotIn("from .forms import", source)
        self.assertFalse((ROOT / "src" / "web" / "forms.py").exists())

    def test_legacy_template_handlers_are_not_left_as_dead_code(self) -> None:
        source = self._routes_module_sources()
        retired_helpers = (
            "request_substrate_exception_page",
            "decide_substrate_exception_page",
            "update_plan_status_page",
            "upload_result_form",
            "upload_result_page",
            "result_analysis_page",
            "save_result_assignments",
            "campaign_management_page",
            "create_campaign_page",
            "update_campaign_page",
            "material_directory_page",
            "create_material_page",
            "create_material_product_page",
            "update_material_page",
            "update_material_product_page",
            "create_fabrication_batch_form",
            "fabrication_batch_dashboard",
            "_history_response",
            "_create_experiment_from_form",
            "_recipe_template_context",
            "_layer_preset_builder_map",
            "_builder_json_or_default",
            "_template_response",
            "_get_result_or_404",
        )
        for helper in retired_helpers:
            with self.subTest(helper=helper):
                self.assertNotIn(f"def {helper}(", source)


if __name__ == "__main__":
    unittest.main()
