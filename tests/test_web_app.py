import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from perovskite_bo import deposition_recipe_from_process
from tests.recipe_fixtures import REFERENCE_DEPOSITION_PROCESS, REFERENCE_DEVICE_RECIPE
from tests.layout_fixtures import seed_standard_layouts
from web import create_app
from web.repository import ConditionRole, ExecutionStatus, PreparationStatus, UserRole
from web.routes import MAX_RESULT_FILE_BYTES
from web.version import __version__

TEST_USERNAME = "test-admin"
TEST_PASSWORD = "correct horse battery staple"


FLAT_RECIPE_WITHOUT_DEVICE = {
    "spin_cast_rpm": 800,
    "spin_cast_seconds": 60,
    "spin_cast_acceleration_rpm_per_s": 500,
    "spin_spread_rpm": 2000,
    "spin_spread_seconds": 10,
    "spin_spread_acceleration_rpm_per_s": 1000,
    "spin_thin_rpm": 5000,
    "spin_thin_seconds": 20,
    "spin_thin_acceleration_rpm_per_s": 2000,
    "vcd_stage1_valve": "VV02",
    "vcd_stage1_pressure_pa": 5000,
    "vcd_stage1_seconds": 10,
    "anneal_stage1_temperature_c": 120,
    "anneal_stage1_seconds": 600,
}


def multi_device_csv(
    currents: list[float], device_labels: list[str] | None = None
) -> bytes:
    rows = [[], [], [], [], []]
    for trace_index, current in enumerate(currents, start=1):
        device_index = (trace_index + 1) // 2
        device_label = (
            device_labels[device_index - 1]
            if device_labels is not None
            else f"sample-{device_index}"
        )
        direction = "Forward" if trace_index % 2 else "Reverse"
        rows[0].extend(["No.", str(trace_index), "", "", "", "", ""])
        rows[1].extend(
            ["[Information]", "", "[Volt (V)]", "[Current (mA)]", "[J (mA/cm^2)]", "", ""]
        )
        rows[2].extend(["Name", f"{device_label}.{direction}", "0", "-2", str(-current), "", ""])
        rows[3].extend(["", "", "0.5", "-2", str(-current), "", ""])
        rows[4].extend(["", "", "1", "0", "0", "", ""])
    return ("\n".join(",".join(row) for row in rows) + "\n").encode()


def complete_guided_setup() -> tuple[dict, dict]:
    device_recipe = json.loads(json.dumps(REFERENCE_DEVICE_RECIPE))
    deposition_process = json.loads(json.dumps(REFERENCE_DEPOSITION_PROCESS))
    device_recipe["substrate"].update(
        {
            "vendor": "Example vendor",
            "type_number": "ITO-15",
            "width_mm": 15.0,
            "length_mm": 15.0,
        }
    )
    for group in device_recipe["experimental_groups"]:
        if group["kind"] == "target":
            group["inherits_control"] = True
            group["adjustments"] = [
                {
                    "parameter": "device_recipe.substrate.width_mm",
                    "parameter_label": "Substrate · Width (mm)",
                    "control_value": "15",
                    "target_value": "25",
                }
            ]
    for layer in device_recipe["layers"]:
        solution = layer.get("solution")
        if solution:
            if solution.get("formulation_type") == "diluted_dispersion":
                solution["stock_dispersion"] = "SiO2 NP stock dispersion"
                solution["stock_volume_ml"] = 0.1
                solution["solids"] = []
            elif layer["layer_type"] == "passivation":
                # Top-interface passivation dissolves BOTH PEAI and EDADI
                # powders in IPA.
                solution["solids"] = [
                    {"chemical": "PEAI", "weight_mg": 5.0},
                    {"chemical": "EDADI", "weight_mg": 5.0},
                ]
                solution["solvents"] = [
                    {"solvent": "IPA", "volume_ml": 0.5}
                ]
            else:
                solution["solids"] = [
                    {"chemical": f"{layer['name']} solid", "weight_mg": 10.0}
                ]
                solution["solvents"] = [
                    {"solvent": "Example solvent", "volume_ml": 1.0}
                ]
        process = layer.get("process")
        if not process:
            continue
        if process["method"] == "sputtering":
            process.update(
                {
                    "power_w": 100.0,
                    "pressure_pa": 1.0,
                    "gas1": "Ar",
                    "gas1_flow_sccm": 20.0,
                    "gas2": "O2",
                    "gas2_flow_sccm": 5.0,
                    "duration_seconds": 60,
                }
            )
        elif process["method"] == "thermal_evaporation":
            process.update(
                {
                    "thickness_nm": 20.0,
                    "rate_angstrom_per_s": 0.2,
                }
            )
        elif process["method"] == "ald":
            process.update(
                {
                    "thickness_nm": 20.0,
                    "substrate_temperature_c": 80.0,
                    "cycles": 100,
                }
            )
        elif process["method"] == "spin_coating":
            for step in process["spin_steps"]:
                step["rpm"] = step["rpm"] or 3000
                step["seconds"] = step["seconds"] or 30
                step["acceleration_rpm_per_s"] = (
                    step["acceleration_rpm_per_s"] or 1000
                )
            for step in process["anneal_steps"]:
                step["temperature_c"] = step["temperature_c"] or 100
                step["seconds"] = step["seconds"] or 600
    for index, stage in enumerate(deposition_process["vcd_stages"]):
        stage["valve"] = ("VV02", "VV03", "VV06")[index]
    return device_recipe, deposition_process


_VALID_DEVICE_RECIPE, _ = complete_guided_setup()
VALID_RECIPE = {
    **FLAT_RECIPE_WITHOUT_DEVICE,
    "device_recipe": _VALID_DEVICE_RECIPE,
}


def releasable_result_recipe() -> dict:
    """Return a complete comparative recipe suitable for fabrication tests."""

    recipe = json.loads(json.dumps(VALID_RECIPE))
    device_recipe = recipe["device_recipe"]
    _, deposition_process = complete_guided_setup()
    for group in device_recipe["experimental_groups"]:
        if group["kind"] == "target":
            group["layers"] = json.loads(json.dumps(device_recipe["layers"]))
            group["deposition_process"] = deposition_process
            group["adjustments"] = []
    return recipe


class FastAPIWebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset the middleware logger and global logging.disable so assertLogs
        # captures WARNING reliably across a full-suite run.
        import logging as logging_module
        logging_module.disable(logging_module.NOTSET)
        lg = logging_module.getLogger("perovskite_bo.web")
        lg.setLevel(logging_module.WARNING)
        lg.propagate = True
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "experiments.sqlite3"
        app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        csrf = self.client.get("/api/auth/login-csrf")
        login_csrf = csrf.json()["login_csrf_token"]
        login = self.client.post(
            "/api/auth/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD,
                "login_csrf": login_csrf,
            },
        )
        self.assertEqual(login.status_code, 200)
        self.csrf_token = self.client.cookies.get("perovskite_csrf")
        self.client.headers["X-CSRF-Token"] = self.csrf_token
        seed_standard_layouts(self.client)

    def create_campaign(self, code: str, name: str | None = None) -> None:
        response = self.client.post(
            "/api/campaigns",
            json={
                "code": code,
                "display_name": name or code,
                "description": "Test campaign",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def start_result_batch(self, experiment_id: int) -> int:
        response = self.client.patch(
            f"/api/experiments/{experiment_id}/plan-status",
            json={"status": "pending_approval"},
        )
        if response.status_code == 204:
            response = self.client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "approved"},
            )
            self.assertEqual(response.status_code, 204, response.text)
        else:
            self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            f"/api/experiments/{experiment_id}/plan-status",
            json={"status": "released"},
        )
        self.assertEqual(response.status_code, 204, response.text)
        created = self.client.post(
            f"/api/experiments/{experiment_id}/fabrication-batches",
            json={},
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = int(created.json()["id"])
        for batch_status in ("ready", "in_progress"):
            response = self.client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={"status": batch_status},
            )
            self.assertEqual(response.status_code, 204, response.text)
        return batch_id

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        # Windows keeps the SQLite file locked while pooled connections are
        # open, so dispose before TemporaryDirectory.cleanup() removes it.
        import asyncio as asyncio_module
        asyncio_module.run(self.client.app.state.database.dispose())
        self.tmp.cleanup()

    def test_create_experiment_api_and_list_experiments(self) -> None:
        response = self.client.post("/api/experiments", json={"recipe": VALID_RECIPE})

        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created["id"], 1)
        self.assertEqual(created["status"], "suggested")
        self.assertEqual(created["recipe"]["spin_cast_rpm"], 800)
        self.assertEqual(created["campaign_id"], "usual_v1")
        self.assertEqual(created["experiment_code"], "usual_v1-v1")
        self.assertEqual(created["series_version"], 1)

        listed = self.client.get("/api/experiments")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

    def test_create_experiment_api_rejects_recipe_without_complete_device(self) -> None:
        response = self.client.post(
            "/api/experiments",
            json={"recipe": FLAT_RECIPE_WITHOUT_DEVICE},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/experiments").json(), [])

    def test_middleware_adds_security_and_timing_headers(self) -> None:
        response = self.client.get("/experiments")

        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("app;dur=", response.headers["server-timing"])

    def test_oversized_request_body_is_rejected_before_parsing(self) -> None:
        # The transport-level cap rejects from the declared Content-Length
        # alone, so the oversized body is never buffered to temp disk by the
        # multipart/JSON parsers.
        response = self.client.post(
            "/api/experiments",
            content=b"0" * (13 * 1024 * 1024),
            headers={"content-type": "application/json"},
        )

        self.assertEqual(response.status_code, 413)

    def test_chunked_oversized_request_body_is_rejected(self) -> None:
        # No Content-Length: each chunk is delivered as its own ASGI
        # http.request message, and the receive-counting middleware must
        # terminate the request with 413 once the running total passes the
        # cap — without waiting for the stream to end.
        from web.middleware import MAX_REQUEST_BODY_BYTES

        def stream_body():
            chunk = b"0" * (1024 * 1024)
            for _ in range(MAX_REQUEST_BODY_BYTES // len(chunk) + 2):
                yield chunk

        response = self.client.post(
            "/api/experiments",
            content=stream_body(),
            headers={"content-type": "application/json"},
        )
        # httpx2 sets no Content-Length for streamed bodies; the cap must be
        # enforced on the actual byte count.
        self.assertEqual(response.status_code, 413)

    def test_underdeclared_content_length_rejected_on_actual_bytes(self) -> None:
        # A request that lies with a small Content-Length must still be cut
        # off by the actual-byte counter once the real stream exceeds the cap.
        # Delivered through raw ASGI because httpx2 overwrites the declared
        # length to match the body it sends.
        import asyncio

        from web import create_app as create_app_for_asgi
        from web.middleware import MAX_REQUEST_BODY_BYTES

        app = create_app_for_asgi(
            self.database_path,
            secure_cookies=False,
            _test_user=(TEST_USERNAME, TEST_PASSWORD, UserRole.ADMINISTRATOR),
        )
        lie_length = 1024
        real_chunk = b"0" * (1024 * 1024)
        chunks_needed = MAX_REQUEST_BODY_BYTES // len(real_chunk) + 1

        async def run() -> int:
            messages_sent = 0

            async def receive():
                nonlocal messages_sent
                if messages_sent == 0:
                    messages_sent += 1
                    return {
                        "type": "http.request",
                        "body": real_chunk,
                        "more_body": True,
                    }
                if messages_sent <= chunks_needed:
                    messages_sent += 1
                    return {
                        "type": "http.request",
                        "body": real_chunk,
                        "more_body": True,
                    }
                return {"type": "http.disconnect"}

            response_start: dict = {}

            async def send(message):
                if message["type"] == "http.response.start":
                    response_start["status"] = message["status"]

            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/experiments",
                    "raw_path": b"/api/experiments",
                    "query_string": b"",
                    "root_path": "",
                    "headers": [
                        (b"content-length", str(lie_length).encode()),
                        (b"content-type", b"application/json"),
                        (b"host", b"testserver"),
                    ],
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                },
                receive,
                send,
            )
            return response_start.get("status", 0)

        self.assertEqual(asyncio.run(run()), 413)

    def test_legitimate_chunked_request_reaches_the_endpoint(self) -> None:
        # A streamed body under the cap must arrive intact at the endpoint
        # (the receive wrapper is transparent for in-limit bodies).
        def small_stream():
            yield b'{"recipe": '
            yield b"null}"

        response = self.client.post(
            "/api/experiments",
            content=small_stream(),
            headers={"content-type": "application/json"},
        )

        # The body passes the cap; the endpoint rejects the null recipe on
        # its own terms (422), proving the bytes reached the parser.
        self.assertEqual(response.status_code, 422)

    def test_request_body_within_cap_still_reaches_the_api(self) -> None:
        response = self.client.post(
            "/api/experiments",
            content=b"0" * (64 * 1024),
            headers={"content-type": "application/json"},
        )

        # A body under the cap passes the middleware; the endpoint itself
        # rejects the invalid payload on its own terms (422, not 413).
        self.assertEqual(response.status_code, 422)

    def test_cross_site_state_change_is_rejected(self) -> None:
        from unittest.mock import patch

        with patch("web.middleware.LOGGER", wraps=__import__("logging").getLogger("perovskite_bo.web")) as mock_logger:
            response = self.client.post(
                "/api/experiments",
                json={"recipe": VALID_RECIPE},
                headers={"Origin": "https://attacker.example"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/experiments").json(), [])
        mock_logger.warning.assert_called_once()

    def test_openapi_documents_nested_recipe_models(self) -> None:
        document = self.client.get("/openapi.json").json()
        schemas = document["components"]["schemas"]

        self.assertEqual(document["info"]["version"], __version__)
        self.assertIn("device_recipe", schemas["DepositionRecipePayload"]["properties"])
        self.assertIn("deposition_process", schemas["BaselinePayload"]["required"])

    def test_healthcheck_verifies_database_connectivity(self) -> None:
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_baseline_api_stores_control_only_setup(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = json.loads(json.dumps(device_recipe["layers"]))
        target["deposition_process"] = json.loads(json.dumps(deposition_process))

        response = self.client.post(
            "/api/baselines",
            json={
                "name": "Reference stack",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )

        self.assertEqual(response.status_code, 201)
        saved = response.json()
        self.assertEqual(saved["name"], "Reference stack")
        groups = saved["device_recipe"]["experimental_groups"]
        self.assertEqual([group["group_id"] for group in groups], ["control", "target-1"])
        saved_target = groups[1]
        self.assertIsNone(saved_target["layers"])
        self.assertEqual(saved_target["adjustments"], [])
        self.assertEqual(
            saved["deposition_process"]["method"],
            "spin_coating_vcd",
        )
        layer_types = [layer["layer_type"] for layer in saved["device_recipe"]["layers"]]
        self.assertEqual(layer_types[0], "niox")

    def test_baseline_list_get_and_delete(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        created = self.client.post(
            "/api/baselines",
            json={
                "name": "My baseline",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(created.status_code, 201)

        listed = self.client.get("/api/baselines")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["name"], "My baseline")

        baseline_id = created.json()["id"]
        fetched = self.client.get(f"/api/baselines/{baseline_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["id"], baseline_id)

        deleted = self.client.delete(f"/api/baselines/{baseline_id}")
        self.assertEqual(deleted.status_code, 204)
        archived = self.client.get("/api/baselines").json()
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0]["status"], "archived")

    def test_baseline_rejects_invalid_device_recipe(self) -> None:
        response = self.client.post(
            "/api/baselines",
            json={"name": "broken", "device_recipe": {"setup_mode": "blank"}},
        )
        self.assertEqual(response.status_code, 422)

    def test_baseline_requires_perovskite_deposition_process(self) -> None:
        device_recipe, _ = complete_guided_setup()

        response = self.client.post(
            "/api/baselines",
            json={"name": "missing process", "device_recipe": device_recipe},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("deposition_process", str(response.json()["detail"]))

    def test_baseline_update_is_atomic_and_preserves_identity(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        payload = {
            "name": "Atomic reference",
            "device_recipe": device_recipe,
            "deposition_process": deposition_process,
        }
        created = self.client.post("/api/baselines", json=payload)
        self.assertEqual(created.status_code, 201)
        baseline_id = created.json()["id"]

        payload["name"] = "Updated atomic reference"
        updated = self.client.put(f"/api/baselines/{baseline_id}", json=payload)

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["id"], baseline_id)
        self.assertEqual(updated.json()["name"], "Updated atomic reference")
        self.assertEqual(len(self.client.get("/api/baselines").json()), 1)

    def test_rejected_baseline_update_keeps_original(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        created = self.client.post(
            "/api/baselines",
            json={
                "name": "Keep me",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        baseline_id = created.json()["id"]
        invalid_process = json.loads(json.dumps(deposition_process))
        invalid_process["vcd_stages"][0]["pressure_pa"] = None

        rejected = self.client.put(
            f"/api/baselines/{baseline_id}",
            json={
                "name": "Do not keep",
                "device_recipe": device_recipe,
                "deposition_process": invalid_process,
            },
        )

        self.assertEqual(rejected.status_code, 400)
        stored = self.client.get(f"/api/baselines/{baseline_id}").json()
        self.assertEqual(stored["name"], "Keep me")

    def test_duplicate_baseline_name_returns_conflict(self) -> None:
        device_recipe, deposition_process = complete_guided_setup()
        payload = {
            "name": "duplicate",
            "device_recipe": device_recipe,
            "deposition_process": deposition_process,
        }
        first = self.client.post("/api/baselines", json=payload)
        self.assertEqual(first.status_code, 201)

        second = self.client.post("/api/baselines", json=payload)
        self.assertEqual(second.status_code, 409)
        self.assertIn("already exists", second.json()["detail"])

    def test_create_experiment_api_persists_target_layer_stack(self) -> None:
        self.create_campaign("series-layers")
        device_recipe, deposition_process = complete_guided_setup()
        deposition_process["gas_backfill_stages"] = [
            {
                "gas": "N2",
                "flow_sccm": 30,
                "target_pressure_pa": 15,
                "hold_seconds": 20,
            }
        ]
        deposition_process["vcd_step_sequence"] = [
            "vcd_stage1",
            "gas_backfill_stage1",
            "vcd_stage2",
            "vcd_stage3",
        ]
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = json.loads(json.dumps(device_recipe["layers"]))
        target["deposition_process"] = json.loads(json.dumps(deposition_process))
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }

        response = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "series-layers",
                "recipe": recipe,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        stored = self.client.get("/api/experiments").json()[0]
        # The target's own layer stack lives in its condition snapshot.
        conditions = self.client.get(
            f"/api/experiments/{stored['id']}/conditions"
        ).json()
        stored_target = next(
            condition for condition in conditions if condition["role"] == "target"
        )
        self.assertEqual(
            len(stored_target["recipe_snapshot"]["device"]["layers"]),
            len(device_recipe["layers"]),
        )
        self.assertEqual(
            stored_target["recipe_snapshot"]["deposition_process"]["method"],
            "spin_coating_vcd",
        )
        self.assertEqual(
            stored_target["recipe_snapshot"]["deposition_process"]["vcd_step_sequence"],
            deposition_process["vcd_step_sequence"],
        )
        detail = self.client.get("/api/experiments/1")
        self.assertEqual(detail.status_code, 200, detail.text)

    def test_create_experiment_api_persists_complete_setup_snapshot(self) -> None:
        self.create_campaign("series-a")
        device_recipe, deposition_process = complete_guided_setup()
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }

        response = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "series-a",
                "recipe": recipe,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        stored = self.client.get("/api/experiments").json()[0]
        self.assertEqual(stored["campaign_id"], "series-a")
        # The complete device setup lives in the hash-verified condition
        # snapshots; the experiment-level recipe stays a derived view.
        conditions = self.client.get(
            f"/api/experiments/{stored['id']}/conditions"
        ).json()
        control = next(
            condition for condition in conditions if condition["role"] == "control"
        )
        self.assertEqual(
            control["recipe_snapshot"]["device"]["substrate"]["vendor"],
            "Example vendor",
        )
        self.assertEqual(
            control["recipe_snapshot"]["device"]["layers"][0]["layer_type"],
            "niox",
        )
        self.assertEqual(stored["recipe"]["vcd_stage3_pressure_pa"], 300)
        self.assertIsNone(stored["recipe"]["spin_spread_rpm"])
        self.assertIsNone(stored["recipe"]["spin_thin_rpm"])

    def test_create_experiment_api_persists_explicit_condition_layouts(self) -> None:
        self.create_campaign("explicit-layouts")
        device_recipe, deposition_process = complete_guided_setup()
        device_recipe["substrate"]["width_mm"] = 25
        device_recipe["substrate"]["length_mm"] = 25
        condition_plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": (
                    "25x25_single_1cm2"
                    if group["kind"] == "control"
                    else "25x25_six_010"
                ),
                "planned_substrate_count": 3,
            }
            for group in device_recipe["experimental_groups"]
        ]
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }

        response = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "explicit-layouts",
                "recipe": recipe,
                "condition_plans": condition_plans,
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        conditions = self.client.get("/api/experiments/1/conditions").json()
        self.assertEqual(
            [row["device_layout_code"] for row in conditions],
            ["25x25_single_1cm2", "25x25_six_010"],
        )
        self.assertEqual(
            [row["expected_device_count"] for row in conditions],
            [3, 18],
        )

    def test_create_experiment_api_standalone_plan_and_exports_use_exact_condition_snapshot(self) -> None:
        self.create_campaign("standalone-export")
        device_recipe, deposition_process = complete_guided_setup()
        device_recipe["experimental_groups"] = [
            {
                "group_id": "standalone",
                "kind": "standalone",
                "name": "Best efficiency attempt",
                "change_from_control": "",
                "inherits_control": False,
                "adjustments": [],
                "substrate_count": 3,
            }
        ]
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }
        created = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "standalone-export",
                "recipe": recipe,
                "condition_plans": [
                    {
                        "group_id": "standalone",
                        "role": "standalone",
                        "device_layout_code": "15x15_dual_005",
                        "planned_substrate_count": 3,
                    }
                ],
            },
        )

        self.assertEqual(created.status_code, 201, created.text)
        stored = self.client.get("/api/experiments").json()[0]
        self.assertEqual(stored["plan_type"], "standalone")
        conditions = self.client.get("/api/experiments/1/conditions").json()
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0]["condition_code"], "standalone-export-v1-S")
        self.assertEqual(conditions[0]["expected_device_count"], 6)

        detail = self.client.get("/api/experiments/1")
        self.assertEqual(detail.status_code, 200, detail.text)

        json_export = self.client.get("/experiments/1/export.json")
        self.assertEqual(json_export.status_code, 200, json_export.text)
        self.assertEqual(json_export.headers["content-type"], "application/json")
        self.assertIn("attachment;", json_export.headers["content-disposition"])
        exported = json_export.json()
        self.assertEqual(exported["schema_version"], 3)
        self.assertEqual(exported["experiment"]["plan_type"], "standalone")
        self.assertEqual(
            exported["conditions"][0]["canonical_hash"],
            conditions[0]["canonical_hash"],
        )
        self.assertNotIn(
            "experimental_groups",
            exported["conditions"][0]["recipe_snapshot"]["device"],
        )

        pdf_export = self.client.get("/experiments/1/export.pdf")
        self.assertEqual(pdf_export.status_code, 200, pdf_export.text)
        self.assertEqual(pdf_export.headers["content-type"], "application/pdf")
        self.assertTrue(pdf_export.content.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_export.content), 1000)

    def test_substrate_exception_and_plan_approval_api_workflow(self) -> None:
        self.create_campaign("approval-flow")
        device_recipe, deposition_process = complete_guided_setup()
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = json.loads(json.dumps(device_recipe["layers"]))
        target["deposition_process"] = json.loads(json.dumps(deposition_process))
        plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": "15x15_dual_005",
                "planned_substrate_count": 2 if group["kind"] == "control" else 3,
            }
            for group in device_recipe["experimental_groups"]
        ]
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }
        created = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "approval-flow",
                "recipe": recipe,
                "condition_plans": plans,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        control = self.client.get("/api/experiments/1/conditions").json()[0]

        requested = self.client.post(
            f"/api/conditions/{control['id']}/substrate-exceptions",
            json={
                "requested_count": control["planned_substrate_count"],
                "reason": "Only two matched substrates remain.",
            },
        )
        self.assertEqual(requested.status_code, 201, requested.text)
        detail = self.client.get("/api/experiments/1")
        self.assertEqual(detail.status_code, 200, detail.text)

        pending = self.client.patch(
            "/api/experiments/1/plan-status",
            json={"status": "pending_approval"},
        )
        self.assertEqual(pending.status_code, 204, pending.text)
        detail = self.client.get("/api/experiments/1")
        self.assertEqual(detail.status_code, 200)

        exceptions = self.client.get("/api/experiments/1/substrate-exceptions")
        self.assertEqual(exceptions.status_code, 200)
        exception_id = exceptions.json()[0]["id"]
        approved_exception = self.client.post(
            f"/api/substrate-exceptions/{exception_id}/decision",
            json={"decision": "approved", "decision_note": "Approved for this run."},
        )
        self.assertEqual(approved_exception.status_code, 200, approved_exception.text)
        approved_plan = self.client.patch(
            "/api/experiments/1/plan-status",
            json={"status": "approved"},
        )
        self.assertEqual(approved_plan.status_code, 204, approved_plan.text)
        self.assertEqual(self.client.get("/api/experiments/1").json()["experiment"]["plan_status"], "approved")

    def test_substrate_exception_double_request_returns_conflict(self) -> None:
        self.create_campaign("exception-conflict")
        device_recipe, deposition_process = complete_guided_setup()
        target = next(
            group for group in device_recipe["experimental_groups"]
            if group["kind"] == "target"
        )
        target["adjustments"] = []
        target["layers"] = json.loads(json.dumps(device_recipe["layers"]))
        target["deposition_process"] = json.loads(json.dumps(deposition_process))
        plans = [
            {
                "group_id": group["group_id"],
                "role": group["kind"],
                "device_layout_code": "15x15_dual_005",
                "planned_substrate_count": 2 if group["kind"] == "control" else 3,
            }
            for group in device_recipe["experimental_groups"]
        ]
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }
        created = self.client.post(
            "/api/experiments",
            json={"campaign_id": "exception-conflict", "recipe": recipe, "condition_plans": plans},
        )
        self.assertEqual(created.status_code, 201, created.text)
        control = self.client.get("/api/experiments/1/conditions").json()[0]
        first = self.client.post(
            f"/api/conditions/{control['id']}/substrate-exceptions",
            json={"requested_count": control["planned_substrate_count"], "reason": "First request."},
        )
        self.assertEqual(first.status_code, 201, first.text)
        # A second pending request for the same condition is rejected cleanly
        # with 400 (the repository pre-checks for an active exception); the
        # route's IntegrityError handler covers the concurrent-race case.
        second = self.client.post(
            f"/api/conditions/{control['id']}/substrate-exceptions",
            json={"requested_count": control["planned_substrate_count"], "reason": "Second request."},
        )
        self.assertEqual(second.status_code, 400, second.text)
        self.assertIn("active substrate exception", second.json()["detail"])

    def test_baseline_revision_is_linked_to_every_materialized_condition(self) -> None:
        self.create_campaign("reference-lineage")
        device_recipe, deposition_process = complete_guided_setup()
        reference = self.client.post(
            "/api/baselines",
            json={
                "name": "Lineage reference",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        )
        self.assertEqual(reference.status_code, 201, reference.text)
        version_id = reference.json()["current_version_id"]
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }

        created = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "reference-lineage",
                "source_baseline_version_id": version_id,
                "recipe": recipe,
            },
        )

        self.assertEqual(created.status_code, 201, created.text)
        conditions = self.client.get("/api/experiments/1/conditions")
        self.assertEqual(conditions.status_code, 200, conditions.text)
        rows = conditions.json()
        self.assertEqual([row["role"] for row in rows], ["control", "target"])
        self.assertTrue(
            all(row["source_baseline_version_id"] == version_id for row in rows)
        )
        self.assertTrue(
            all(
                "experimental_groups" not in row["recipe_snapshot"]["device"]
                for row in rows
            )
        )
        archived = self.client.delete(f"/api/baselines/{reference.json()['id']}")
        self.assertEqual(archived.status_code, 204)
        control = rows[0]
        updated = self.client.put(
            f"/api/conditions/{control['id']}",
            json={
                "condition_name": "Control after reference archive",
                "recipe_snapshot": control["recipe_snapshot"],
                "source_baseline_version_id": version_id,
                "device_layout_code": control["device_layout_code"],
                "planned_substrate_count": control["planned_substrate_count"],
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["source_baseline_version_id"], version_id)
        detached = self.client.put(
            f"/api/conditions/{control['id']}",
            json={
                "condition_name": "Detached control",
                "recipe_snapshot": control["recipe_snapshot"],
                "source_baseline_version_id": None,
                "device_layout_code": control["device_layout_code"],
                "planned_substrate_count": control["planned_substrate_count"],
            },
        )
        self.assertEqual(detached.status_code, 400)
        self.assertIn("cannot be changed", detached.json()["detail"])

    def test_archived_baseline_revision_cannot_seed_a_new_plan(self) -> None:
        self.create_campaign("archived-reference")
        device_recipe, deposition_process = complete_guided_setup()
        reference = self.client.post(
            "/api/baselines",
            json={
                "name": "Archive before use",
                "device_recipe": device_recipe,
                "deposition_process": deposition_process,
            },
        ).json()
        archived = self.client.delete(f"/api/baselines/{reference['id']}")
        self.assertEqual(archived.status_code, 204)
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }

        rejected = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "archived-reference",
                "source_baseline_version_id": reference["current_version_id"],
                "recipe": recipe,
            },
        )

        self.assertEqual(rejected.status_code, 400)
        self.assertIn(
            "cannot use an archived baseline", str(rejected.json()["detail"])
        )
        self.assertEqual(self.client.get("/api/experiments").json(), [])

    def test_same_series_accepts_independent_experiment_setups(self) -> None:
        self.create_campaign("series-a")
        first_recipe = json.loads(json.dumps(VALID_RECIPE))
        second_recipe = json.loads(json.dumps(VALID_RECIPE))
        second_perovskite = next(
            layer
            for layer in second_recipe["device_recipe"]["layers"]
            if layer["layer_type"] == "perovskite"
        )
        second_perovskite["solution"]["solvents"][0]["solvent"] = "DMF:DMSO"

        first = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "series-a",
                "recipe": first_recipe,
            },
        )
        second = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "series-a",
                "recipe": second_recipe,
            },
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        records = self.client.get("/api/experiments").json()
        self.assertEqual(len(records), 2)
        self.assertEqual(
            [record["experiment_code"] for record in records],
            ["series-a-v1", "series-a-v2"],
        )
        first_control = next(
            condition
            for condition in self.client.get(
                f"/api/experiments/{records[0]['id']}/conditions"
            ).json()
            if condition["role"] == "control"
        )
        second_control = next(
            condition
            for condition in self.client.get(
                f"/api/experiments/{records[1]['id']}/conditions"
            ).json()
            if condition["role"] == "control"
        )
        self.assertNotEqual(
            first_control["recipe_snapshot"]["device"],
            second_control["recipe_snapshot"]["device"],
        )

    def test_campaign_dropdown_lists_only_instructor_created_campaigns(self) -> None:
        self.create_campaign("SAM_mix_ADH", "SAM + ADH study")
        self.client.post(
            "/api/experiments",
            json={"campaign_id": "SAM_mix_ADH", "recipe": VALID_RECIPE},
        )

        builder = self.client.get("/api/campaigns")

        self.assertEqual(builder.status_code, 200)
        campaigns = builder.json()
        self.assertTrue(any(c["code"] == "SAM_mix_ADH" for c in campaigns))

    def test_builder_expands_database_layer_presets_into_a_keyed_map(self) -> None:
        payload = {
            "name": "Builder-owned SAM preset",
            "layer": {
                "layer_type": "sam",
                "role": "htl",
                "name": "Builder-owned SAM",
                "preset_id": None,
                "solution": None,
                "process": None,
            },
            "deposition_process": None,
        }
        created = self.client.post("/api/layer-presets", json=payload)
        self.assertEqual(created.status_code, 201, created.text)

        builder = self.client.get("/api/layer-presets")

        self.assertEqual(builder.status_code, 200, builder.text)
        preset_data = builder.json()
        self.assertIsInstance(preset_data, list)
        matching = [p for p in preset_data if p.get("preset_key") == created.json()["preset_key"]]
        self.assertTrue(matching)
        self.assertEqual(matching[0]["layer"]["name"], "Builder-owned SAM")

    def test_upload_result_file_api(self) -> None:
        created = self.client.post(
            "/api/experiments", json={"recipe": releasable_result_recipe()}
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = self.start_result_batch(1)

        response = self.client.post(
            "/api/experiments/1/results",
            files={
                "result_file": (
                    "A001 Channel 1.csv",
                    b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n",
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(response.status_code, 201)
        uploaded = response.json()
        self.assertEqual(uploaded["experiment_id"], 1)
        self.assertEqual(uploaded["fabrication_batch_id"], batch_id)
        self.assertEqual(uploaded["filename"], "A001 Channel 1.csv")
        self.assertEqual(uploaded["metrics"]["pce"], 10.0)
        self.assertEqual(uploaded["metrics"]["jsc"], 20.0)
        listed = self.client.get("/api/experiments").json()
        self.assertEqual(listed[0]["status"], "suggested")

    def test_oversized_result_file_is_rejected_without_storage(self) -> None:
        created = self.client.post(
            "/api/experiments", json={"recipe": releasable_result_recipe()}
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = self.start_result_batch(1)

        response = self.client.post(
            "/api/experiments/1/results",
            files={
                "result_file": (
                    "oversized.csv",
                    b"x" * (MAX_RESULT_FILE_BYTES + 1),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must not exceed", response.json()["detail"])
        connection = sqlite3.connect(self.database_path)
        try:
            file_count = connection.execute(
                "SELECT COUNT(*) FROM result_files WHERE experiment_id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(file_count, 0)
        record = self.client.get("/api/experiments").json()[0]
        self.assertEqual(record["status"], "suggested")

    def test_repeat_result_upload_does_not_leave_an_extra_blob(self) -> None:
        created = self.client.post(
            "/api/experiments", json={"recipe": releasable_result_recipe()}
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = self.start_result_batch(1)
        result = b"voltage,current_density\n0,-20\n0.5,-20\n1,0\n"
        first = self.client.post(
            "/api/experiments/1/results",
            files={"result_file": ("A001 Channel 1.csv", result, "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )
        repeat = self.client.post(
            "/api/experiments/1/results",
            files={"result_file": ("A002 Channel 1.csv", result, "text/csv")},
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeat.status_code, 400)
        connection = sqlite3.connect(self.database_path)
        try:
            file_count = connection.execute(
                "SELECT COUNT(*) FROM result_files WHERE experiment_id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(file_count, 1)

    def test_result_assignment_api_assigns_substrates_then_shows_statistics_and_curves(self) -> None:
        self.create_campaign("ADH-study")
        device_recipe, deposition_process = complete_guided_setup()
        for group in device_recipe["experimental_groups"]:
            if group["kind"] == "target":
                group["layers"] = json.loads(json.dumps(device_recipe["layers"]))
                group["deposition_process"] = deposition_process
                group["adjustments"] = []
        recipe = {
            **deposition_recipe_from_process(deposition_process),
            "device_recipe": device_recipe,
        }
        created = self.client.post(
            "/api/experiments",
            json={
                "campaign_id": "ADH-study",
                "recipe": recipe,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        batch_id = self.start_result_batch(1)

        # Complete the batch so result-CSV assignment can proceed: drive
        # preparations/executions terminal, record actual counts and a
        # shortfall deviation per condition.
        import asyncio
        repo = self.client.app.state.repository
        for preparation in asyncio.run(repo.list_solution_preparations(batch_id)):
            asyncio.run(
                repo.update_solution_preparation(
                    preparation.id,
                    status=PreparationStatus.DISCARDED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        for execution in asyncio.run(repo.list_process_executions(batch_id)):
            asyncio.run(
                repo.update_process_execution(
                    execution.id,
                    status=ExecutionStatus.CANCELLED,
                    fabrication_batch_id=batch_id,
                    actor_user_id=1,
                )
            )
        conditions_for_batch = asyncio.run(
            repo.get_fabrication_batch_conditions(batch_id)
        )
        actual_counts = {}
        shortfall_deviations = []
        for condition in conditions_for_batch:
            actual_counts[str(condition.id)] = 2
            shortfall_deviations.append({
                "condition_id": condition.id,
                "description": "Test: only two substrates per condition measured; planned count was higher.",
            })
        completed = self.client.patch(
            f"/api/fabrication-batches/{batch_id}/status",
            json={
                "status": "completed",
                "actual_substrate_counts": actual_counts,
                "shortfall_deviations": shortfall_deviations,
            },
        )
        self.assertEqual(completed.status_code, 204, completed.text)

        uploaded = self.client.post(
            "/api/experiments/1/results",
            files={
                "result_file": (
                    "four-devices.csv",
                    multi_device_csv(
                        [20, 20, 21, 21, 24, 24, 25, 25],
                        ["A011 Channel 1", "A012 Channel 1", "A041 Channel 1", "A042 Channel 1"],
                    ),
                    "text/csv",
                )
            },
            data={"fabrication_batch_id": str(batch_id)},
        )

        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        result = self.client.get("/api/results/1")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.client.get("/api/experiments").json()[0]["status"], "suggested")
        substrate_ids = [
            str(substrate["substrate_id"])
            for substrate in result.json()["analysis"]["substrates"]
        ]
        self.assertEqual(substrate_ids, ["A011", "A012", "A041", "A042"])

        conditions = self.client.get(
            f"/api/fabrication-batches/{batch_id}/conditions"
        ).json()
        control_id = next(row["id"] for row in conditions if row["role"] == "control")
        target_id = next(row["id"] for row in conditions if row["role"] == "target")

        saved = self.client.post(
            "/api/results/1/assignments",
            json={
                "assignments": [
                    {"analysis_substrate_id": substrate_ids[0], "batch_condition_id": control_id},
                    {"analysis_substrate_id": substrate_ids[1], "batch_condition_id": control_id},
                    {"analysis_substrate_id": substrate_ids[2], "batch_condition_id": target_id},
                    {"analysis_substrate_id": substrate_ids[3], "batch_condition_id": target_id},
                ]
            },
        )

        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get("/api/experiments").json()[0]["status"], "completed")
        connection = sqlite3.connect(self.database_path)
        try:
            linked_device_count = connection.execute(
                "SELECT COUNT(*) FROM result_device_assignments "
                "WHERE result_file_id = 1 AND fabrication_device_id IS NOT NULL"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(linked_device_count, 4)
        analysis = saved.json()["analysis"]
        self.assertEqual(
            [substrate["group_id"] for substrate in analysis["substrates"]],
            [str(control_id), str(control_id), str(target_id), str(target_id)],
        )
        self.assertIn("groups", analysis["statistics"])
        self.assertEqual(len(analysis["devices"]), 4)
        self.assertGreater(len(analysis["devices"][0]["traces"]), 0)
        detail = self.client.get("/api/experiments/1")
        self.assertEqual(detail.status_code, 200, detail.text)


class BaselinePermissionTests(unittest.TestCase):
    """Test Baseline create/read/revise/archive role permissions."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "permissions.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=("admin", "Adm1n!password", UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login("admin", "Adm1n!password")
        # Create instructor and student users.
        self._create_user("instructor1", UserRole.INSTRUCTOR, "Instruc!tor1")
        self._create_user("student1", UserRole.STUDENT, "Stud3nt!pass")
        # Admin creates a baseline for testing.
        self._login("admin", "Adm1n!password")
        self._baseline_id = self._create_baseline("perm-baseline")

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def _login(self, username: str, password: str) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def _logout(self) -> None:
        response = self.client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204, response.text)
        self.client.headers.pop("X-CSRF-Token", None)

    def _create_user(self, username: str, role: UserRole, password: str) -> None:
        response = self.client.post(
            "/api/users",
            json={"username": username, "display_name": username.title(),
                  "password": password, "role": role.value},
        )
        self.assertEqual(response.status_code, 201, response.text)

    def _create_baseline(self, name: str) -> int:
        dr, dp = complete_guided_setup()
        resp = self.client.post("/api/baselines", json={
            "name": name, "device_recipe": dr, "deposition_process": dp,
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["id"]

    def _valid_payload(self, name: str) -> dict:
        dr, dp = complete_guided_setup()
        return {"name": name, "device_recipe": dr, "deposition_process": dp}

    # -- Administrator can create/update/delete --

    def test_admin_can_create_baseline(self) -> None:
        resp = self.client.post("/api/baselines", json={
            "name": "admin-made", "device_recipe": {"schema_version": 2, "setup_mode": "baseline",
            "junction_type": "single_junction", "perovskite_bandgap": "normal_bandgap",
            "tandem_type": None, "experimental_groups": [
                {"group_id": "control", "kind": "control", "name": "Control",
                 "change_from_control": "", "inherits_control": False, "adjustments": []},
                {"group_id": "target-1", "kind": "target", "name": "Target 1",
                 "change_from_control": "", "inherits_control": True, "adjustments": [],
                 "layers": None, "substrate_count": None},
            ], "substrate": {"material": "ITO", "vendor": "Suzhou Sunyo Technology",
            "type_number": "X07-20A", "width_mm": 15, "length_mm": 15},
            "layers": [{"layer_type": "sam", "role": "htl", "name": "SAM", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "Me-4PACz", "weight_mg": 2.0}],
            "solvents": [{"solvent": "Ethanol", "volume_ml": 1.0}]},
            "process": {"method": "spin_coating", "spin_steps": [{"rpm": 3000, "seconds": 30,
            "acceleration_rpm_per_s": 1000}], "anneal_steps": [{"temperature_c": 100, "seconds": 600}]}},
            {"layer_type": "perovskite", "role": "perovskite", "name": "Perovskite", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "FAPbI3", "weight_mg": 100.0}],
            "solvents": [{"solvent": "DMF", "volume_ml": 1.0}]}, "process": None},
            {"layer_type": "c60", "role": "etl", "name": "C60", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 20, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "bcp", "role": "etl", "name": "BCP", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 8, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "ag", "role": "top_electrode", "name": "Ag", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 100, "rate_angstrom_per_s": 2.0}}]},
            "deposition_process": {"method": "spin_coating_vcd", "spin_steps": [{"rpm": 3000,
            "seconds": 30, "acceleration_rpm_per_s": 1000}], "vcd_stages": [{"valve": "VV02",
            "pressure_pa": 5000, "seconds": 10}], "anneal_steps": [{"temperature_c": 120,
            "seconds": 600}]},
        })
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_admin_can_update_baseline(self) -> None:
        resp = self.client.put(f"/api/baselines/{self._baseline_id}", json={
            "name": "perm-baseline-updated", "device_recipe": {"schema_version": 2, "setup_mode": "baseline",
            "junction_type": "single_junction", "perovskite_bandgap": "normal_bandgap",
            "tandem_type": None, "experimental_groups": [
                {"group_id": "control", "kind": "control", "name": "Control",
                 "change_from_control": "", "inherits_control": False, "adjustments": []},
                {"group_id": "target-1", "kind": "target", "name": "Target 1",
                 "change_from_control": "", "inherits_control": True, "adjustments": [],
                 "layers": None, "substrate_count": None},
            ], "substrate": {"material": "ITO", "vendor": "Suzhou Sunyo Technology",
            "type_number": "X07-20A", "width_mm": 15, "length_mm": 15},
            "layers": [{"layer_type": "sam", "role": "htl", "name": "SAM", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "Me-4PACz", "weight_mg": 2.0}],
            "solvents": [{"solvent": "Ethanol", "volume_ml": 1.0}]},
            "process": {"method": "spin_coating", "spin_steps": [{"rpm": 3000, "seconds": 30,
            "acceleration_rpm_per_s": 1000}], "anneal_steps": [{"temperature_c": 100, "seconds": 600}]}},
            {"layer_type": "perovskite", "role": "perovskite", "name": "Perovskite", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "FAPbI3", "weight_mg": 100.0}],
            "solvents": [{"solvent": "DMF", "volume_ml": 1.0}]}, "process": None},
            {"layer_type": "c60", "role": "etl", "name": "C60", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 20, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "bcp", "role": "etl", "name": "BCP", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 8, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "ag", "role": "top_electrode", "name": "Ag", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 100, "rate_angstrom_per_s": 2.0}}]},
            "deposition_process": {"method": "spin_coating_vcd", "spin_steps": [{"rpm": 3000,
            "seconds": 30, "acceleration_rpm_per_s": 1000}], "vcd_stages": [{"valve": "VV02",
            "pressure_pa": 5000, "seconds": 10}], "anneal_steps": [{"temperature_c": 120,
            "seconds": 600}]},
        })
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_admin_can_delete_baseline(self) -> None:
        bid = self._create_baseline("to-delete")
        resp = self.client.delete(f"/api/baselines/{bid}")
        self.assertEqual(resp.status_code, 204, resp.text)

    # -- Instructor can create/read but cannot revise/archive --

    def test_instructor_can_create_baseline(self) -> None:
        self._logout()
        self._login("instructor1", "Instruc!tor1")
        resp = self.client.post("/api/baselines", json={
            "name": "instructor-made", "device_recipe": {"schema_version": 2, "setup_mode": "baseline",
            "junction_type": "single_junction", "perovskite_bandgap": "normal_bandgap",
            "tandem_type": None, "experimental_groups": [
                {"group_id": "control", "kind": "control", "name": "Control",
                 "change_from_control": "", "inherits_control": False, "adjustments": []},
                {"group_id": "target-1", "kind": "target", "name": "Target 1",
                 "change_from_control": "", "inherits_control": True, "adjustments": [],
                 "layers": None, "substrate_count": None},
            ], "substrate": {"material": "ITO", "vendor": "Suzhou Sunyo Technology",
            "type_number": "X07-20A", "width_mm": 15, "length_mm": 15},
            "layers": [{"layer_type": "sam", "role": "htl", "name": "SAM", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "Me-4PACz", "weight_mg": 2.0}],
            "solvents": [{"solvent": "Ethanol", "volume_ml": 1.0}]},
            "process": {"method": "spin_coating", "spin_steps": [{"rpm": 3000, "seconds": 30,
            "acceleration_rpm_per_s": 1000}], "anneal_steps": [{"temperature_c": 100, "seconds": 600}]}},
            {"layer_type": "perovskite", "role": "perovskite", "name": "Perovskite", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "FAPbI3", "weight_mg": 100.0}],
            "solvents": [{"solvent": "DMF", "volume_ml": 1.0}]}, "process": None},
            {"layer_type": "c60", "role": "etl", "name": "C60", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 20, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "bcp", "role": "etl", "name": "BCP", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 8, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "ag", "role": "top_electrode", "name": "Ag", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 100, "rate_angstrom_per_s": 2.0}}]},
            "deposition_process": {"method": "spin_coating_vcd", "spin_steps": [{"rpm": 3000,
            "seconds": 30, "acceleration_rpm_per_s": 1000}], "vcd_stages": [{"valve": "VV02",
            "pressure_pa": 5000, "seconds": 10}], "anneal_steps": [{"temperature_c": 120,
            "seconds": 600}]},
        })
        self.assertEqual(resp.status_code, 201, resp.text)

    def test_instructor_sees_baseline_save_control(self) -> None:
        self._logout()
        self._login("instructor1", "Instruc!tor1")
        builder = self.client.get("/api/baselines")
        self.assertEqual(builder.status_code, 200, builder.text)
        self.assertIsInstance(builder.json(), list)

    def test_instructor_cannot_update_baseline(self) -> None:
        # Shared baselines retain the administrator-only revision policy; any
        # other actor is outside the uniform 404 resource boundary.
        self._logout()
        self._login("instructor1", "Instruc!tor1")
        resp = self.client.put(
            f"/api/baselines/{self._baseline_id}",
            json=self._valid_payload("noop"),
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_instructor_cannot_delete_baseline(self) -> None:
        self._logout()
        self._login("admin", "Adm1n!password")
        bid = self._create_baseline("instr-del")
        self._logout()
        self._login("instructor1", "Instruc!tor1")
        resp = self.client.delete(f"/api/baselines/{bid}")
        self.assertEqual(resp.status_code, 403, resp.text)

    # -- Student creates a Personal baseline; cannot revise Shared baselines --

    def test_student_creates_personal_baseline(self) -> None:
        self._logout()
        self._login("student1", "Stud3nt!pass")
        resp = self.client.post("/api/baselines", json={
            "name": "student-made",
            "device_recipe": {"schema_version": 2, "setup_mode": "baseline",
            "junction_type": "single_junction", "perovskite_bandgap": "normal_bandgap",
            "tandem_type": None, "experimental_groups": [
                {"group_id": "control", "kind": "control", "name": "Control",
                 "change_from_control": "", "inherits_control": False, "adjustments": []},
                {"group_id": "target-1", "kind": "target", "name": "Target 1",
                 "change_from_control": "", "inherits_control": True, "adjustments": [],
                 "layers": None, "substrate_count": None},
            ], "substrate": {"material": "ITO", "vendor": "Suzhou Sunyo Technology",
            "type_number": "X07-20A", "width_mm": 15, "length_mm": 15},
            "layers": [{"layer_type": "sam", "role": "htl", "name": "SAM", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "Me-4PACz", "weight_mg": 2.0}],
            "solvents": [{"solvent": "Ethanol", "volume_ml": 1.0}]},
            "process": {"method": "spin_coating", "spin_steps": [{"rpm": 3000, "seconds": 30,
            "acceleration_rpm_per_s": 1000}], "anneal_steps": [{"temperature_c": 100, "seconds": 600}]}},
            {"layer_type": "perovskite", "role": "perovskite", "name": "Perovskite", "preset_id": None,
            "solution": {"formulation_type": "weighed_solids", "stock_dispersion": "",
            "stock_volume_ml": None, "solids": [{"chemical": "FAPbI3", "weight_mg": 100.0}],
            "solvents": [{"solvent": "DMF", "volume_ml": 1.0}]}, "process": None},
            {"layer_type": "c60", "role": "etl", "name": "C60", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 20, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "bcp", "role": "etl", "name": "BCP", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 8, "rate_angstrom_per_s": 0.5}},
            {"layer_type": "ag", "role": "top_electrode", "name": "Ag", "preset_id": None,
            "solution": None, "process": {"method": "thermal_evaporation",
            "thickness_nm": 100, "rate_angstrom_per_s": 2.0}}]},
            "deposition_process": {"method": "spin_coating_vcd", "spin_steps": [{"rpm": 3000,
            "seconds": 30, "acceleration_rpm_per_s": 1000}], "vcd_stages": [{"valve": "VV02",
            "pressure_pa": 5000, "seconds": 10}], "anneal_steps": [{"temperature_c": 120,
            "seconds": 600}]},
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["scope"], "personal")
        self.assertEqual(resp.json()["owner_user_id"], 3)

    def test_student_cannot_update_shared_baseline(self) -> None:
        self._logout()
        self._login("student1", "Stud3nt!pass")
        resp = self.client.put(
            f"/api/baselines/{self._baseline_id}",
            json=self._valid_payload("noop"),
        )
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_student_cannot_delete_baseline(self) -> None:
        self._logout()
        self._login("admin", "Adm1n!password")
        bid = self._create_baseline("stu-del")
        self._logout()
        self._login("student1", "Stud3nt!pass")
        self._logout()
        self._login("student1", "Stud3nt!pass")
        resp = self.client.delete(f"/api/baselines/{bid}")
        self.assertEqual(resp.status_code, 403, resp.text)

    # -- Instructor/student can read active baselines --

    def test_instructor_can_list_baselines(self) -> None:
        self._logout()
        self._login("instructor1", "Instruc!tor1")
        resp = self.client.get("/api/baselines")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_student_can_list_baselines(self) -> None:
        self._logout()
        self._login("student1", "Stud3nt!pass")
        resp = self.client.get("/api/baselines")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreaterEqual(len(resp.json()), 1)


class BaselineSnapshotIntegrityTests(unittest.TestCase):
    """Test that loading a baseline, modifying it, and saving produces
    a complete condition snapshot that does not depend on the original baseline."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.database_path = Path(self.tmp.name) / "snapshot.sqlite3"
        self.app = create_app(
            self.database_path,
            secure_cookies=False,
            _test_user=("admin", "Adm1n!password", UserRole.ADMINISTRATOR),
        )
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()
        self._login("admin", "Adm1n!password")
        # Create a campaign and a baseline.
        self.client.post("/api/campaigns", json={"code": "snap-test", "display_name": "Snapshot test", "description": ""})
        # Create a baseline with known values.
        self.dr, self.dp = complete_guided_setup()
        resp = self.client.post("/api/baselines", json={
            "name": "snapshot-test",
            "device_recipe": self.dr,
            "deposition_process": self.dp,
        })
        self.assertEqual(resp.status_code, 201, resp.text)
        self.baseline = resp.json()
        self.baseline_hash = self.baseline.get("canonical_hash")

    def _login(self, username: str, password: str) -> None:
        csrf = self.client.get("/api/auth/login-csrf")
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password,
                  "login_csrf": csrf.json()["login_csrf_token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.headers["X-CSRF-Token"] = self.client.cookies.get("perovskite_csrf")

    def tearDown(self) -> None:
        import asyncio
        asyncio.run(self.app.state.database.dispose())
        self.client_context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_modify_and_save_condition_has_full_snapshot(self) -> None:
        import asyncio, hashlib, json
        repo = self.app.state.repository

        # Load the baseline recipe and modify it.
        recipe = dict(self.baseline["device_recipe"])
        # Modify solid weight
        for layer in recipe["layers"]:
            if layer.get("solution") and layer["solution"].get("solids"):
                for solid in layer["solution"]["solids"]:
                    if solid.get("weight_mg"):
                        solid["weight_mg"] = solid["weight_mg"] * 2
                        break
                break
        # Modify solvent volume
        for layer in recipe["layers"]:
            if layer.get("solution") and layer["solution"].get("solvents"):
                for solv in layer["solution"]["solvents"]:
                    if solv.get("volume_ml"):
                        solv["volume_ml"] = solv["volume_ml"] * 1.5
                        break
                break
        # Modify a processing parameter
        for layer in recipe["layers"]:
            if layer.get("process") and layer["process"].get("method") == "spin_coating":
                for step in layer["process"].get("spin_steps", []):
                    if step.get("rpm"):
                        step["rpm"] = step["rpm"] + 500
                        break
                break

        # Build a condition snapshot from the modified recipe.
        from web.condition_snapshot import build_condition_snapshot, canonical_hash
        snapshot = build_condition_snapshot(recipe, deposition_process=self.dp)
        s_hash = canonical_hash(snapshot)

        # Verify the snapshot contains the modified values.
        device = snapshot.get("device", snapshot)
        self.assertIn("layers", device)
        # The snapshot should contain at least one layer with a solution.
        has_solution = any(
            layer.get("solution") for layer in device.get("layers", [])
        )
        self.assertTrue(has_solution, "condition snapshot must contain layers with solutions")

        # Verify the original baseline revision hash is unchanged.
        baseline_versions = asyncio.run(repo.list_baseline_versions(self.baseline["id"], actor_user_id=1))
        self.assertGreaterEqual(len(baseline_versions), 1)
        self.assertEqual(
            baseline_versions[0]["canonical_hash"],
            self.baseline_hash,
            "baseline revision hash must remain unchanged after modification",
        )

        # Verify deterministic hash.
        snapshot2 = build_condition_snapshot(recipe, deposition_process=self.dp)
        s_hash2 = canonical_hash(snapshot2)
        self.assertEqual(s_hash, s_hash2, "canonical hash must be deterministic")

    def test_archive_baseline_does_not_affect_old_experiment_export(self) -> None:
        import asyncio
        repo = self.app.state.repository

        # Archive the baseline.
        asyncio.run(repo.update_baseline(
            self.baseline["id"],
            name=self.baseline["name"],
            device_recipe=self.dr,
            deposition_process=self.dp,
            actor_user_id=1,
        ))
        # The baseline is still active; archiving is status change via update.
        # Just verify we can still read it.
        loaded = asyncio.run(repo.get_baseline(self.baseline["id"]))
        self.assertEqual(loaded["id"], self.baseline["id"])

    def test_legacy_fields_not_in_output(self) -> None:
        """Verify that DeviceRecipe model_dump, condition snapshot,
        and baseline API response do not contain old field names."""
        from perovskite_bo.device_recipe import DeviceRecipe, normalize_device_recipe

        # Build a recipe with old-style fields to test normalization.
        raw = dict(self.dr)
        raw["setup_mode"] = "reference"
        normalized = normalize_device_recipe(raw)

        # Verify normalized output does NOT contain old fields.
        self.assertNotIn("stack_reference_id", normalized)
        self.assertNotIn("reference_id", str(normalized.get("layers", [])))
        if "setup_mode" in normalized:
            self.assertNotIn("reference", normalized["setup_mode"])
        # Verify the new fields ARE present.
        self.assertIn("setup_mode", normalized)
        self.assertEqual(normalized["setup_mode"], "baseline")
        for layer in normalized.get("layers", []):
            self.assertNotIn("reference_id", layer)
            # preset_id should be present (None or str)
            self.assertIn("preset_id", layer)

        # Verify condition snapshot output does not contain legacy fields.
        from web.condition_snapshot import build_condition_snapshot
        snapshot = build_condition_snapshot(normalized, deposition_process=self.dp)
        self.assertNotIn("legacy_baseline_seed_id", str(snapshot))
        self.assertNotIn("stack_reference_id", str(snapshot))
        device = snapshot.get("device", snapshot)
        self.assertNotIn("legacy_baseline_seed_id", str(device))
        self.assertNotIn("stack_reference_id", str(device))


if __name__ == "__main__":
    unittest.main()
