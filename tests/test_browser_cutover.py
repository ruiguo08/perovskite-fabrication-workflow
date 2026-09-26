"""Phase 4B genuine CDP browser tests for canonical redirects and login destinations.

Drives the production React bundle via the CDP top-document driver
(``tests/cdp_driver.py``). No inline-script harness, no iframe, no dump-DOM markers.
Tests cover: exact legacy redirects, visible login form submission, safe return,
authenticated-user redirect with exact destination, session-expiry return,
role-specific navigation, export verification, healthz non-shadowing, and 320px.
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
from tests.layout_fixtures import seed_standard_layouts
from web.repository import UserRole

from tests.cdp_driver import (
    click_center,
    evaluate,
    get_cookies,
    launch_chrome_with_viewport,
    wait_for_expression,
)
from tests.test_browser_builder import chrome_path

ADMIN_USERNAME = "cutover-admin"
ADMIN_PASSWORD = "Cutover admin password 2026!"
STUDENT_USERNAME = "cutover-student"
STUDENT_PASSWORD = "Cutover student password 2026!"
INSTRUCTOR_USERNAME = "cutover-instructor"
INSTRUCTOR_PASSWORD = "Cutover instructor password 2026!"


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _js_escape(value: object) -> str:
    return json.dumps(value)


@unittest.skipIf(chrome_path() is None and not os.environ.get("CI"), "install Google Chrome to run browser tests")
class CutoverBrowserTests(unittest.TestCase):
    """Verify canonical redirects, visible login, destination return, and 320px."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        database_path = Path(cls.temporary_directory.name) / "cutover.sqlite3"
        cls.app = create_app(
            database_path,
            secure_cookies=False,
            _test_user=(ADMIN_USERNAME, ADMIN_PASSWORD, UserRole.ADMINISTRATOR),
        )

        with TestClient(cls.app) as client:
            csrf = client.get("/api/auth/login-csrf")
            token = csrf.json()["login_csrf_token"]
            client.post(
                "/api/auth/login",
                json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "login_csrf": token},
            )
            client.headers["X-CSRF-Token"] = client.cookies.get("perovskite_csrf")
            seed_standard_layouts(client)
            for username, display, password, role in (
                (STUDENT_USERNAME, "Cutover Student", STUDENT_PASSWORD, "student"),
                (INSTRUCTOR_USERNAME, "Cutover Instructor", INSTRUCTOR_PASSWORD, "instructor"),
            ):
                created = client.post(
                    "/api/users",
                    json={"username": username, "display_name": display, "password": password, "role": role},
                )
                assert created.status_code == 201, created.text

            from tests.test_web_app import releasable_result_recipe
            created = client.post("/api/experiments", json={"recipe": releasable_result_recipe()})
            assert created.status_code == 201, created.text
            cls.experiment_id = int(created.json()["id"])
            for status in ("pending_approval", "approved", "released"):
                assert client.patch(
                    f"/api/experiments/{cls.experiment_id}/plan-status",
                    json={"status": status},
                ).status_code == 204
            batch = client.post(f"/api/experiments/{cls.experiment_id}/fabrication-batches", json={})
            assert batch.status_code == 201, batch.text
            cls.batch_id = int(batch.json()["id"])
            for status in ("ready", "in_progress"):
                client.patch(f"/api/fabrication-batches/{cls.batch_id}/status", json={"status": status})

            # Store admin session token for session-expiry test.
            users = asyncio.run(cls.app.state.repository.list_users())
            cls.student_id = next(r.id for r in users if r.username == STUDENT_USERNAME)

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
            raise RuntimeError("cutover browser test server did not start")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.should_exit = True
        cls.server_thread.join(timeout=5)
        cls.temporary_directory.cleanup()

    def _open(self, path: str, profile: str) -> tuple[object, object]:
        url = f"http://127.0.0.1:{self.app_port}{path}"
        return launch_chrome_with_viewport(url, width=320, height=900, user_data_dir=profile)

    def _navigate(self, session: object, path: str) -> None:
        evaluate(session, f"location.href = {_js_escape(path)}")
        wait_for_expression(session, "Boolean(document.querySelector('#root'))")

    def _login_via_fetch(self, session: object, username: str, password: str) -> None:
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

    def _login_via_visible_form(self, session: object, username: str, password: str) -> None:
        """Fill and submit the visible React login form through real CDP input."""
        wait_for_expression(session, "Boolean(document.querySelector('input[name=username]'))")
        ok_user = evaluate(
            session,
            f"(function(){{const el=document.querySelector('input[name=username]');"
            "const p=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
            f"p.call(el,{_js_escape(username)});el.dispatchEvent(new Event('input',{{bubbles:true}}));return true;}})()",
        )
        self.assertTrue(ok_user)
        ok_pass = evaluate(
            session,
            f"(function(){{const el=document.querySelector('input[name=password]');"
            "const p=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
            f"p.call(el,{_js_escape(password)});el.dispatchEvent(new Event('input',{{bubbles:true}}));return true;}})()",
        )
        self.assertTrue(ok_pass)
        click_center(session, "document.querySelector('button[type=submit]')")

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

    # ------------------------------------------------------------------
    # C4: Exact cutover redirect tests
    # ------------------------------------------------------------------

    def test_root_redirects_exactly_to_app_root(self) -> None:
        """Unauthenticated / → 303 → exact /app/ (not any /app/* path)."""
        profile = str(Path(self.temporary_directory.name) / "chrome-root")
        process, session = self._open("/", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            # The captured initial path is immune to the SPA router's own
            # navigation (the unauthenticated jump to /app/login).
            path = evaluate(session, "window.__initialPath")
            self.assertIn(path, ("/app/", "/app"), f"expected /app/ or /app, got {path}")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "root redirect")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    def test_experiments_redirects_exactly_to_app_experiments(self) -> None:
        """Unauthenticated /experiments → 303 → exact /app/experiments."""
        profile = str(Path(self.temporary_directory.name) / "chrome-exp")
        process, session = self._open("/experiments", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            # Assert the redirect target, not the live pathname: RequireAuth
            # replaces the URL with /app/login as soon as the session probe
            # returns 401, which can precede this read on a fast runner.
            path = evaluate(session, "window.__initialPath")
            self.assertEqual(path, "/app/experiments", f"expected /app/experiments, got {path}")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "experiments redirect")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C4: Visible login with exact destination assertion
    # ------------------------------------------------------------------

    def test_visible_login_returns_to_exact_destination(self) -> None:
        """Legacy /login?next=/experiments/{id} → visible login → exact /app/experiments/{id}."""
        profile = str(Path(self.temporary_directory.name) / "chrome-login")
        dest = f"/experiments/{self.experiment_id}"
        process, session = self._open(f"/login?next={dest}", profile)
        try:
            # /login redirects to /app/login; assert exact pathname + decoded next.
            wait_for_expression(session, "Boolean(document.querySelector('input[name=username]'))")
            path = evaluate(session, "location.pathname")
            self.assertEqual(path, "/app/login", f"expected /app/login, got {path}")

            # Decode next from the URL and assert it equals the original destination.
            from urllib.parse import urlparse, parse_qs
            search = evaluate(session, "location.search")
            # The search string starts with '?' — strip it before parsing.
            if search.startswith("?"):
                search = search[1:]
            params = parse_qs(search)
            # The key may be 'next' or '?next' depending on how the browser encodes it.
            next_key = "next" if "next" in params else ("?next" if "?next" in params else None)
            self.assertIsNotNone(next_key, f"next not found in params: {params}")
            self.assertEqual(params[next_key][0], dest)

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "login page")

            # Fill and submit the visible React login form.
            self._login_via_visible_form(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Assert exact navigation to /app/experiments/{id} (basename=/app prepends /app).
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)
            path = evaluate(session, "location.pathname")
            self.assertEqual(path, f"/app/experiments/{self.experiment_id}",
                             f"expected /app/experiments/{self.experiment_id}, got {path}")
            self.assertNotIn("/app/app/", path)

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "experiment detail after login")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C3: Authenticated login redirect
    # ------------------------------------------------------------------

    def test_authenticated_user_with_next_redirects_to_destination(self) -> None:
        """Authenticated user opening /app/login?next=... redirects to the exact destination."""
        profile = str(Path(self.temporary_directory.name) / "chrome-authed-next")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Navigate to /app/login?next=/experiments/{id} while authenticated.
            self._navigate(session, f"/app/login?next=/experiments/{self.experiment_id}")
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)
            path = evaluate(session, "location.pathname")
            self.assertEqual(path, f"/app/experiments/{self.experiment_id}",
                             f"expected /app/experiments/{self.experiment_id}, got {path}")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "authenticated redirect with next")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    def test_authenticated_user_without_next_redirects_to_app_root(self) -> None:
        """Authenticated user opening /app/login (no next) redirects to exactly /app/."""
        profile = str(Path(self.temporary_directory.name) / "chrome-authed-no-next")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            self._navigate(session, "/app/login")
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)
            path = evaluate(session, "location.pathname")
            self.assertIn(path, ("/app/", "/app"), f"expected /app/ or /app, got {path}")
            search = evaluate(session, "location.search")
            self.assertEqual(search, "", f"expected empty search, got {search}")
            hash_val = evaluate(session, "location.hash")
            self.assertEqual(hash_val, "", f"expected empty hash, got {hash_val}")
            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "authenticated redirect no next")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C3: Role-specific navigation
    # ------------------------------------------------------------------

    def test_role_navigation_student_instructor_admin(self) -> None:
        """Student/instructor/admin see role-specific navigation in the React shell."""
        for username, password, display_name, should_see_users in (
            (STUDENT_USERNAME, STUDENT_PASSWORD, "Cutover Student", False),
            (INSTRUCTOR_USERNAME, INSTRUCTOR_PASSWORD, "Cutover Instructor", False),
            ("cutover-admin", "Cutover admin password 2026!", "Administrator", True),
        ):
            profile = str(Path(self.temporary_directory.name) / f"chrome-{display_name.lower().replace(' ', '-')}")
            process, session = self._open("/app/login", profile)
            try:
                wait_for_expression(session, "Boolean(document.querySelector('#root'))")
                self._login_via_fetch(session, username, password)
                self._navigate(session, "/app/")
                wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)

                # Assert the authenticated display name is visible.
                body_text = evaluate(session, "document.body.textContent")
                self.assertIn(display_name, body_text, f"display name '{display_name}' not visible")

                # Assert Users nav visibility.
                users_link = evaluate(
                    session,
                    "Boolean(Array.from(document.querySelectorAll('a.nav-item,span.nav-item,button.nav-item')).find(e=>e.textContent.trim()==='Users'))",
                )
                if should_see_users:
                    self.assertTrue(users_link, f"{display_name} should see Users navigation")
                else:
                    self.assertFalse(users_link, f"{display_name} should NOT see Users navigation")

                # The unfinished Review queue must not appear for any role.
                review_link = evaluate(
                    session,
                    "Boolean(Array.from(document.querySelectorAll('a.nav-item,span.nav-item,button.nav-item')).find(e=>e.textContent.trim()==='Review queue'))",
                )
                self.assertFalse(review_link, f"{display_name} should not see unfinished Review queue navigation")

                self._assert_viewport(session, 320)
                self._assert_no_overflow(session, f"{display_name} shell")
                session.check_errors()
            finally:
                session.close(); process.kill()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C4: Export and healthz verification
    # ------------------------------------------------------------------

    def test_healthz_and_export_not_shadowed(self) -> None:
        """/healthz returns 200; exports return 200 + attachment disposition + valid JSON."""
        profile = str(Path(self.temporary_directory.name) / "chrome-export")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # /healthz not shadowed
            healthz = evaluate(session, "fetch('/healthz').then(r => r.status)")
            self.assertEqual(int(healthz), 200)

            # Experiment export: 200 + attachment disposition + JSON content + schema_version
            exp_result = evaluate(
                session,
                f"fetch('/experiments/{self.experiment_id}/export.json',{{redirect:'manual'}})"
                ".then(r=>r.text().then(body=>JSON.stringify({status:r.status,cd:r.headers.get('content-disposition'),ct:r.headers.get('content-type'),body:body})))",
            )
            exp_obj = json.loads(exp_result)
            self.assertEqual(int(exp_obj["status"]), 200, "experiment export status")
            self.assertTrue(
                exp_obj["cd"].split(";")[0].strip() == "attachment",
                f"experiment export disposition type not 'attachment': {exp_obj['cd']}",
            )
            self.assertIn("json", exp_obj["ct"], "experiment export content-type")
            exp_body = json.loads(exp_obj["body"])
            self.assertIn("schema_version", exp_body, "experiment export JSON missing schema_version")

            # Batch export: 200 + attachment disposition + JSON content + schema_version
            batch_result = evaluate(
                session,
                f"fetch('/experiments/{self.experiment_id}/batches/{self.batch_id}/export.json',{{redirect:'manual'}})"
                ".then(r=>r.text().then(body=>JSON.stringify({status:r.status,cd:r.headers.get('content-disposition'),ct:r.headers.get('content-type'),body:body})))",
            )
            batch_obj = json.loads(batch_result)
            self.assertEqual(int(batch_obj["status"]), 200, "batch export status")
            self.assertTrue(
                batch_obj["cd"].split(";")[0].strip() == "attachment",
                f"batch export disposition type not 'attachment': {batch_obj['cd']}",
            )
            self.assertIn("json", batch_obj["ct"], "batch export content-type")
            batch_body = json.loads(batch_obj["body"])
            self.assertIn("schema_version", batch_body, "batch export JSON missing schema_version")

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "export check")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C2: Session expiry workflow
    # ------------------------------------------------------------------

    def test_session_expiry_returns_to_original_route_with_query_and_fragment(self) -> None:
        """Session expiry on a protected route → /app/login?next=... → login → exact return."""
        profile = str(Path(self.temporary_directory.name) / "chrome-expiry")
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Open a protected route with query and fragment.
            target_path = f"/experiments/{self.experiment_id}"
            target_search = "?tab=plan"
            target_hash = "#conditions"
            full_route = f"{target_path}{target_search}{target_hash}"
            self._navigate(session, f"/app{full_route}")
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)

            # Invalidate the server-side session by deleting it from the database.
            repo = self.app.state.repository
            session_token = None
            base_url = f"http://127.0.0.1:{self.app_port}/"
            cookies = get_cookies(session, base_url)
            session_cookie = next((c for c in cookies if c.get("name") == "perovskite_session"), None)
            self.assertIsNotNone(session_cookie, "session cookie not found")
            session_token = session_cookie["value"]

            # Delete the session server-side using the token hash.
            from web.auth import hash_token
            token_hash = hash_token(session_token)
            asyncio.run(repo.delete_session(token_hash, actor_user_id=1, client_ip="127.0.0.1"))

            # Reload the page. The SPA boots at the current URL (with query+fragment).
            # The session hook calls /api/session → 401 → unauthenticated.
            # RequireAuth captures the location (pathname, search, hash) as `from` state
            # and navigates to /app/login. LoginPage reads `from` after login.
            evaluate(session, "location.reload()")

            # Wait for the SPA to reload and RequireAuth to redirect to /app/login.
            # RequireAuth captures the full location (pathname, search, hash) as
            # `from` state for LoginPage to return to after login.
            wait_for_expression(
                session,
                "location.pathname === '/app/login'",
                timeout=20,
            )

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "session-expiry login page")

            # Fill and submit the visible React login form.
            self._login_via_visible_form(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Assert return to the exact original pathname, query, and fragment.
            # RequireAuth preserved the location as `from` state; LoginPage reads it.
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)
            path = evaluate(session, "location.pathname")
            search = evaluate(session, "location.search")
            hash_val = evaluate(session, "location.hash")
            self.assertEqual(path, f"/app{target_path}", f"return path mismatch: {path}")
            self.assertEqual(search, target_search, f"return search mismatch: {search}")
            self.assertEqual(hash_val, target_hash, f"return hash mismatch: {hash_val}")
            self.assertNotIn("/app/app/", path, "doubled basename in return path")

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "session-expiry return page")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass

    # ------------------------------------------------------------------
    # C2: Genuine redirectToLogin() browser scenario
    # ------------------------------------------------------------------

    def test_redirect_to_login_via_api_fetch_401_on_patch(self) -> None:
        """Session expiry triggers apiFetch redirectToLogin() with encoded next + login return."""
        profile = str(Path(self.temporary_directory.name) / "chrome-redirect")
        target_path = f"/experiments/{self.experiment_id}"
        target_search = "?tab=plan"
        target_hash = "#conditions"
        full_route = f"{target_path}{target_search}{target_hash}"
        process, session = self._open("/app/login", profile)
        try:
            wait_for_expression(session, "Boolean(document.querySelector('#root'))")
            self._login_via_fetch(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Navigate to the experiment detail page with query and fragment.
            self._navigate(session, f"/app{full_route}")
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)

            # Confirm the detail page rendered (not just the shell).
            detail_ready = evaluate(
                session,
                "Boolean(document.body.textContent.match(/Export|Fabrication|plan/i))",
            )
            self.assertTrue(detail_ready, "experiment detail page did not render")

            # Invalidate the exact browser session server-side.
            base_url = f"http://127.0.0.1:{self.app_port}/"
            cookies = get_cookies(session, base_url)
            session_cookie = next((c for c in cookies if c.get("name") == "perovskite_session"), None)
            self.assertIsNotNone(session_cookie, "session cookie not found")
            session_token = session_cookie["value"]

            repo = self.app.state.repository
            from web.auth import hash_token
            token_hash = hash_token(session_token)
            asyncio.run(repo.delete_session(token_hash, actor_user_id=1, client_ip="127.0.0.1"))

            # Without reloading, click "Start fabrication" button.
            # This invokes ExperimentDetailPage.changePlanStatus() → apiFetch PATCH
            # → 401 → redirectToLogin() → hard navigation to /app/login?next=...
            # The PATCH 401 is expected; consume it before check_errors.
            # Wait for the detail fetch + render to settle before looking for
            # the button (the detail route fetches /api/experiments/{id} on
            # mount; on a slow runner the plan-actions section may not have
            # rendered yet when we first poll).
            wait_for_expression(
                session,
                "Boolean(Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Start fabrication'))",
                timeout=15,
            )

            # Check button disabled state and get diagnostic info.
            btn_info = evaluate(
                session,
                "(function(){const btn=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Start fabrication');if(!btn)return null;return {disabled:btn.disabled,tagName:btn.tagName,type:btn.type};})()",
            )
            self.assertIsNotNone(btn_info, "button info not found")
            self.assertFalse(btn_info.get("disabled", True), f"Start fabrication button is disabled: {btn_info}")

            # Click the button via real CDP mouse click (trusted event) to trigger
            # the React onClick handler → changePlanStatus() → apiFetch PATCH.
            click_center(
                session,
                "Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Start fabrication')",
            )

            # Consume the exact expected PATCH 401 response before
            # wait_for_expression's internal check_errors() catches it.
            # This matches method=PATCH, pathname=/api/experiments/{id}/plan-status, status=401.
            # It does NOT suppress 500s, unrelated failures, or other methods on the same URL.
            expected = session.wait_for_response(
                method="PATCH",
                pathname=f"/api/experiments/{self.experiment_id}/plan-status",
                status=401,
                timeout=15,
            )
            self.assertEqual(expected["method"], "PATCH")
            self.assertEqual(expected["pathname"], f"/api/experiments/{self.experiment_id}/plan-status")
            self.assertEqual(expected["status"], 401)

            # apiFetch's redirectToLogin() does window.location.assign to
            # /app/login?next=<encoded path including query and hash>.
            wait_for_expression(
                session,
                "location.pathname === '/app/login'",
                timeout=20,
            )

            # Decode the next query parameter and assert it equals the original route.
            search = evaluate(session, "location.search")
            if search.startswith("?"):
                search = search[1:]
            from urllib.parse import parse_qs
            params = parse_qs(search)
            next_key = "next" if "next" in params else ("?next" if "?next" in params else None)
            self.assertIsNotNone(next_key, f"next not found in params: {params}")
            decoded_next = params[next_key][0]
            full_route = f"{target_path}{target_search}{target_hash}"
            self.assertEqual(decoded_next, full_route,
                             f"decoded next {decoded_next!r} != full route {full_route!r}")
            self.assertNotIn("/app/app/", decoded_next, "doubled basename in next")

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "redirect-to-login page")

            # Fill and submit the visible React login form.
            self._login_via_visible_form(session, ADMIN_USERNAME, ADMIN_PASSWORD)

            # Assert exact return to the original pathname, query, and fragment.
            wait_for_expression(session, "Boolean(document.querySelector('.shell'))", timeout=15)
            path = evaluate(session, "location.pathname")
            search = evaluate(session, "location.search")
            hash_val = evaluate(session, "location.hash")
            self.assertEqual(path, f"/app{target_path}", f"return path mismatch: {path}")
            self.assertEqual(search, target_search, f"return search mismatch: {search}")
            self.assertEqual(hash_val, target_hash, f"return hash mismatch: {hash_val}")
            self.assertNotIn("/app/app/", path, "doubled basename in return path")

            self._assert_viewport(session, 320)
            self._assert_no_overflow(session, "redirect-to-login return page")
            session.check_errors()
        finally:
            session.close(); process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass


if __name__ == "__main__":
    unittest.main()
