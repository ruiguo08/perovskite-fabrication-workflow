"""Real-browser acceptance tests for the Phase 3 React result upload and analysis.

Drives the production React bundle (served from ``src/web/static-app``) inside
headless Chrome with a forced 320px layout viewport, using the CDP driver
(``tests/cdp_driver.py``). The file input is set through the genuine CDP
``DOM.setFileInputFiles`` command so React receives a real FileList.
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

from tests.layout_fixtures import seed_standard_layouts
from web import create_app
from web.repository import BatchStatus, ExecutionStatus, PreparationStatus, UserRole

from tests.cdp_driver import (
    click_until,
    evaluate,
    launch_chrome_with_viewport,
    set_file_input,
    wait_for_expression,
)
from tests.test_browser_builder import chrome_path

ADMIN_USERNAME = "results-admin"
ADMIN_PASSWORD = "Results administrator password 2026!"
STUDENT_USERNAME = "results-student"
STUDENT_PASSWORD = "Results student password 2026!"
OTHER_USERNAME = "results-other"
OTHER_PASSWORD = "Results other password 2026!"


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _js_escape(value: object) -> str:
    return json.dumps(value)


def multi_device_csv(currents: list[float]) -> str:
    rows = [[], [], [], [], []]
    for trace_index, current in enumerate(currents, start=1):
        device_index = (trace_index + 1) // 2
        direction = "Forward" if trace_index % 2 else "Reverse"
        rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        rows[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        rows[2].extend(["Name", f"A{device_index:03d} Channel 1.{direction}", "0", "-2", str(-current), "", ""])
        rows[3].extend(["", "", "0.5", "-2", str(-current), "", ""])
        rows[4].extend(["", "", "1", "0", "0", "", ""])
    return "\n".join(",".join(row) for row in rows) + "\n"


@unittest.skipIf(chrome_path() is None and not os.environ.get("CI"), "install Google Chrome to run browser tests")
class ResultBrowserTests(unittest.TestCase):
    """Verify the React result upload, assignment, and analysis flow at 320px."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        database_path = Path(cls.temporary_directory.name) / "results-browser.sqlite3"
        cls.app = create_app(
            database_path,
            secure_cookies=False,
            _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
        )
        cls.csv_path = Path(cls.temporary_directory.name) / "jv-multi.csv"
        cls.csv_path.write_text(multi_device_csv([20.0, 20.0, 21.0, 21.0]), encoding="utf-8")

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
            seed_standard_layouts(client)

            def logout() -> None:
                response = client.post("/api/auth/logout")
                assert response.status_code == 204, response.text
                client.headers.pop("X-CSRF-Token", None)

            def owned_released_experiment(username: str, password: str, code: str) -> int:
                from perovskite_bo import deposition_recipe_from_process
                from tests.test_web_app import complete_guided_setup

                device_recipe, deposition_process = complete_guided_setup()
                for group in device_recipe["experimental_groups"]:
                    if group["kind"] == "target":
                        group["adjustments"] = []
                        group["layers"] = [dict(layer) for layer in device_recipe["layers"]]
                        group["deposition_process"] = json.loads(json.dumps(deposition_process))
                logout()
                login(ADMIN_USERNAME, ADMIN_PASSWORD)
                baseline = client.post(
                    "/api/baselines",
                    json={
                        "name": f"Results baseline {code}",
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
                        "source_baseline_version_id": baseline.json()["current_version_id"],
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
            for username, display, password, role in (
                (STUDENT_USERNAME, "Results Student", STUDENT_PASSWORD, "student"),
                (OTHER_USERNAME, "Results Other", OTHER_PASSWORD, "student"),
            ):
                created = client.post(
                    "/api/users",
                    json={
                        "username": username,
                        "display_name": display,
                        "password": password,
                        "role": role,
                    },
                )
                assert created.status_code == 201, created.text

            cls.experiment_id = owned_released_experiment(
                STUDENT_USERNAME, STUDENT_PASSWORD, "results-student"
            )
            cls.other_experiment_id = owned_released_experiment(
                OTHER_USERNAME, OTHER_PASSWORD, "results-other"
            )

            repository = cls.app.state.repository
            users = asyncio.run(repository.list_users())
            cls.student_id = next(r.id for r in users if r.username == STUDENT_USERNAME)
            cls.other_id = next(r.id for r in users if r.username == OTHER_USERNAME)

            cls.batch = asyncio.run(
                repository.create_fabrication_batch(cls.experiment_id, actor_user_id=cls.student_id)
            )
            for status in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                asyncio.run(
                    repository.update_fabrication_batch_status(
                        cls.batch.id, status, actor_user_id=cls.student_id, client_ip="127.0.0.1"
                    )
                )
            # Complete the batch so result-CSV assignment can proceed: drive
            # preparations/executions terminal, record actual counts (the CSV
            # parses two substrates) and a shortfall deviation per condition.
            for preparation in asyncio.run(
                repository.list_solution_preparations(cls.batch.id)
            ):
                asyncio.run(
                    repository.update_solution_preparation(
                        preparation.id,
                        status=PreparationStatus.DISCARDED,
                        fabrication_batch_id=cls.batch.id,
                        actor_user_id=cls.student_id,
                    )
                )
            for execution in asyncio.run(
                repository.list_process_executions(cls.batch.id)
            ):
                asyncio.run(
                    repository.update_process_execution(
                        execution.id,
                        status=ExecutionStatus.CANCELLED,
                        fabrication_batch_id=cls.batch.id,
                        actor_user_id=cls.student_id,
                    )
                )
            batch_conditions = asyncio.run(
                repository.get_fabrication_batch_conditions(cls.batch.id)
            )
            actual_counts = {}
            shortfall_deviations = []
            for condition in batch_conditions:
                actual_counts[condition.id] = 1
                shortfall_deviations.append(
                    (condition.id, "Browser test: one substrate measured per condition; planned count was higher.")
                )
            asyncio.run(
                repository.update_fabrication_batch_status(
                    cls.batch.id,
                    BatchStatus.COMPLETED,
                    actor_user_id=cls.student_id,
                    client_ip="127.0.0.1",
                    actual_substrate_counts=actual_counts,
                    shortfall_deviations=shortfall_deviations,
                )
            )
            cls.other_batch = asyncio.run(
                repository.create_fabrication_batch(cls.other_experiment_id, actor_user_id=cls.other_id)
            )
            for status in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                asyncio.run(
                    repository.update_fabrication_batch_status(
                        cls.other_batch.id, status, actor_user_id=cls.other_id, client_ip="127.0.0.1"
                    )
                )

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
            raise RuntimeError("results browser test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.server_thread.join(timeout=5)
        cls.temporary_directory.cleanup()

    def _open(self, path: str, user_data_dir: str) -> tuple[object, object]:
        url = f"http://127.0.0.1:{self.app_port}{path}"
        return launch_chrome_with_viewport(url, width=320, height=900, user_data_dir=user_data_dir)

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
        self.assertEqual(int(status), 200, f"login failed for {username}")
        base_url = f"http://127.0.0.1:{self.app_port}/"
        cookies = get_cookies(session, base_url)
        self.assertIsNotNone(
            next((c for c in cookies if c.get("name") == "perovskite_session"), None),
            "session cookie not set after login",
        )

    def _navigate(self, session: object, path: str) -> None:
        evaluate(session, f"location.href = {_js_escape(path)}")
        wait_for_expression(session, "Boolean(document.querySelector('#root'))")

    def _assert_viewport(self, session: object, expected: int) -> None:
        inner = evaluate(session, "window.innerWidth")
        client = evaluate(session, "document.documentElement.clientWidth")
        diagnostic = (
            f"window.innerWidth={inner}px, "
            f"document.documentElement.clientWidth={client}px, expected {expected}px"
        )
        self.assertEqual(int(inner), expected, diagnostic)
        self.assertEqual(int(client), expected, diagnostic)

    def _assert_no_overflow(self, session: object, label: str) -> None:
        overflow = evaluate(
            session,
            "document.documentElement.scrollWidth > document.documentElement.clientWidth",
        )
        self.assertFalse(overflow, f"horizontal overflow on {label}")

    def _set_select(self, session: object, expression: str, value: str) -> None:
        evaluate(
            session,
            f"(function() {{ const el = ({expression}); "
            "const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set; "
            f"setter.call(el, {_js_escape(value)}); el.dispatchEvent(new Event('change', {{bubbles: true}})); return true; }})()",
        )

    def _click_real(self, session: object, expression: str) -> None:
        from tests.cdp_driver import click_center

        click_center(session, expression)

    def test_student_uploads_assigns_and_views_results_at_320px(self) -> None:
        profile = str(Path(self.temporary_directory.name) / "chrome-results")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login(session, STUDENT_USERNAME, STUDENT_PASSWORD)

            # Upload page.
            self._navigate(session, f"/app/experiments/{self.experiment_id}/upload")
            wait_for_expression(session, "Boolean(document.querySelector('input[type=file]'))")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "upload page")

            # Genuine file selection through CDP DOM.setFileInputFiles.
            set_file_input(session, "document.querySelector('input[type=file]')", str(self.csv_path))
            wait_for_expression(session, "Boolean(document.querySelector('input[type=file]').files.length)")

            # Choose the eligible (in_progress) batch and submit through the React form.
            batch_select = (
                f"Array.from(document.querySelectorAll('select option')).find(o => "
                f"o.textContent.indexOf({_js_escape(self.batch.batch_code)}) !== -1)?.parentElement"
            )
            option_value = evaluate(
                session,
                f"(function() {{ const opt = Array.from(document.querySelectorAll('select option')).find(o => "
                f"o.textContent.indexOf({_js_escape(self.batch.batch_code)}) !== -1); return opt ? opt.value : null; }})()",
            )
            self.assertIsNotNone(option_value, "eligible batch not in the select")
            self._set_select(session, "document.querySelector('select')", option_value)
            self._click_real(session, "document.querySelector('button[type=submit]')")

            # Navigation to the result detail route.
            wait_for_expression(session, "Boolean(document.querySelector('[data-result-detail]'))")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "result detail before assignment")

            # Assignment form is visible (statistics not yet present).
            wait_for_expression(
                session,
                "Array.from(document.querySelectorAll('select')).some(s => s.getAttribute('aria-label') && s.getAttribute('aria-label').indexOf('Assign') !== -1)",
            )
            self._assert_no_overflow(session, "assignment form")

            # At the narrow viewport, exclusion thresholds and their action
            # group stack to the same panel width instead of drifting on
            # separate flex lines.
            exclusion_layout = evaluate(
                session,
                "(function() {"
                "const row = document.querySelector('.exclusion-presets');"
                "const actions = document.querySelector('.exclusion-presets__actions');"
                "if (!row || !actions) return null;"
                "const rowRect = row.getBoundingClientRect();"
                "const controls = [...row.querySelectorAll(':scope > .form-field'), actions];"
                "return controls.map(element => { const rect = element.getBoundingClientRect(); "
                "return {left: rect.left - rowRect.left, right: rowRect.right - rect.right}; });"
                "})()",
            )
            self.assertIsNotNone(exclusion_layout, "exclusion action group is missing")
            for bounds in exclusion_layout:
                self.assertLessEqual(abs(float(bounds["left"])), 1)
                self.assertLessEqual(abs(float(bounds["right"])), 1)

            # Complete every substrate assignment through the React controls.
            substrate_ids = evaluate(
                session,
                "Array.from(document.querySelectorAll('[aria-label^=\"Assign \"]')).map(s => s.getAttribute('aria-label').replace('Assign ', '').replace(' to', ''))",
            )
            self.assertEqual(len(substrate_ids), 2, f"expected 2 substrates, got {substrate_ids}")
            groups = evaluate(
                session,
                "Array.from(document.querySelectorAll('select option')).filter(o => o.value && o.value !== '').map(o => ({value: o.value, text: o.textContent}))",
            )
            self.assertGreaterEqual(len(groups), 2)
            self._set_select(
                session,
                f"document.querySelector('[aria-label=\"Assign {substrate_ids[0]} to\"]')",
                groups[0]["value"],
            )
            self._set_select(
                session,
                f"document.querySelector('[aria-label=\"Assign {substrate_ids[1]} to\"]')",
                groups[1]["value"],
            )

            # Submit assignments through the real POST endpoint via the form.
            evaluate(session, "document.querySelector('form').requestSubmit()")
            # Saving switches the page to the figures section; the statistics
            # panel lives behind the Statistics section button.
            wait_for_expression(
                session,
                "Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics')) && !Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics')).disabled",
            )
            self._click_real(
                session,
                "Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics'))",
            )
            wait_for_expression(session, "Boolean(document.body.textContent.match(/Directional group statistics/))")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "statistics and charts")

            # Select all devices and plot their JV curves through the React
            # controls. The JV chart lives in the figures section, so switch
            # back from statistics first.
            self._click_real(
                session,
                "Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Figures'))",
            )
            wait_for_expression(
                session,
                "Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === 'Select all' && b.getBoundingClientRect().width > 0)",
            )
            click_until(
                session,
                "Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Select all')",
                verify="!Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Plot selected').disabled",
            )
            click_until(
                session,
                "Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Plot selected')",
                verify="Boolean(document.querySelector('[role=img][aria-label*=\"J-V curves\"]'))",
            )
            # JV chart SVG renders and no more than 12 devices selected.
            chart_count = evaluate(session, "document.querySelectorAll('[role=img][aria-label*=\"J-V curves\"]').length")
            self.assertLessEqual(int(chart_count), 12, f"too many JV charts: {chart_count}")

            # Navigate away to the global results list and back — proving persistence from the server.
            self._navigate(session, "/app/results")
            wait_for_expression(
                session,
                f"Array.from(document.querySelectorAll('[data-result-row]')).some(el => el.textContent.indexOf('jv-multi.csv') !== -1)",
            )
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "global results list")
            # The global list links back to the result.
            self._click_real(session, "document.querySelector('[data-result-row] a')")
            wait_for_expression(session, "Boolean(document.querySelector('[data-result-detail]'))")
            # A saved analysis opens on the figures section; switch to statistics.
            wait_for_expression(
                session,
                "Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics')) && !Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics')).disabled",
            )
            self._click_real(
                session,
                "Array.from(document.querySelectorAll('.result-section-nav__button')).find(b => b.textContent.trim().startsWith('Statistics'))",
            )
            wait_for_expression(session, "Boolean(document.body.textContent.match(/Directional group statistics/))")
            session.check_errors()
        finally:
            session.close()
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    def test_student_receives_404_for_another_students_result(self) -> None:
        # Upload a result as the other student, then try to view it as the first student.
        with TestClient(self.app) as client:
            csrf = client.get("/api/auth/login-csrf").json()["login_csrf_token"]
            client.post(
                "/api/auth/login",
                json={"username": OTHER_USERNAME, "password": OTHER_PASSWORD, "login_csrf": csrf},
            )
            client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")
            uploaded = client.post(
                f"/api/experiments/{self.other_experiment_id}/results",
                files={"result_file": ("other.csv", self.csv_path.read_bytes(), "text/csv")},
                data={"fabrication_batch_id": str(self.other_batch.id)},
            )
            assert uploaded.status_code == 201, uploaded.text
            other_result_id = int(uploaded.json()["id"])

        profile = str(Path(self.temporary_directory.name) / "chrome-404")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login(session, STUDENT_USERNAME, STUDENT_PASSWORD)
            self._navigate(session, f"/app/results/{other_result_id}")
            wait_for_expression(
                session,
                "document.body.textContent.indexOf('Unable to load result') !== -1",
            )
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
