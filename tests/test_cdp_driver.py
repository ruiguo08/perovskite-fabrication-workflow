"""Deterministic regression tests for CdpSession event handling.

These tests do NOT launch Chrome. They inject events directly into a
CdpSession's ``_events`` list and verify that ``wait_for_response`` and
``check_errors`` behave correctly.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock
from typing import Any

from tests.cdp_driver import CdpSession


def _make_session() -> CdpSession:
    """Create a CdpSession with a mock socket (no real Chrome)."""
    session = CdpSession.__new__(CdpSession)
    session._socket = MagicMock()
    session._next_id = 0
    session._events: list[dict[str, Any]] = []
    session._request_methods: dict[str, str] = {}
    session._closed = False
    # Override call() to be a no-op (no real CDP roundtrip).
    session.call = MagicMock(return_value={})
    return session


def _request_will_be_sent(request_id: str, method: str, url: str) -> dict[str, Any]:
    return {
        "method": "Network.requestWillBeSent",
        "params": {
            "requestId": request_id,
            "request": {"method": method, "url": url},
        },
    }


def _response_received(
    request_id: str, url: str, status: int
) -> dict[str, Any]:
    return {
        "method": "Network.responseReceived",
        "params": {
            "requestId": request_id,
            "response": {"url": url, "status": status},
        },
    }


class WaitForResponseTests(unittest.TestCase):
    """Deterministic tests for CdpSession.wait_for_response."""

    def test_one_exact_response_is_returned_and_consumed(self) -> None:
        session = _make_session()
        session._events = [
            _request_will_be_sent("1", "POST", "http://127.0.0.1:8000/api/experiments"),
            _response_received("1", "http://127.0.0.1:8000/api/experiments", 201),
        ]
        result = session.wait_for_response(
            method="POST", pathname="/api/experiments", status=201, timeout=1
        )
        self.assertEqual(result["method"], "POST")
        self.assertEqual(result["pathname"], "/api/experiments")
        self.assertEqual(result["status"], 201)
        # The matching events should be consumed; nonmatching remain.
        remaining_responses = [
            e for e in session._events
            if e.get("method") == "Network.responseReceived"
        ]
        self.assertEqual(len(remaining_responses), 0)

    def test_two_exact_matches_raise(self) -> None:
        session = _make_session()
        session._events = [
            _request_will_be_sent("1", "POST", "http://127.0.0.1:8000/api/experiments"),
            _response_received("1", "http://127.0.0.1:8000/api/experiments", 201),
            _request_will_be_sent("2", "POST", "http://127.0.0.1:8000/api/experiments"),
            _response_received("2", "http://127.0.0.1:8000/api/experiments", 201),
        ]
        with self.assertRaises(AssertionError) as ctx:
            session.wait_for_response(
                method="POST", pathname="/api/experiments", status=201, timeout=1
            )
        self.assertIn("2 matching", str(ctx.exception))

    def test_same_pathname_status_different_method_does_not_match(self) -> None:
        session = _make_session()
        session._events = [
            _request_will_be_sent("1", "GET", "http://127.0.0.1:8000/api/experiments/1/plan-status"),
            _response_received("1", "http://127.0.0.1:8000/api/experiments/1/plan-status", 401),
        ]
        with self.assertRaises(TimeoutError):
            session.wait_for_response(
                method="PATCH", pathname="/api/experiments/1/plan-status", status=401, timeout=0.2
            )
        # The non-matching response should remain for check_errors.
        remaining_responses = [
            e for e in session._events
            if e.get("method") == "Network.responseReceived"
        ]
        self.assertEqual(len(remaining_responses), 1)

    def test_500_on_same_path_is_not_consumed_when_waiting_for_401(self) -> None:
        session = _make_session()
        session._events = [
            _request_will_be_sent("1", "PATCH", "http://127.0.0.1:8000/api/experiments/1/plan-status"),
            _response_received("1", "http://127.0.0.1:8000/api/experiments/1/plan-status", 500),
        ]
        with self.assertRaises(TimeoutError):
            session.wait_for_response(
                method="PATCH", pathname="/api/experiments/1/plan-status", status=401, timeout=0.2
            )
        # The 500 response should remain and be raised by check_errors.
        with self.assertRaises(RuntimeError) as ctx:
            session.check_errors()
        self.assertIn("500", str(ctx.exception))

    def test_newly_queued_events_are_drained_during_wait(self) -> None:
        session = _make_session()
        # Override call() to inject a new event on each invocation.
        call_count = [0]

        def mock_call(method: str, params: dict | None = None, timeout: float = 20.0) -> Any:
            call_count[0] += 1
            # On the 2nd call (first drain), inject the matching response.
            if call_count[0] == 2:
                session._events.append(
                    _request_will_be_sent("1", "POST", "http://127.0.0.1:8000/api/experiments")
                )
                session._events.append(
                    _response_received("1", "http://127.0.0.1:8000/api/experiments", 201)
                )
            return {}

        session.call = mock_call  # type: ignore

        result = session.wait_for_response(
            method="POST", pathname="/api/experiments", status=201, timeout=2
        )
        self.assertEqual(result["status"], 201)
        self.assertGreater(call_count[0], 0, "call() was never invoked during wait")

    def test_unrelated_500_remains_and_is_raised_by_check_errors(self) -> None:
        session = _make_session()
        session._events = [
            _request_will_be_sent("1", "POST", "http://127.0.0.1:8000/api/experiments"),
            _response_received("1", "http://127.0.0.1:8000/api/experiments", 201),
            _request_will_be_sent("2", "POST", "http://127.0.0.1:8000/api/results"),
            _response_received("2", "http://127.0.0.1:8000/api/results", 500),
        ]
        # wait_for_response consumes the 201 match, then calls check_errors()
        # on remaining events — the 500 should be raised there.
        with self.assertRaises(RuntimeError) as ctx:
            session.wait_for_response(
                method="POST", pathname="/api/experiments", status=201, timeout=1
            )
        self.assertIn("500", str(ctx.exception))


class ChromeDiscoveryTests(unittest.TestCase):
    """Deterministic tests for platform-portable Chrome discovery."""

    def test_windows_candidate_is_skipped_when_not_existing(self) -> None:
        from tests.cdp_driver import discover_chrome_executable

        executable = discover_chrome_executable(
            candidates=[
                "C:/Program Files/Google/Chrome/Application/chrome.exe",
                "/usr/bin/google-chrome",
            ],
            exists=lambda path: path == "/usr/bin/google-chrome",
        )
        self.assertEqual(executable, "/usr/bin/google-chrome")

    def test_returns_none_when_no_candidate_exists(self) -> None:
        from tests.cdp_driver import discover_chrome_executable

        self.assertIsNone(
            discover_chrome_executable(
                candidates=[
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "/usr/bin/google-chrome",
                ],
                exists=lambda path: False,
            )
        )

    def test_builtin_candidates_include_posix_locations(self) -> None:
        from tests import cdp_driver

        self.assertIn("/usr/bin/google-chrome", cdp_driver._CHROME_CANDIDATES)
        self.assertIn("/opt/google/chrome/chrome", cdp_driver._CHROME_CANDIDATES)

    def test_launch_without_any_chrome_raises_a_clear_error(self) -> None:
        from unittest.mock import patch

        from tests import cdp_driver

        with patch.object(cdp_driver, "discover_chrome_executable", return_value=None):
            with self.assertRaises(RuntimeError) as context:
                cdp_driver.launch_chrome_with_viewport(
                    "http://127.0.0.1:1/app/login"
                )
        self.assertIn("Chrome", str(context.exception))


class ClickUntilTests(unittest.TestCase):
    """Deterministic tests for retrying trusted clicks until verified."""

    def _session(self, verify_truthy_after: int | None) -> MagicMock:
        """Fake CdpSession dispatching on the Runtime.evaluate expression.

        click_center evaluates a scrollIntoView and a getBoundingClientRect
        expression before dispatching mouse events; any other expression is
        treated as a verify poll. Verify polls return False until the
        ``verify_truthy_after``-th poll (None: never truthy).
        """

        session = _make_session()
        verify_polls = [0]

        def fake_call(method: str, params: dict | None = None, timeout: float = 20.0) -> Any:
            if method != "Runtime.evaluate":
                return {}
            expression = (params or {}).get("expression", "")
            if "scrollIntoView" in expression:
                return {"result": {"value": True}}
            if "getBoundingClientRect" in expression:
                return {"result": {"value": {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0}}}
            verify_polls[0] += 1
            truthy = (
                verify_truthy_after is not None
                and verify_polls[0] >= verify_truthy_after
            )
            return {"result": {"value": truthy}}

        session.call = MagicMock(side_effect=fake_call)
        return session

    def _mouse_releases(self, session: MagicMock) -> list[Any]:
        return [
            call
            for call in session.call.call_args_list
            if call.args[0] == "Input.dispatchMouseEvent"
            and call.args[1]["type"] == "mouseReleased"
        ]

    def test_retries_the_click_when_verification_keeps_failing(self) -> None:
        from tests.cdp_driver import click_until

        session = self._session(verify_truthy_after=5)
        click_until(
            session,
            "document.querySelector('[data-split-member]')",
            verify="document.querySelector('[data-split-member]').checked",
            attempts=3,
            verify_timeout=0.3,
        )
        # The first attempt times out on false polls, so a second click is
        # issued before the fifth poll turns the verify expression truthy.
        self.assertGreaterEqual(len(self._mouse_releases(session)), 2)

    def test_raises_when_no_attempt_achieves_the_verification(self) -> None:
        from tests.cdp_driver import click_until

        session = self._session(verify_truthy_after=None)
        with self.assertRaises(TimeoutError) as context:
            click_until(
                session,
                "document.querySelector('[data-split-member]')",
                verify="document.querySelector('[data-split-member]').checked",
                attempts=2,
                verify_timeout=0.2,
            )
        self.assertIn("click did not achieve", str(context.exception))
        self.assertEqual(len(self._mouse_releases(session)), 2)


class ClickStabilizationTests(unittest.TestCase):
    """click_center must wait for the element rect to stop moving."""

    def _session_with_shifting_rect(self) -> MagicMock:
        session = _make_session()
        rects = iter(
            (
                {"x": 0.0, "y": 100.0, "width": 20.0, "height": 20.0},
                {"x": 0.0, "y": 96.0, "width": 20.0, "height": 20.0},
                {"x": 0.0, "y": 96.0, "width": 20.0, "height": 20.0},
            )
        )

        def fake_call(method: str, params: dict | None = None, timeout: float = 20.0) -> Any:
            if method != "Runtime.evaluate":
                return {}
            expression = (params or {}).get("expression", "")
            if "scrollIntoView" in expression:
                return {"result": {"value": True}}
            if "getBoundingClientRect" in expression:
                return {"result": {"value": next(rects, {"x": 0.0, "y": 96.0, "width": 20.0, "height": 20.0})}}
            return {"result": {"value": None}}

        session.call = MagicMock(side_effect=fake_call)
        return session

    def test_clicks_at_the_settled_rect_center(self) -> None:
        from tests.cdp_driver import click_center

        session = self._session_with_shifting_rect()
        click_center(session, "document.querySelector('#target')")

        released = [
            call
            for call in session.call.call_args_list
            if call.args[0] == "Input.dispatchMouseEvent"
            and call.args[1]["type"] == "mouseReleased"
        ]
        self.assertEqual(len(released), 1)
        # The settled rect (y=96) must win over the first two reads.
        self.assertEqual(released[0].args[1]["y"], 106.0)


class CheckErrorsNetworkTests(unittest.TestCase):
    """loadingFailed handling must ignore client-side cancellations."""

    def _session_with_failure(self, error_text: str) -> CdpSession:
        session = _make_session()
        session._events = [
            {
                "method": "Network.loadingFailed",
                "params": {"requestId": "1", "errorText": error_text},
            }
        ]
        return session

    def test_client_aborted_requests_are_ignored(self) -> None:
        session = self._session_with_failure("net::ERR_ABORTED")
        session.check_errors()

    def test_real_network_failures_still_raise(self) -> None:
        session = self._session_with_failure("net::ERR_CONNECTION_REFUSED")
        with self.assertRaises(RuntimeError) as context:
            session.check_errors()
        self.assertIn("ERR_CONNECTION_REFUSED", str(context.exception))


if __name__ == "__main__":
    unittest.main()
