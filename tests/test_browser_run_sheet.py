"""Real-browser acceptance tests for the Phase 3 React fabrication run sheet.

Drives the production React bundle (served from ``src/web/static-app``) inside
headless Chrome with a forced 320px layout viewport, using a minimal Chrome
DevTools Protocol driver (``tests/cdp_driver.py``). Interactions are performed
from Python via CDP ``Runtime.evaluate`` so the tests genuinely exercise the
bundle, the VCD snapshot PATCH validation, and the 320px responsive layout.
"""

from __future__ import annotations
import os

import asyncio
import json
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

from tests.cdp_driver import evaluate, launch_chrome_with_viewport, wait_for_expression
from tests.layout_fixtures import seed_standard_layouts
from tests.test_browser_builder import chrome_path

ADMIN_USERNAME = "run-sheet-admin"
ADMIN_PASSWORD = "Run sheet administrator password 2026!"
STUDENT_USERNAME = "run-sheet-student"
STUDENT_PASSWORD = "Run sheet student password 2026!"
OTHER_USERNAME = "run-sheet-other"
OTHER_PASSWORD = "Run sheet other password 2026!"


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _js_escape(value: object) -> str:
    return json.dumps(value)


@unittest.skipIf(chrome_path() is None and not os.environ.get("CI"), "install Google Chrome to run browser tests")
class RunSheetBrowserTests(unittest.TestCase):
    """Verify the React batch list and run sheet in a real browser at 320px."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        database_path = Path(cls.temporary_directory.name) / "run-sheet.sqlite3"
        cls.app = create_app(
            database_path,
            secure_cookies=False,
            _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
        )

        # The CDP driver renders the SPA in the top document (no iframe, no
        # inline scripts), so the real bundle and its own bundled scripts are
        # allowed by the production CSP. No security-header relaxation is
        # needed; the SPA is served exactly as in production.

        with TestClient(cls.app) as client:
            def login(username: str, password: str) -> None:
                csrf = client.get("/api/auth/login-csrf")
                assert csrf.status_code == 200, csrf.text
                token = csrf.json()["login_csrf_token"]
                logged_in = client.post(
                    "/api/auth/login",
                    json={
                        "username": username,
                        "password": password,
                        "login_csrf": token,
                    },
                )
                assert logged_in.status_code == 200, logged_in.text
                client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")

            def logout() -> None:
                logged_out = client.post("/api/auth/logout")
                assert logged_out.status_code == 204, logged_out.text
                client.headers.pop("X-CSRF-Token", None)

            def owned_released_experiment(
                username: str,
                password: str,
                campaign_code: str,
            ) -> int:
                from perovskite_bo import deposition_recipe_from_process
                from tests.test_web_app import complete_guided_setup

                device_recipe, deposition_process = complete_guided_setup()
                for group in device_recipe["experimental_groups"]:
                    if group["kind"] == "target":
                        group["adjustments"] = []
                        group["layers"] = [
                            dict(layer) for layer in device_recipe["layers"]
                        ]
                        group["deposition_process"] = json.loads(
                            json.dumps(deposition_process)
                        )
                logout()
                login(ADMIN_USERNAME, ADMIN_PASSWORD)
                baseline = client.post(
                    "/api/baselines",
                    json={
                        "name": f"Run sheet baseline {campaign_code}",
                        "device_recipe": device_recipe,
                        "deposition_process": deposition_process,
                    },
                )
                assert baseline.status_code == 201, baseline.text
                logout()
                login(username, password)
                created = client.post(
                    "/api/experiments",
                    json={
                        "recipe": {
                            **deposition_recipe_from_process(deposition_process),
                            "device_recipe": device_recipe,
                        },
                        "source_baseline_version_id": baseline.json()[
                            "current_version_id"
                        ],
                        "condition_plans": [
                            {
                                "group_id": group["group_id"],
                                "role": group["kind"],
                                "device_layout_code": "15x15_dual_005",
                                "planned_substrate_count": 3,
                            }
                            for group in device_recipe["experimental_groups"]
                        ],
                    },
                )
                assert created.status_code == 201, created.text
                experiment_id = int(created.json()["id"])
                submitted = client.patch(
                    f"/api/experiments/{experiment_id}/plan-status",
                    json={"status": "pending_approval"},
                )
                assert submitted.status_code == 204, submitted.text
                logout()
                login(ADMIN_USERNAME, ADMIN_PASSWORD)
                approved = client.patch(
                    f"/api/experiments/{experiment_id}/plan-status",
                    json={"status": "approved"},
                )
                assert approved.status_code == 204, approved.text
                released = client.patch(
                    f"/api/experiments/{experiment_id}/plan-status",
                    json={"status": "released"},
                )
                assert released.status_code == 204, released.text
                return experiment_id

            login(ADMIN_USERNAME, ADMIN_PASSWORD)
            seed_standard_layouts(client)
            created_student = client.post(
                "/api/users",
                json={
                    "username": STUDENT_USERNAME,
                    "display_name": "Run Sheet Student",
                    "password": STUDENT_PASSWORD,
                    "role": "student",
                },
            )
            assert created_student.status_code == 201, created_student.text
            created_other = client.post(
                "/api/users",
                json={
                    "username": OTHER_USERNAME,
                    "display_name": "Run Sheet Other",
                    "password": OTHER_PASSWORD,
                    "role": "student",
                },
            )
            assert created_other.status_code == 201, created_other.text

            cls.experiment_id = owned_released_experiment(
                STUDENT_USERNAME,
                STUDENT_PASSWORD,
                "run-sheet-student",
            )
            cls.other_experiment_id = owned_released_experiment(
                OTHER_USERNAME,
                OTHER_PASSWORD,
                "run-sheet-other",
            )

            repository = cls.app.state.repository
            users = asyncio.run(repository.list_users())
            cls.student_id = next(
                record.id for record in users if record.username == STUDENT_USERNAME
            )
            cls.other_id = next(
                record.id for record in users if record.username == OTHER_USERNAME
            )
            cls.batch = asyncio.run(
                repository.create_fabrication_batch(
                    cls.experiment_id,
                    actor_user_id=cls.student_id,
                )
            )
            cls.other_batch = asyncio.run(
                repository.create_fabrication_batch(
                    cls.other_experiment_id,
                    actor_user_id=cls.other_id,
                )
            )
            executions = asyncio.run(
                repository.list_process_executions(cls.batch.id)
            )
            memberships = [
                asyncio.run(repository.list_process_execution_members(execution.id))
                for execution in executions
            ]
            if not any(len(members) >= 2 for members in memberships):
                raise AssertionError(
                    "the run-sheet browser seed requires an execution with "
                    "two or more members"
                )
            preparations = asyncio.run(
                repository.list_solution_preparations(cls.batch.id)
            )
            preparation_uses = [
                asyncio.run(repository.list_solution_preparation_uses(preparation.id))
                for preparation in preparations
            ]
            if not any(len(uses) >= 2 for uses in preparation_uses):
                raise AssertionError(
                    "the run-sheet browser seed requires a preparation with "
                    "two or more uses"
                )
            vcd_executions = [
                execution
                for execution in executions
                if execution.method == "vcd"
            ]
            if not vcd_executions:
                raise AssertionError(
                    "the run-sheet browser seed requires a genuine VCD "
                    "execution snapshot"
                )
            non_vcd = [execution for execution in executions if execution.method != "vcd"]
            first_execution = non_vcd[0]
            asyncio.run(
                repository.create_process_execution(
                    fabrication_batch_id=cls.batch.id,
                    method=first_execution.method,
                    layer_role=first_execution.layer_role,
                    layer_type=first_execution.layer_type,
                    layer_name=first_execution.layer_name,
                    planned_process_snapshot=first_execution.planned_process_snapshot,
                    actor_user_id=cls.student_id,
                )
            )

        cls.app_port = available_port()
        config = uvicorn.Config(
            cls.app,
            host="127.0.0.1",
            port=cls.app_port,
            log_level="error",
        )
        cls.server = uvicorn.Server(config)
        cls.server.install_signal_handlers = lambda: None
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()
        deadline = time.monotonic() + 10
        while not cls.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not cls.server.started:
            raise RuntimeError("run sheet browser test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.server_thread.join(timeout=5)
        cls.temporary_directory.cleanup()

    def _open(self, path: str, user_data_dir: str) -> tuple[object, object]:
        url = f"http://127.0.0.1:{self.app_port}{path}"
        return launch_chrome_with_viewport(
            url,
            width=320,
            height=900,
            user_data_dir=user_data_dir,
        )

    def _login(self, session: object, username: str, password: str) -> None:
        from tests.cdp_driver import get_cookies

        csrf = evaluate(
            session,
            "fetch('/api/auth/login-csrf').then(r => r.json()).then(d => d.login_csrf_token)",
        )
        status = evaluate(
            session,
            (
                "fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, "
                f"body: JSON.stringify({{username: {_js_escape(username)}, password: {_js_escape(password)}, "
                "login_csrf: " + _js_escape(csrf) + "})}).then(r => r.status)"
            ),
        )
        self.assertEqual(int(status), 200)
        base_url = f"http://127.0.0.1:{self.app_port}/"
        cookies = get_cookies(session, base_url)
        session_cookie = next(
            (cookie for cookie in cookies if cookie.get("name") == "perovskite_session"),
            None,
        )
        self.assertIsNotNone(session_cookie, "session cookie not set after login")
        session_user = evaluate(
            session,
            "fetch('/api/session').then(r => r.json()).then(d => d.username)",
        )
        self.assertEqual(session_user, username, "session not established after login")

    def _navigate(self, session: object, path: str) -> None:
        evaluate(session, f"location.href = {_js_escape(path)}")
        wait_for_expression(session, "Boolean(document.querySelector('#root'))")
        wait_for_expression(session, "Boolean(document.querySelector('.shell'))")

    def test_admin_records_prep_split_deviation_vcd_and_transitions_at_320px(self) -> None:
        profile = str(Path(self.temporary_directory.name) / "chrome-admin")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login(session, ADMIN_USERNAME, ADMIN_PASSWORD)
            self._navigate(session, "/app/fabrication-batches")
            wait_for_expression(
                session,
                f"Array.from(document.querySelectorAll('[data-batch-row]')).some(el => el.textContent.indexOf({_js_escape(self.batch.batch_code)}) !== -1)",
            )
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "batch list")
            self._click_first_match(
                session,
                f"[data-batch-row] a[href*='batches/{self.batch.id}']",
            )
            try:
                wait_for_expression(
                    session,
                    "Boolean(document.querySelector('[data-run-sheet]'))",
                )
            except TimeoutError:
                path = evaluate(session, "location.pathname")
                body = evaluate(session, "document.body ? document.body.textContent.slice(0, 200) : 'no body'")
                raise AssertionError(
                    f"run sheet did not mount at {path}; body: {body}"
                ) from None
            self._assert_no_overflow(session, "run sheet")

            # Persistence-verified VCD edit through the real PATCH + validation.
            self._vcd_edit_and_verify_persistence(session)

            # Preparation actual recording.
            self._set_select(session, "[data-preparation] [data-actual-mode]", "entered")
            wait_for_expression(
                session,
                "Boolean(document.querySelector('[data-preparation] [data-snapshot-editor]'))",
            )
            self._set_number(session, "[data-preparation] input[type='number']", 4)
            self._click_real(session, "[data-preparation] [data-save-preparation]")
            self._wait_for_text(session, "Recorded")

            # Split a preparation with more than one use. Scope every interaction
            # to the specific card whose disclosure we open. The disclosure
            # click itself can be swallowed by a transient overlay, so re-click
            # until the member checkbox appears.
            split_card_expr = (
                "Array.from(document.querySelectorAll('[data-preparation]'))"
                ".find(c => Array.from(c.querySelectorAll('button'))"
                ".some(b => b.textContent.indexOf('Split preparation') !== -1))"
            )
            from tests.cdp_driver import click_until

            click_until(
                session,
                split_card_expr + " && Array.from(" + split_card_expr + ".querySelectorAll('button')).find(b => b.textContent.indexOf('Split preparation') !== -1)",
                verify=f"Boolean({split_card_expr} && {split_card_expr}.querySelector('[data-split-member]'))",
            )
            member_expr = split_card_expr + ".querySelector('[data-split-member]')"
            # Drive the checkbox with a real trusted mouse click so React's
            # controlled state updates. A fixed overlay (an auto-dismissing
            # toast from the previous save) or a re-render shift can swallow
            # the first click, so re-click until the checked state lands.
            click_until(
                session,
                member_expr,
                verify=f"Boolean({member_expr} && {member_expr}.checked)",
            )
            prep_count = int(
                evaluate(session, "document.querySelectorAll('[data-preparation]').length")
            )
            wait_for_expression(
                session,
                f"!{split_card_expr}.querySelector('[data-split-submit]').disabled",
                timeout=10,
            )
            self._click_real(
                session,
                split_card_expr + ".querySelector('[data-split-submit]')",
            )
            try:
                wait_for_expression(
                    session,
                    f"document.querySelectorAll('[data-preparation]').length > {prep_count}",
                )
            except TimeoutError:
                current = evaluate(
                    session,
                    "document.querySelectorAll('[data-preparation]').length",
                )
                posts = session.api_post_responses()
                session.check_errors()
                raise AssertionError(
                    f"split did not increase preparations from {prep_count} to {current}; "
                    f"api responses: {posts}"
                ) from None
                body = evaluate(
                    session,
                    "document.body.textContent.slice(-400)",
                )
                raise AssertionError(
                    f"preparation split did not complete; body tail: {body}"
                ) from None

            # Merge a non-VCD execution through the confirmation dialog.
            self._merge_execution_via_dialog(session)

            # Deviation targeting the batch.
            self._set_text(
                session,
                "[data-deviation-description]",
                "Browser integration deviation",
            )
            self._click_real(session, "[data-deviation-submit]")
            self._wait_for_text(session, "Browser integration deviation")

            # Transition draft -> ready.
            self._click_real(session, "[data-status-action='ready']")
            self._wait_for_text(session, "ready")
            self._assert_viewport(session, 320)
            session.check_errors()
        finally:
            session.close()
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def test_student_run_sheet_hides_the_cancel_action(self) -> None:
        profile = str(Path(self.temporary_directory.name) / "chrome-student")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login(session, STUDENT_USERNAME, STUDENT_PASSWORD)
            self._navigate(
                session,
                f"/app/experiments/{self.experiment_id}/batches/{self.batch.id}",
            )
            wait_for_expression(session, "Boolean(document.querySelector('[data-run-sheet]'))")
            has_cancel = evaluate(
                session,
                "Boolean(document.querySelector('[data-status-action=\"cancelled\"]'))",
            )
            self.assertFalse(has_cancel)
        finally:
            session.close()
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def test_student_run_sheet_hides_another_students_batch(self) -> None:
        profile = str(Path(self.temporary_directory.name) / "chrome-404")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login(session, STUDENT_USERNAME, STUDENT_PASSWORD)
            self._navigate(
                session,
                f"/app/experiments/{self.other_experiment_id}/batches/{self.other_batch.id}",
            )
            wait_for_expression(
                session,
                "document.body.textContent.indexOf('Unable to load run sheet') !== -1",
            )
        finally:
            session.close()
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    # ------------------------------------------------------------------
    # CDP interaction helpers
    # ------------------------------------------------------------------

    def _assert_viewport(self, session: object, expected: int) -> None:
        # Both measures must equal the forced 320px layout viewport: the true
        # window width and documentElement.clientWidth (scrollbars are hidden
        # by the CDP driver so the scrollbar deduction does not apply).
        inner = evaluate(session, "window.innerWidth")
        client = evaluate(session, "document.documentElement.clientWidth")
        diagnostic = (f"window.innerWidth={inner}px, "
                      f"document.documentElement.clientWidth={client}px, "
                      f"expected {expected}px")
        self.assertEqual(int(inner), expected, diagnostic)
        self.assertEqual(int(client), expected, diagnostic)

    def _assert_no_overflow(self, session: object, label: str) -> None:
        overflow = evaluate(
            session,
            "document.documentElement.scrollWidth > document.documentElement.clientWidth",
        )
        self.assertFalse(overflow, f"horizontal overflow on {label}")

    def _click(self, session: object, selector: str) -> None:
        """Synthetic click; used for simple buttons and disclosure toggles."""
        expression = self._resolve_element(selector)
        clicked = evaluate(
            session,
            f"(function() {{ const el = {expression}; if (!el) return false; el.click(); return true; }})()",
        )
        self.assertTrue(clicked, f"no element matched: {selector}")

    def _click_real(self, session: object, selector: str) -> None:
        """Trusted CDP mouse click; required for React controlled checkboxes."""
        from tests.cdp_driver import click_center

        click_center(session, self._resolve_element(selector))

    def _click_first_match(self, session: object, selector: str) -> None:
        clicked = evaluate(
            session,
            f"(function() {{ const el = document.querySelector({_js_escape(selector)}); if (!el) return false; el.click(); return true; }})()",
        )
        self.assertTrue(clicked, f"no element matched: {selector}")

    def _resolve_element(self, selector: str) -> str:
        """Return a JS expression resolving the target element.

        Plain CSS selectors are wrapped in querySelector; raw expressions
        (already element-returning) are used as-is.
        """
        if (
            selector.startswith("document")
            or selector.startswith("Array")
            or selector.startswith("(function")
        ):
            return selector
        return f"document.querySelector({_js_escape(selector)})"

    def _set_select(self, session: object, selector: str, value: str) -> None:
        set_value = (
            "(function() { const el = %s; "
            "const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; "
            "setter.call(el, %s); el.dispatchEvent(new Event('change', {bubbles: true})); return true; })()"
        )
        evaluate(session, set_value % (self._resolve_element(selector), _js_escape(value)))

    def _set_text(self, session: object, selector: str, value: str) -> None:
        set_value = (
            "(function() { const el = %s; "
            "const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; "
            "const setter = Object.getOwnPropertyDescriptor(proto, 'value').set; "
            "setter.call(el, %s); el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()"
        )
        evaluate(session, set_value % (self._resolve_element(selector), _js_escape(value)))

    def _check(self, session: object, selector: str) -> None:
        checked = evaluate(
            session,
            "(function() { const el = %s; if (!el) return false; "
            "const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked').set; "
            "setter.call(el, !el.checked); "
            "el.dispatchEvent(new Event('change', {bubbles: true})); "
            "el.dispatchEvent(new Event('click', {bubbles: true})); return true; })()"
            % self._resolve_element(selector),
        )
        self.assertTrue(checked, f"no element matched: {selector}")

    def _set_number(self, session: object, selector: str, value: float) -> None:
        set_value = (
            "(function() { const el = %s; "
            "const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; "
            "setter.call(el, %s); el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()"
        )
        evaluate(
            session,
            set_value % (self._resolve_element(selector), _js_escape(str(value))),
        )

    def _wait_for_text(self, session: object, text: str) -> None:
        wait_for_expression(
            session,
            f"document.body.textContent.indexOf({_js_escape(text)}) !== -1",
        )

    def _vcd_card_expr(self) -> str:
        return (
            "Array.from(document.querySelectorAll('[data-execution]'))"
            ".find(c => c.textContent.indexOf('vcd') !== -1)"
        )

    def _vcd_duration_input_expr(self) -> str:
        return (
            "(function() { const card = " + self._vcd_card_expr() + "; "
            "const label = Array.from(card.querySelectorAll('label')).find(l => l.textContent.indexOf('Duration (s)') !== -1); "
            "return label.querySelector('input'); })()"
        )

    def _vcd_edit_and_verify_persistence(self, session: object) -> None:
        self._set_select(
            session,
            self._vcd_card_expr() + ".querySelector('[data-actual-mode]')",
            "entered",
        )
        wait_for_expression(
            session,
            "Array.from(document.querySelectorAll('[data-execution]')).some(c => c.textContent.indexOf('vcd') !== -1 && Boolean(c.querySelector('[data-snapshot-editor]')))",
        )
        original = evaluate(session, "Number(" + self._vcd_duration_input_expr() + ".value)")
        edited = int(original) + 3
        self._set_number(session, self._vcd_duration_input_expr(), edited)
        self._click_real(
            session,
            self._vcd_card_expr() + ".querySelector('[data-save-execution]')",
        )
        self._wait_for_text(session, "Recorded")
        self._assert_no_overflow(session, "VCD editor")

        # Force a fresh server render: navigate to the list and back.
        self._click_first_match(session, "a[href*='fabrication-batches']")
        wait_for_expression(
            session,
            f"Array.from(document.querySelectorAll('[data-batch-row]')).some(el => el.textContent.indexOf({_js_escape(self.batch.batch_code)}) !== -1)",
        )
        self._click_first_match(
            session,
            f"[data-batch-row] a[href*='batches/{self.batch.id}']",
        )
        wait_for_expression(session, "Boolean(document.querySelector('[data-run-sheet]'))")
        self._set_select(
            session,
            self._vcd_card_expr() + ".querySelector('[data-actual-mode]')",
            "entered",
        )
        wait_for_expression(
            session,
            "Array.from(document.querySelectorAll('[data-execution]')).some(c => c.textContent.indexOf('vcd') !== -1 && Boolean(c.querySelector('[data-snapshot-editor]')))",
        )
        persisted = evaluate(session, "Number(" + self._vcd_duration_input_expr() + ".value)")
        self.assertEqual(
            int(persisted),
            edited,
            f"VCD edit did not persist after refetch: {persisted} !== {edited}",
        )

    def _merge_execution_via_dialog(self, session: object) -> None:
        candidate_expr = (
            "Array.from(document.querySelectorAll('[data-execution]')).find(c => {"
            "  if (c.textContent.indexOf('vcd') !== -1) return false;"
            "  const select = c.querySelector('[data-merge-source]');"
            "  return select && select.options.length > 1;"
            "})"
        )
        wait_for_expression(session, f"Boolean({candidate_expr})")
        exec_count = int(
            evaluate(session, "document.querySelectorAll('[data-execution]').length")
        )
        source_value = evaluate(
            session,
            f"(function() {{ const select = ({candidate_expr}).querySelector('[data-merge-source]'); return select.options[1].value; }})()",
        )
        self._set_select(
            session,
            candidate_expr + ".querySelector('[data-merge-source]')",
            source_value,
        )
        # Open an execution split disclosure alongside the merge control for the
        # expanded 320px overflow check.
        self._click(
            session,
            "Array.from(document.querySelectorAll('[data-execution] button')).find(b => b.textContent.indexOf('Split execution') !== -1)",
        )
        wait_for_expression(
            session,
            "Boolean(document.querySelector('[data-execution] [data-split-member]'))",
        )
        self._assert_no_overflow(session, "split + merge controls")
        self._click_real(session, candidate_expr + ".querySelector('[data-merge-submit]')")
        wait_for_expression(session, "Boolean(document.querySelector('[role=\"dialog\"]'))")
        dialog_text = evaluate(
            session,
            "document.querySelector('[role=\"dialog\"]').textContent",
        )
        self.assertIn("merged and deleted", dialog_text)
        self._click_real(
            session,
            "document.querySelector('[role=\"dialog\"] button:last-child')",
        )
        wait_for_expression(
            session,
            f"document.querySelectorAll('[data-execution]').length === {exec_count - 1}",
        )


if __name__ == "__main__":
    unittest.main()
