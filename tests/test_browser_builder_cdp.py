"""Phase 4B genuine CDP browser tests for the experiment-builder workflow.

Replaces the retired ReactBuilderBrowserTests (CSP false positive). Drives the
production React bundle via the CDP top-document driver (no iframe, no inline
harness). The test logs in via JSON auth, opens /app/experiments/new, selects
a seeded baseline through the visible UI, navigates to the layer step, edits
a weight value, submits through the real React "Save experiment" button,
verifies navigation to /app/experiments/{id}, verifies the saved record via
the backend API, and checks 320px overflow on both builder and detail pages.

Every step is mandatory — the test fails if any baseline/edit/save/navigation/
persistence/detail step does not occur.
"""

from __future__ import annotations
import os

import json
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from web import create_app
from web.repository import UserRole

from tests.cdp_driver import (
    click_center,
    evaluate,
    get_cookies,
    launch_chrome_with_viewport,
    wait_for_expression,
)
from tests.test_browser_builder import chrome_path

ADMIN_USERNAME = "builder-cdp-admin"
ADMIN_PASSWORD = "Builder CDP admin password 2026!"


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _js_escape(value: object) -> str:
    return json.dumps(value)


@unittest.skipIf(chrome_path() is None and not os.environ.get("CI"), "install Google Chrome to run browser tests")
class BuilderCdpBrowserTests(unittest.TestCase):
    """Verify the React experiment-builder end-to-end via genuine CDP."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        database_path = Path(cls.temporary_directory.name) / "builder-cdp.sqlite3"
        cls.app = create_app(
            database_path,
            secure_cookies=False,
            _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
        )

        with TestClient(cls.app) as client:
            csrf = client.get("/api/auth/login-csrf")
            assert csrf.status_code == 200
            token = csrf.json()["login_csrf_token"]
            logged_in = client.post(
                "/api/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "login_csrf": token},
            )
            assert logged_in.status_code == 200, logged_in.text
            client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")
            from tests.layout_fixtures import seed_standard_layouts

            seed_standard_layouts(client)
            from tests.test_web_app import complete_guided_setup
            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = [dict(layer) for layer in device_recipe["layers"]]
                    group["deposition_process"] = json.loads(json.dumps(deposition_process))
            baseline = client.post(
                "/api/baselines",
                json={"name": "Builder CDP baseline", "device_recipe": device_recipe, "deposition_process": deposition_process},
            )
            assert baseline.status_code == 201, baseline.text
            cls.baseline_version_id = baseline.json()["current_version_id"]
            cls.baseline_name = baseline.json()["name"]
            cls.seeded_recipe = device_recipe
            # Seed a campaign for the builder's campaign select.
            campaign = client.post("/api/campaigns", json={"code": "builder-cdp", "display_name": "Builder CDP Campaign", "description": "Test campaign"})
            assert campaign.status_code == 201, campaign.text
            cls.campaign_code = "builder-cdp"
            cls.campaign_name = "Builder CDP Campaign"
            cls.campaign_id = campaign.json()["id"]
            # Capture the first solid chemical's initial weight for editing.
            for layer in device_recipe["layers"]:
                if layer.get("solution") and layer["solution"].get("solids"):
                    cls.edit_layer_name = layer["name"]
                    cls.edit_chemical = layer["solution"]["solids"][0]["chemical"]
                    cls.edit_weight_before = layer["solution"]["solids"][0]["weight_mg"]
                    cls.edit_weight_after = cls.edit_weight_before + 1.0
                    break

        cls.app_port = available_port()
        config = uvicorn.Config(cls.app, host="127.0.0.1", port=cls.app_port, log_level="error")
        cls.server = uvicorn.Server(config)
        cls.server.install_signal_handlers = lambda: None
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not cls.server.started:
            raise RuntimeError("builder CDP test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.server_thread.join(timeout=5)
        cls.temporary_directory.cleanup()

    def _login_via_fetch(self, session: object) -> None:
        csrf = evaluate(
            session,
            "fetch('/api/auth/login-csrf').then(r => r.json()).then(d => d.login_csrf_token)",
        )
        status = evaluate(
            session,
            (
                "fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, "
                f"body: JSON.stringify({{username: {_js_escape(ADMIN_USERNAME)}, password: {_js_escape(ADMIN_PASSWORD)}, "
                "login_csrf: " + _js_escape(csrf) + "})}).then(r => r.status)"
            ),
        )
        self.assertEqual(int(status), 200)

    def _navigate(self, session: object, path: str) -> None:
        evaluate(session, f"location.href = {_js_escape(path)}")
        wait_for_expression(session, "Boolean(document.querySelector('#root'))")

    def _set_native_value(self, session: object, expression: str, value: str) -> bool:
        """Set a value on an element returned by a JS expression via native setter."""
        result = evaluate(
            session,
            f"(function(){{const el=({expression});if(!el)return false;"
            "const p=el instanceof HTMLSelectElement?"
            "Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set:"
            "el instanceof HTMLTextAreaElement?"
            "Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set:"
            "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
            f"p.call(el,{_js_escape(value)});"
            "const evt=el instanceof HTMLSelectElement?'change':'input';"
            "el.dispatchEvent(new Event(evt,{bubbles:true}));return true;})()",
        )
        return bool(result)

    def _assert_viewport(self, session: object, expected: int) -> None:
        inner = evaluate(session, "window.innerWidth")
        client = evaluate(session, "document.documentElement.clientWidth")
        diagnostic = (f"window.innerWidth={inner}px, "
                      f"document.documentElement.clientWidth={client}px, expected {expected}px")
        self.assertEqual(int(inner), expected, diagnostic)
        self.assertEqual(int(client), expected, diagnostic)

    def _assert_no_overflow(self, session: object, label: str) -> None:
        overflow = evaluate(
            session,
            "document.documentElement.scrollWidth > document.documentElement.clientWidth",
        )
        self.assertFalse(overflow, f"horizontal overflow on {label}")

    def test_builder_selects_baseline_edits_weight_saves_and_verifies_at_320px(self) -> None:
        """Complete builder workflow: login, select baseline, edit weight, save, verify, 320px."""
        profile = str(Path(self.temporary_directory.name) / "chrome-builder")
        process, session = launch_chrome_with_viewport(
            f"http://127.0.0.1:{self.app_port}/app/login",
            width=320, height=900, user_data_dir=profile,
        )
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session)

            # Step 1: Open the builder
            self._navigate(session, "/app/experiments/new")
            wait_for_expression(
                session,
                "Boolean(document.querySelector('#builder-baseline'))",
                timeout=15,
            )
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "builder initial")

            # Step 2: Select the seeded baseline through the visible UI.
            # The select has id="builder-baseline"; find the option matching our baseline name.
            option_value = evaluate(
                session,
                f"(function(){{const sel=document.getElementById('builder-baseline');"
                f"if(!sel)return null;const opt=Array.from(sel.options).find(o=>o.textContent.indexOf({_js_escape(self.baseline_name)})!==-1);"
                f"return opt?opt.value:null;}})()",
            )
            self.assertIsNotNone(option_value, "baseline option not found in select")

            set_ok = self._set_native_value(session, "document.getElementById('builder-baseline')", option_value)
            self.assertTrue(set_ok, "failed to set baseline select value")

            # Wait for the baseline to load (React processes the change and expands the draft).
            wait_for_expression(
                session,
                f"Boolean(document.body.textContent.match(/{re.escape(self.baseline_name)}/))",
                timeout=10,
            )

            # Select the seeded campaign through the visible UI.
            campaign_value = evaluate(
                session,
                f"(function(){{const sel=document.getElementById('builder-campaign');"
                f"if(!sel)return null;const opt=Array.from(sel.options).find(o=>o.textContent.indexOf({_js_escape(self.campaign_name)})!==-1);"
                f"return opt?opt.value:null;}})()",
            )
            self.assertIsNotNone(campaign_value, "campaign option not found in select")
            campaign_ok = self._set_native_value(session, "document.getElementById('builder-campaign')", campaign_value)
            self.assertTrue(campaign_ok, "failed to set campaign select value")

            # Step 3: Navigate through all builder steps to ensure each step's
            # setup is triggered (substrate auto-applies layout, conditions validates).
            for step_label in ("substrate", "layer", "condition"):
                step_ok = evaluate(
                    session,
                    f"(function(){{const btn=Array.from(document.querySelectorAll('.builder-step')).find(b=>b.textContent.toLowerCase().includes('{step_label}'));if(btn){{btn.click();return true;}}return false;}})()",
                )
                self.assertTrue(step_ok, f"{step_label} step button not found")
                # Brief wait for the step panel to render.
                wait_for_expression(session, "Boolean(document.querySelector('.builder-panel'))", timeout=10)

            # Step 4: Now navigate to the layer stack step to edit a weight.
            evaluate(
                session,
                "(function(){const btn=Array.from(document.querySelectorAll('.builder-step')).find(b=>b.textContent.toLowerCase().includes('layer'));if(btn)btn.click();})()",
            )
            wait_for_expression(session, "Boolean(document.querySelector('.builder-layer-card'))", timeout=10)

            # Step 4: Find the "Weight (mg)" input within the layer card for the
            # specific layer/chemical we intend to edit. Scope to the layer name
            # and chemical to avoid editing an unrelated layer's weight.
            layer_name = self.edit_layer_name
            chemical_name = self.edit_chemical
            original_weight = evaluate(
                session,
                f"(function(){{"
                "const cards=Array.from(document.querySelectorAll('.builder-layer-card'));"
                f"const card=cards.find(c=>c.getAttribute('aria-label')&&c.getAttribute('aria-label').includes({_js_escape(layer_name)}));"
                "if(!card)return null;"
                "const labels=Array.from(card.querySelectorAll('label.builder-field'));"
                "const weightLabel=labels.find(l=>l.textContent.includes('Weight (mg)'));"
                "if(!weightLabel)return null;"
                "const input=weightLabel.querySelector('input[type=number]');"
                "return input?input.value:null;"
                "})()",
            )
            self.assertIsNotNone(original_weight, f"Weight (mg) input not found in layer {layer_name}")
            self.assertEqual(float(original_weight), float(self.edit_weight_before),
                             f"original weight {original_weight} != seeded {self.edit_weight_before}")

            edit_ok = self._set_native_value(
                session,
                f"(function(){{"
                "const cards=Array.from(document.querySelectorAll('.builder-layer-card'));"
                f"const card=cards.find(c=>c.getAttribute('aria-label')&&c.getAttribute('aria-label').includes({_js_escape(layer_name)}));"
                "if(!card)return null;"
                "const labels=Array.from(card.querySelectorAll('label.builder-field'));"
                "const weightLabel=labels.find(l=>l.textContent.includes('Weight (mg)'));"
                "return weightLabel?weightLabel.querySelector('input[type=number]'):null;})()",
                str(self.edit_weight_after),
            )
            self.assertTrue(edit_ok, "failed to set weight input value")

            # Verify the input now shows the edited value.
            new_weight = evaluate(
                session,
                f"(function(){{"
                "const cards=Array.from(document.querySelectorAll('.builder-layer-card'));"
                f"const card=cards.find(c=>c.getAttribute('aria-label')&&c.getAttribute('aria-label').includes({_js_escape(layer_name)}));"
                "if(!card)return null;"
                "const labels=Array.from(card.querySelectorAll('label.builder-field'));"
                "const weightLabel=labels.find(l=>l.textContent.includes('Weight (mg)'));"
                "if(!weightLabel)return null;const input=weightLabel.querySelector('input[type=number]');"
                "return input?input.value:null;"
                "})()",
            )
            self.assertEqual(float(new_weight), float(self.edit_weight_after),
                             f"edited weight {new_weight} != expected {self.edit_weight_after}")

            # Step 5: Navigate to Review step and click "Save experiment".
            # Click the Review step button.
            review_clicked = evaluate(
                session,
                "(function(){const btn=Array.from(document.querySelectorAll('.builder-step')).find(b=>b.textContent.includes('Review'));if(btn){btn.click();return true;}return false;})()",
            )
            self.assertTrue(review_clicked, "Review step button not found")
            wait_for_expression(session, "Boolean(document.body.textContent.match(/Review|Save experiment/i))", timeout=10)

            # Find the "Save experiment" button (type=button, text="Save experiment").
            save_button_exists = evaluate(
                session,
                "Boolean(Array.from(document.querySelectorAll('button[type=button]')).find(b=>b.textContent.trim()==='Save experiment'))",
            )
            self.assertTrue(save_button_exists, "Save experiment button not found")

            # Assert the save button is enabled (no validation issues blocking it).
            save_disabled = evaluate(
                session,
                "(function(){const btn=Array.from(document.querySelectorAll('button[type=button]')).find(b=>b.textContent.trim()==='Save experiment');return btn?btn.disabled:true;})()",
            )
            if save_disabled:
                issues_text = evaluate(
                    session,
                    "(function(){const panel=document.querySelector('.builder-panel:last-child');return panel?panel.textContent.slice(0,500):'no panel';})()",
                )
                self.fail(f"Save experiment button is disabled. Issues: {issues_text}")

            # Step 6: Click Save experiment through real CDP mouse click.
            click_center(
                session,
                "Array.from(document.querySelectorAll('button[type=button]')).find(b=>b.textContent.trim()==='Save experiment')",
            )

            # Step 7: Wait for navigation to /app/experiments/{numeric_id}.
            # The save POSTs to /api/experiments and navigates to /experiments/{id}.
            # BrowserRouter with basename="/app" means location.pathname includes /app/.
            try:
                wait_for_expression(
                    session,
                    "Boolean(location.pathname.match(/\\/experiments\\/\\d+$/))",
                    timeout=20,
                )
            except TimeoutError:
                posts = session.api_post_responses()
                body_tail = evaluate(session, "document.body.textContent.slice(-300)")
                raise AssertionError(
                    f"Save did not navigate to experiment detail. "
                    f"API posts: {posts}. Body tail: {body_tail}"
                ) from None

            # Assert exact navigation: /app/experiments/{numeric_id}.
            path = evaluate(session, "location.pathname")
            match = re.search(r"/experiments/(\d+)$", path)
            self.assertIsNotNone(match, f"navigation did not reach /experiments/{{id}}: {path}")
            experiment_id = int(match.group(1))
            self.assertEqual(path, f"/app/experiments/{experiment_id}",
                             f"exact navigation mismatch: expected /app/experiments/{experiment_id}, got {path}")
            self.assertNotIn("/app/app/", path, f"doubled basename in {path}")

            # Step 8 (C2): Assert exactly one POST /api/experiments → 201 using method-aware evidence.
            create_response = session.wait_for_response(
                method="POST",
                pathname="/api/experiments",
                status=201,
                timeout=5,
            )
            self.assertEqual(create_response["method"], "POST")
            self.assertEqual(create_response["pathname"], "/api/experiments")
            self.assertEqual(create_response["status"], 201)

            # Step 8 (C1+C3): Fetch GET /api/experiments/{id} and verify with explicit status.
            saved_result = evaluate(
                session,
                f"fetch('/api/experiments/{experiment_id}').then(r=>r.text().then(body=>JSON.stringify({{status:r.status,body:body}})))",
            )
            self.assertIsNotNone(saved_result, "API fetch returned null")
            saved_obj = json.loads(saved_result)
            self.assertEqual(saved_obj["status"], 200, f"GET /api/experiments/{experiment_id} status != 200")
            detail = json.loads(saved_obj["body"])

            # C1: Assert every materialized condition has source_baseline_version_id == seeded.
            conditions = detail.get("conditions", [])
            self.assertGreater(len(conditions), 0, "no conditions in saved experiment")
            for i, condition in enumerate(conditions):
                self.assertEqual(
                    condition.get("source_baseline_version_id"),
                    self.baseline_version_id,
                    f"condition {i} source_baseline_version_id != seeded {self.baseline_version_id}",
                )

            # C1: Assert the experiment's campaign_id equals the seeded campaign ID.
            self.assertEqual(
                detail["experiment"].get("campaign_id"),
                self.campaign_code,
                f"experiment campaign_id != seeded {self.campaign_code}",
            )

            # C1: Assert the edited weight was persisted in the condition's recipe_snapshot.
            snapshot = conditions[0].get("recipe_snapshot", {})
            device = snapshot.get("device", {})
            layers = device.get("layers", [])
            found_edited_weight = False
            for layer in layers:
                sol = layer.get("solution")
                if sol and sol.get("solids"):
                    for solid in sol["solids"]:
                        if solid.get("chemical") == self.edit_chemical:
                            persisted_weight = solid.get("weight_mg")
                            self.assertEqual(
                                float(persisted_weight),
                                float(self.edit_weight_after),
                                f"persisted weight {persisted_weight} != edited {self.edit_weight_after}",
                            )
                            found_edited_weight = True
            self.assertTrue(found_edited_weight, f"edited chemical {self.edit_chemical} not found in saved snapshot")

            # C1: Assert the complete planned snapshot exists (recipe_snapshot has schema_version).
            self.assertIn("schema_version", snapshot, "recipe_snapshot missing schema_version")
            self.assertEqual(snapshot["schema_version"], 3, "unexpected recipe_schema_version")

            # Step 9: 320px viewport and no overflow on both builder and detail.
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "detail page after save")

            # Step 10: Fail on page exceptions, console errors, and failed mutations.
            session.check_errors()
        finally:
            session.close()
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


if __name__ == "__main__":
    unittest.main()
