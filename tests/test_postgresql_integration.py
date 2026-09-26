import asyncio
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from perovskite_bo import DepositionRecipe, deposition_recipe_from_process
from tests.recipe_fixtures import FACTORY_LAYER_PRESETS as LAYER_PRESETS
from web import create_app
from web.auth import hash_password, normalize_username
from web.database import (
    Database,
    catalog_seed_versions,
    audit_events,
    baselines,
    execution_deviations,
    experiment_conditions,
    experiments,
    fabrication_batch_conditions,
    fabrication_batches,
    fabrication_substrates,
    layer_presets,
    solution_preparations,
    result_device_assignments,
    result_files,
)
from web.jv_parser import (
    _flat_metrics_from_analysis,
    assign_substrates_to_groups,
    parse_jv_analysis,
)
from web.repository import (
    BatchStatus,
    ConditionRole,
    ExecutionStatus,
    PlanStatus,
    PreparationStatus,
    UserRole,
    WebRepository,
)


from tests.layout_fixtures import seed_standard_layouts_async
from tests.test_web_app import complete_guided_setup


@unittest.skipUnless(
    os.environ.get("PEROVSKITE_TEST_POSTGRESQL_URL"),
    "set PEROVSKITE_TEST_POSTGRESQL_URL to run PostgreSQL integration tests",
)
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_plan_start_and_last_batch_cancellation_cannot_both_succeed(self) -> None:
        from tests.test_fabrication_batches import _create_released_experiment_with_conditions

        async def run() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            suffix = uuid4().hex[:12]
            try:
                actor = await repository.create_user(
                    username=f"pg-batch-guard-{suffix}", display_name="Batch guard test",
                    password_hash=hash_password(f"batch guard secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository, f"pg-batch-guard-{suffix}", actor_user_id=actor.id,
                )
                batch = await repository.create_fabrication_batch(experiment_id, actor_user_id=actor.id)
                start = asyncio.create_task(repository.update_plan_status(
                    experiment_id, PlanStatus.IN_PROGRESS, actor_user_id=actor.id,
                ))
                cancel = asyncio.create_task(repository.update_fabrication_batch_status(
                    batch.id, BatchStatus.CANCELLED, actor_user_id=actor.id,
                ))
                outcomes = await asyncio.wait_for(
                    asyncio.gather(start, cancel, return_exceptions=True), timeout=10,
                )
                self.assertEqual(sum(outcome is None for outcome in outcomes), 1, outcomes)
                self.assertEqual(sum(isinstance(outcome, ValueError) for outcome in outcomes), 1, outcomes)
                async with database.engine.connect() as connection:
                    plan_status = await connection.scalar(select(experiments.c.plan_status).where(
                        experiments.c.id == experiment_id,
                    ))
                    batch_status = await connection.scalar(select(fabrication_batches.c.status).where(
                        fabrication_batches.c.id == batch.id,
                    ))
                self.assertFalse(plan_status == PlanStatus.IN_PROGRESS.value and batch_status == BatchStatus.CANCELLED.value)
            finally:
                await database.dispose()

        asyncio.run(run())

    def test_individual_preparation_waits_for_batch_before_locking_child(self) -> None:
        """Bulk parent lock must not race an individual child-first edit."""
        from tests.test_fabrication_batches import _create_released_experiment_with_conditions
        from sqlalchemy.exc import OperationalError

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]

        async def run() -> None:
            database = Database(url)
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                actor = await repository.create_user(
                    username=f"pg-prep-lock-{suffix}", display_name="Preparation lock test",
                    password_hash=hash_password(f"lock secret {suffix}"), role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository, f"pg-prep-lock-{suffix}", actor_user_id=actor.id,
                )
                batch = await repository.create_fabrication_batch(experiment_id, actor_user_id=actor.id)
                preparation = (await repository.list_solution_preparations(batch.id))[0]
                async with database.begin() as parent_connection:
                    await parent_connection.execute(select(fabrication_batches.c.id).where(
                        fabrication_batches.c.id == batch.id).with_for_update())
                    pending = asyncio.create_task(repository.update_solution_preparation(
                        preparation.id, actual_matches_planned=True,
                        fabrication_batch_id=batch.id, actor_user_id=actor.id,
                    ))
                    await asyncio.sleep(0.25)
                    try:
                        async with database.begin() as probe_connection:
                            await probe_connection.execute(select(solution_preparations.c.id).where(
                                solution_preparations.c.id == preparation.id).with_for_update(nowait=True))
                    except OperationalError as error:
                        self.fail(f"individual edit locked the preparation before the batch: {error}")
                await asyncio.wait_for(pending, timeout=5)
            finally:
                await database.dispose()

        asyncio.run(run())
    def test_catalog_scope_and_current_version_integrity_use_postgresql(self) -> None:
        async def exercise_catalog() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            suffix = uuid4().hex[:12]
            try:
                instructor = await repository.create_user(
                    username=f"pg-catalog-{suffix}",
                    display_name="PostgreSQL Catalog Instructor",
                    password_hash=hash_password(f"catalog integration secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                # With no factory catalog, the instructor authors the first
                # shared preset themselves.
                layer = deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"])
                seeded_shared = await repository.create_layer_preset(
                    name=f"PostgreSQL shared catalog {suffix}",
                    layer=layer,
                    deposition_process=None,
                    scope="shared",
                    actor_user_id=instructor.id,
                )
                visible = await repository.list_layer_presets(
                    actor_user_id=instructor.id
                )
                self.assertTrue(
                    any(record["scope"] == "shared" for record in visible)
                )
                first = await repository.create_layer_preset(
                    name=f"PostgreSQL catalog one {suffix}",
                    layer=layer,
                    deposition_process=None,
                    actor_user_id=instructor.id,
                )
                second = await repository.create_layer_preset(
                    name=f"PostgreSQL catalog two {suffix}",
                    layer=layer,
                    deposition_process=None,
                    actor_user_id=instructor.id,
                )

                with self.assertRaises(IntegrityError):
                    async with database.engine.begin() as connection:
                        await connection.execute(
                            layer_presets.update()
                            .where(layer_presets.c.id == first["id"])
                            .values(
                                current_version_id=second["current_version_id"]
                            )
                        )

                # No factory catalog seeding runs at startup anymore, so the
                # ledger stays empty on a fresh database.
                async with database.engine.connect() as connection:
                    seed_count = int(
                        await connection.scalar(
                            select(func.count()).select_from(catalog_seed_versions)
                        )
                        or 0
                    )
                self.assertEqual(seed_count, 0)
            finally:
                await database.dispose()

        asyncio.run(exercise_catalog())

    def test_runtime_database_role_is_restricted(self) -> None:
        async def inspect_role() -> tuple[bool, bool, bool, bool]:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            try:
                async with database.engine.connect() as connection:
                    row = (
                        await connection.execute(
                            text(
                                "SELECT rolsuper, rolcreatedb, rolcreaterole, "
                                "rolbypassrls FROM pg_roles WHERE rolname = current_user"
                            )
                        )
                    ).one()
                    return tuple(row)
            finally:
                await database.dispose()

        self.assertEqual(asyncio.run(inspect_role()), (False, False, False, False))

    def test_repository_transactions_use_migrated_postgresql_schema(self) -> None:
        asyncio.run(self._exercise_repository())

    def test_role_scoped_http_workflow_uses_postgresql(self) -> None:
        suffix = uuid4().hex[:12]
        accounts = {
            "instructor": (
                f"pg-instructor-{suffix}",
                f"PostgreSQL instructor password {suffix}",
                UserRole.INSTRUCTOR,
            ),
            "owner": (
                f"pg-owner-{suffix}",
                f"PostgreSQL owner password {suffix}",
                UserRole.STUDENT,
            ),
            "other": (
                f"pg-other-{suffix}",
                f"PostgreSQL other password {suffix}",
                UserRole.STUDENT,
            ),
        }

        async def seed_users() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                for username, password, role in accounts.values():
                    await repository.create_user(
                        username=username,
                        display_name=username,
                        password_hash=hash_password(password, username=username),
                        role=role,
                    )
            finally:
                await database.dispose()

        asyncio.run(seed_users())
        app = create_app(
            os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"],
            secure_cookies=False,
        )

        with TestClient(app, base_url="https://testserver") as client:
            def login(account: str) -> None:
                username, password, _ = accounts[account]
                login_csrf = client.get("/api/auth/login-csrf")
                self.assertEqual(login_csrf.status_code, 200)
                response = client.post(
                    "/api/auth/login",
                    json={
                        "username": username,
                        "password": password,
                        "login_csrf": login_csrf.json()["login_csrf_token"],
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                client.headers["X-CSRF-Token"] = client.cookies.get(
                    "perovskite_csrf"
                )

            def logout() -> None:
                response = client.post("/api/auth/logout")
                self.assertEqual(response.status_code, 204, response.text)
                client.headers.pop("X-CSRF-Token", None)

            campaign_code = f"pg-role-{suffix}"
            login("instructor")
            campaign = client.post(
                "/api/campaigns",
                json={
                    "code": campaign_code,
                    "display_name": f"PostgreSQL role test {suffix}",
                    "description": "Disposable integration-test campaign",
                },
            )
            self.assertEqual(campaign.status_code, 201, campaign.text)
            device_recipe, deposition_process = complete_guided_setup()
            baseline = client.post(
                "/api/baselines",
                json={
                    "name": f"PostgreSQL role baseline {suffix}",
                    "device_recipe": device_recipe,
                    "deposition_process": deposition_process,
                },
            )
            self.assertEqual(baseline.status_code, 201, baseline.text)
            baseline_version_id = baseline.json()["current_version_id"]
            logout()

            login("owner")
            personal_layer = deepcopy(LAYER_PRESETS["sam_spin_v1"]["layer"])
            personal_preset = client.post(
                "/api/layer-presets",
                json={
                    "name": f"PostgreSQL personal preset {suffix}",
                    "layer": personal_layer,
                    "deposition_process": None,
                    "scope": "personal",
                },
            )
            self.assertEqual(personal_preset.status_code, 201, personal_preset.text)
            personal_preset_id = int(personal_preset.json()["id"])
            personal_layer["name"] = f"Revised PostgreSQL SAM {suffix}"
            revised_preset = client.put(
                f"/api/layer-presets/{personal_preset_id}",
                json={
                    "name": f"PostgreSQL personal preset {suffix}",
                    "layer": personal_layer,
                    "deposition_process": None,
                    "scope": "personal",
                },
            )
            self.assertEqual(revised_preset.status_code, 200, revised_preset.text)
            self.assertEqual(
                [
                    version["revision_number"]
                    for version in client.get(
                        f"/api/layer-presets/{personal_preset_id}/versions"
                    ).json()
                ],
                [1, 2],
            )
            created = client.post(
                "/api/experiments",
                json={
                    "recipe": {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    },
                    "campaign_id": campaign_code,
                    "source_baseline_version_id": baseline_version_id,
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            experiment_id = created.json()["id"]
            self.assertEqual(
                [row["id"] for row in client.get("/api/experiments").json()],
                [experiment_id],
            )
            self.assertEqual(
                client.post(
                    "/api/campaigns",
                    json={
                        "code": f"student-{suffix}",
                        "display_name": "Forbidden student campaign",
                        "description": "",
                    },
                ).status_code,
                403,
            )
            logout()

            login("other")
            self.assertEqual(client.get("/api/experiments").json(), [])
            visible_preset_ids = {
                row["id"] for row in client.get("/api/layer-presets").json()
            }
            self.assertNotIn(personal_preset_id, visible_preset_ids)
            self.assertEqual(
                client.get(
                    f"/api/layer-presets/{personal_preset_id}/versions"
                ).status_code,
                404,
            )
            self.assertEqual(
                client.get(
                    f"/api/experiments/{experiment_id}/conditions"
                ).status_code,
                404,
            )
            logout()

            login("instructor")
            visible_ids = [
                row["id"] for row in client.get("/api/experiments").json()
            ]
            self.assertIn(experiment_id, visible_ids)
            self.assertEqual(
                client.get(f"/experiments/{experiment_id}").status_code,
                200,
            )

    def test_fabrication_batch_workflow_uses_postgresql_schema(self) -> None:
        asyncio.run(self._exercise_fabrication_batch())

    def test_phase3_contracts_use_postgresql_schema(self) -> None:
        asyncio.run(self._exercise_phase3_contracts())

    async def _exercise_phase3_contracts(self) -> None:
        from perovskite_bo import (
            MAX_SOLID_CHEMICALS,
            MAX_SOLVENTS,
            VCD_VALVES,
            deposition_recipe_from_process,
        )

        from web.database import result_files

        database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
        repository = WebRepository(database)
        await seed_standard_layouts_async(database)
        suffix = uuid4().hex[:12]
        accounts = {
            "instructor": (
                f"pg3-instructor-{suffix}",
                f"PostgreSQL Phase 3 instructor password {suffix}",
                UserRole.INSTRUCTOR,
            ),
            "owner": (
                f"pg3-owner-{suffix}",
                f"PostgreSQL Phase 3 owner password {suffix}",
                UserRole.STUDENT,
            ),
            "other": (
                f"pg3-other-{suffix}",
                f"PostgreSQL Phase 3 other password {suffix}",
                UserRole.STUDENT,
            ),
        }

        async def seed_users() -> None:
            for username, password, role in accounts.values():
                await repository.create_user(
                    username=username,
                    display_name=username,
                    password_hash=hash_password(password, username=username),
                    role=role,
                )

        async def owner_account_id() -> int:
            owner = await repository.get_user_by_username(
                normalize_username(accounts["owner"][0])
            )
            self.assertIsNotNone(owner)
            return int(owner.id)

        try:
            await seed_users()
            owner_id = await owner_account_id()
        finally:
            await database.dispose()

        app = create_app(
            os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"],
            secure_cookies=False,
        )
        uploaded_content = (
            "No.,1,,,,,,No.,2,,,,,\n"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,,"
            "[Information],,[Volt (V)],[Current (mA)],[J (mA/cm^2)],,\n"
            "Name,A001 Channel 1.Forward,0,-2,-20,,,Name,A001 Channel 1.Reverse,0,-2,-20,,\n"
            ",,0.5,-2,-20,,,,,0.5,-2,-20,,\n"
            ",,1,0,0,,,,,1,0,0,,\n"
        ).encode("utf-8")
        with TestClient(app, base_url="https://testserver") as client:
            def login(account: str) -> None:
                username, password, _ = accounts[account]
                login_csrf = client.get("/api/auth/login-csrf")
                self.assertEqual(login_csrf.status_code, 200)
                response = client.post(
                    "/api/auth/login",
                    json={
                        "username": username,
                        "password": password,
                        "login_csrf": login_csrf.json()["login_csrf_token"],
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                client.headers["X-CSRF-Token"] = client.cookies.get(
                    "perovskite_csrf"
                )

            def logout() -> None:
                response = client.post("/api/auth/logout")
                self.assertEqual(response.status_code, 204, response.text)
                client.headers.pop("X-CSRF-Token", None)

            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = deepcopy(device_recipe["layers"])
                    group["deposition_process"] = deepcopy(deposition_process)

            login("instructor")
            campaign_code = f"pg3-{suffix}"
            campaign = client.post(
                "/api/campaigns",
                json={
                    "code": campaign_code,
                    "display_name": f"PostgreSQL Phase 3 test {suffix}",
                    "description": "Disposable Phase 3 integration campaign",
                },
            )
            self.assertEqual(campaign.status_code, 201, campaign.text)
            baseline = client.post(
                "/api/baselines",
                json={
                    "name": f"PostgreSQL Phase 3 baseline {suffix}",
                    "device_recipe": deepcopy(device_recipe),
                    "deposition_process": deepcopy(deposition_process),
                },
            )
            self.assertEqual(baseline.status_code, 201, baseline.text)
            logout()

            login("owner")
            created = client.post(
                "/api/experiments",
                json={
                    "recipe": {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    },
                    "campaign_id": campaign_code,
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
            self.assertEqual(created.status_code, 201, created.text)
            experiment_id = int(created.json()["id"])
            submitted = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "pending_approval"},
            )
            self.assertEqual(submitted.status_code, 204, submitted.text)
            logout()
            login("instructor")
            approved = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "approved"},
            )
            self.assertEqual(approved.status_code, 204, approved.text)
            released = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "released"},
            )
            self.assertEqual(released.status_code, 204, released.text)
            logout()
            login("owner")
            batch = client.post(
                f"/api/experiments/{experiment_id}/fabrication-batches",
                json={"notes": "PostgreSQL Phase 3 batch"},
            )
            self.assertEqual(batch.status_code, 201, batch.text)
            batch_id = int(batch.json()["id"])
            for status_name in ("ready", "in_progress"):
                transition = client.patch(
                    f"/api/fabrication-batches/{batch_id}/status",
                    json={"status": status_name},
                )
                self.assertEqual(transition.status_code, 204, transition.text)
            # Result-CSV association is a post-completion step: drive
            # preparations/executions terminal, declare one actual substrate per
            # condition (with a shortfall deviation for the 3 planned) and
            # complete the batch before uploading.
            preparations = client.get(
                f"/api/fabrication-batches/{batch_id}/solution-preparations"
            )
            self.assertEqual(preparations.status_code, 200, preparations.text)
            for preparation in preparations.json():
                transition = client.patch(
                    f"/api/fabrication-batches/{batch_id}/solution-preparations/{preparation['id']}",
                    json={"status": "discarded"},
                )
                self.assertEqual(transition.status_code, 200, transition.text)
            executions = client.get(
                f"/api/fabrication-batches/{batch_id}/process-executions"
            )
            self.assertEqual(executions.status_code, 200, executions.text)
            for execution in executions.json():
                transition = client.patch(
                    f"/api/fabrication-batches/{batch_id}/process-executions/{execution['id']}",
                    json={"status": "cancelled"},
                )
                self.assertEqual(transition.status_code, 200, transition.text)
            pg_conditions = client.get(
                f"/api/fabrication-batches/{batch_id}/conditions"
            )
            self.assertEqual(pg_conditions.status_code, 200, pg_conditions.text)
            actual_counts = {}
            actual_counts = {}
            shortfall_deviations = []
            for condition in pg_conditions.json():
                actual_counts[str(condition["id"])] = 1
                shortfall_deviations.append({
                    "condition_id": condition["id"],
                    "description": (
                        "PostgreSQL test: one substrate per condition was "
                        "measured; the remaining planned substrates were not made."
                    ),
                })
            completed = client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={
                    "status": "completed",
                    "actual_substrate_counts": actual_counts,
                    "shortfall_deviations": shortfall_deviations,
                },
            )
            self.assertEqual(completed.status_code, 204, completed.text)
            uploaded = client.post(
                f"/api/experiments/{experiment_id}/results",
                files={
                    "result_file": (
                        "phase3_pg.csv",
                        uploaded_content,
                        "text/csv",
                    )
                },
                data={"fabrication_batch_id": str(batch_id)},
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            file_id = int(uploaded.json()["id"])

            owner_batches = client.get("/api/fabrication-batches").json()
            self.assertEqual([row["id"] for row in owner_batches], [batch_id])
            self.assertTrue(owner_batches[0]["experiment_code"])
            owner_results = client.get("/api/results").json()
            self.assertEqual([row["id"] for row in owner_results], [file_id])
            self.assertTrue(owner_results[0]["batch_code"])

            run_sheet = client.get(
                f"/api/fabrication-batches/{batch_id}/run-sheet"
            )
            self.assertEqual(run_sheet.status_code, 200, run_sheet.text)
            sheet = run_sheet.json()
            self.assertEqual(len(sheet["batch"]["condition_set_hash"]), 64)
            self.assertTrue(sheet["preparations"])
            self.assertTrue(sheet["preparations"][0]["uses"])
            self.assertTrue(sheet["executions"])
            self.assertTrue(sheet["executions"][0]["members"])
            self.assertEqual(
                sheet["editor_config"]["max_solid_chemicals"],
                MAX_SOLID_CHEMICALS,
            )
            self.assertEqual(sheet["editor_config"]["max_solvents"], MAX_SOLVENTS)
            self.assertEqual(
                sheet["editor_config"]["vcd_valves"],
                list(VCD_VALVES),
            )

            detail = client.get(f"/api/results/{file_id}")
            self.assertEqual(detail.status_code, 200, detail.text)
            detail_body = detail.json()
            self.assertEqual(detail_body["created_by_id"], owner_id)
            self.assertEqual(len(detail_body["groups"]), 2)
            self.assertEqual(detail_body["assignments"], [])
            control_condition = next(
                group["batch_condition_id"]
                for group in detail_body["groups"]
                if group["kind"] == "control"
            )
            substrate_id = str(
                detail_body["analysis"]["substrates"][0]["substrate_id"]
            )

            assigned = client.post(
                f"/api/results/{file_id}/assignments",
                json={
                    "assignments": [
                        {
                            "analysis_substrate_id": substrate_id,
                            "batch_condition_id": control_condition,
                        }
                    ]
                },
            )
            self.assertEqual(assigned.status_code, 200, assigned.text)
            self.assertTrue(
                assigned.json()["analysis"]["statistics"]["groups"]
            )
            self.assertEqual(len(assigned.json()["assignments"]), 1)
            persisted = client.get(f"/api/results/{file_id}/assignments")
            self.assertEqual(persisted.status_code, 200, persisted.text)
            self.assertEqual(len(persisted.json()), 1)
            self.assertEqual(
                persisted.json()[0]["analysis_substrate_id"],
                substrate_id,
            )
            logout()

            login("other")
            self.assertEqual(client.get("/api/fabrication-batches").json(), [])
            self.assertEqual(client.get("/api/results").json(), [])
            self.assertEqual(
                client.get(f"/api/results/{file_id}").status_code,
                404,
            )
            self.assertEqual(
                client.get(f"/api/fabrication-batches/{batch_id}/run-sheet").status_code,
                404,
            )
            logout()

            login("instructor")
            instructor_batches = client.get(
                "/api/fabrication-batches"
            ).json()
            self.assertIn(batch_id, [row["id"] for row in instructor_batches])
            instructor_results = client.get("/api/results").json()
            self.assertIn(file_id, [row["id"] for row in instructor_results])

        # Binary-content round-trip through the PostgreSQL LargeBinary column.
        database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
        try:
            async with database.engine.connect() as connection:
                stored = await connection.scalar(
                    select(result_files.c.content).where(
                        result_files.c.id == file_id
                    )
                )
            self.assertEqual(stored, uploaded_content)
        finally:
            await database.dispose()

    def test_deviation_type_and_target_constraints_enforced_by_postgresql(self) -> None:
        """PostgreSQL itself rejects an invalid deviation_type, a missing
        deviation_type, and condition_id combined with another target, even
        when application validation is bypassed."""

        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        async def exercise() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            suffix = uuid4().hex[:12]
            try:
                instructor = await repository.create_user(
                    username=f"pg-devtype-{suffix}",
                    display_name="PostgreSQL Deviation Types Instructor",
                    password_hash=hash_password(f"devtype secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository,
                    f"pg-devtype-{suffix}",
                    actor_user_id=instructor.id,
                )
                batch = await repository.create_fabrication_batch(
                    experiment_id,
                    actor_user_id=instructor.id,
                )
                conditions = await repository.get_fabrication_batch_conditions(
                    batch.id
                )
                control = next(
                    condition
                    for condition in conditions
                    if condition.role == "control"
                )
                substrate = (
                    await repository.get_fabrication_substrates_for_batch(batch.id)
                )[0]
                now = datetime.now(timezone.utc)

                async def insert_deviation(**overrides: Any) -> None:
                    values: dict[str, Any] = {
                        "fabrication_batch_id": batch.id,
                        "category": "substrate",
                        "severity": "warning",
                        "description": "PostgreSQL constraint probe",
                        "recorded_by_id": instructor.id,
                        "recorded_at": now,
                        "condition_id": control.id,
                        "created_at": now,
                    }
                    values.update(overrides)
                    async with database.engine.begin() as connection:
                        await connection.execute(
                            insert(execution_deviations).values(**values)
                        )

                with self.assertRaises(IntegrityError):
                    await insert_deviation(deviation_type="bogus")
                with self.assertRaises(IntegrityError):
                    await insert_deviation()
                with self.assertRaises(IntegrityError):
                    await insert_deviation(
                        deviation_type="general",
                        substrate_id=substrate.id,
                    )
                # The legal shapes insert cleanly.
                await insert_deviation(deviation_type="general")
                await insert_deviation(deviation_type="fabrication_shortfall")
                await insert_deviation(deviation_type="measurement_shortfall")
            finally:
                await database.dispose()

        asyncio.run(exercise())

    def test_condition_edits_serialize_with_plan_status_transitions(self) -> None:
        """Concurrent condition updates/deletes and plan releases serialize
        on the parent experiment row: no released plan can contain a change
        that escaped validation, and a validated edit cannot be silently
        overwritten by a racing status transition."""

        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]

        async def setup_round(repository: WebRepository, tag: str):
            instructor = await repository.create_user(
                username=f"pg-race6-{tag}",
                display_name="PostgreSQL Condition Race Instructor",
                password_hash=hash_password(f"condition race secret {tag}"),
                role=UserRole.INSTRUCTOR,
            )
            await repository.create_campaign(
                code=f"pg-race6-{tag}",
                display_name=f"PostgreSQL condition race {tag}",
                description="",
                actor_user_id=instructor.id,
            )
            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = [dict(layer) for layer in device_recipe["layers"]]
                    group["deposition_process"] = deepcopy(deposition_process)
            device_recipe["substrate"]["width_mm"] = 15.0
            device_recipe["substrate"]["length_mm"] = 15.0
            recipe = DepositionRecipe.from_mapping(
                {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                }
            )
            record = await repository.add_experiment(
                recipe,
                campaign_id=f"pg-race6-{tag}",
                condition_plans=[
                    {
                        "group_id": group["group_id"],
                        "role": group["kind"],
                        "device_layout_code": "15x15_dual_005",
                        "planned_substrate_count": 3,
                    }
                    for group in device_recipe["experimental_groups"]
                ],
                actor_user_id=instructor.id,
            )
            # Park the plan at approved so the race is between a condition
            # edit (which resets to draft) and the release transition.
            await repository.update_plan_status(
                record.id, PlanStatus.PENDING_APPROVAL, actor_user_id=instructor.id
            )
            await repository.update_plan_status(
                record.id, PlanStatus.APPROVED, actor_user_id=instructor.id
            )
            conditions = await repository.list_conditions_for_experiment(
                record.id
            )
            return instructor.id, record.id, conditions[0]

        async def run_round(round_index: int, mode: str) -> None:
            tag = f"{uuid4().hex[:10]}-{round_index}-{mode}"
            setup_database = Database(url)
            try:
                repository = WebRepository(setup_database)
                await seed_standard_layouts_async(setup_database)
                instructor_id, experiment_id, condition = await setup_round(
                    repository, tag
                )
            finally:
                await setup_database.dispose()

            databases = [Database(url), Database(url)]
            try:
                async def edit_condition(database: Database) -> None:
                    repo = WebRepository(database)
                    if mode == "update":
                        await repo.update_condition(
                            condition.id,
                            condition_name=f"{condition.condition_name} (edited)",
                            recipe_snapshot=dict(condition.recipe_snapshot),
                            source_baseline_version_id=condition.source_baseline_version_id,
                            device_layout_code=condition.device_layout_code,
                            planned_substrate_count=condition.planned_substrate_count,
                            actor_user_id=instructor_id,
                        )
                    else:
                        await repo.delete_condition(
                            condition.id, actor_user_id=instructor_id
                        )

                async def release_plan(database: Database) -> None:
                    await WebRepository(database).update_plan_status(
                        experiment_id,
                        PlanStatus.RELEASED,
                        actor_user_id=instructor_id,
                    )

                outcomes = await asyncio.gather(
                    edit_condition(databases[0]),
                    release_plan(databases[1]),
                    return_exceptions=True,
                )
            finally:
                for database in databases:
                    await database.dispose()

            errors = [
                outcome
                for outcome in outcomes
                if isinstance(outcome, BaseException)
            ]
            successes = [
                outcome
                for outcome in outcomes
                if not isinstance(outcome, BaseException)
            ]
            self.assertEqual(
                len(successes), 1,
                f"exactly one side may commit (round {round_index}, {mode}): "
                f"{outcomes!r}",
            )
            self.assertEqual(len(errors), 1, outcomes)

            verify_database = Database(url)
            try:
                async with verify_database.engine.connect() as connection:
                    final_status = await connection.scalar(
                        select(experiments.c.plan_status).where(
                            experiments.c.id == experiment_id
                        )
                    )
                repository = WebRepository(verify_database)
                await seed_standard_layouts_async(verify_database)
                if final_status == PlanStatus.RELEASED.value:
                    if mode == "update":
                        final_condition = await repository.get_condition(condition.id)
                        self.assertEqual(
                            final_condition.condition_name,
                            condition.condition_name,
                            "a released plan must not contain an unvalidated "
                            "condition edit",
                        )
                    else:
                        remaining = await repository.list_conditions_for_experiment(
                            experiment_id
                        )
                        self.assertTrue(
                            any(row.id == condition.id for row in remaining),
                            "a released plan must not contain a deletion "
                            "that escaped validation",
                        )
                else:
                    self.assertEqual(final_status, PlanStatus.DRAFT.value)
            finally:
                await verify_database.dispose()

        async def run_all() -> None:
            for round_index in range(5):
                for mode in ("update", "delete"):
                    await run_round(round_index, mode)

        asyncio.run(run_all())

    def test_two_concurrent_completions_commit_exactly_once(self) -> None:
        """Two transactions completing the same batch simultaneously must
        serialize: exactly one may commit, the other must fail."""

        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]

        async def seed() -> tuple[int, int]:
            database = Database(url)
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                instructor = await repository.create_user(
                    username=f"pg-comp-{suffix}",
                    display_name="PostgreSQL Concurrent Completion Instructor",
                    password_hash=hash_password(f"comp secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository,
                    f"pg-comp-{suffix}",
                    actor_user_id=instructor.id,
                )
                batch = await repository.create_fabrication_batch(
                    experiment_id,
                    actor_user_id=instructor.id,
                )
                for status_name in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                    await repository.update_fabrication_batch_status(
                        batch.id, status_name, actor_user_id=instructor.id
                    )
                for preparation in await repository.list_solution_preparations(
                    batch.id
                ):
                    await repository.update_solution_preparation(
                        preparation.id,
                        status=PreparationStatus.DISCARDED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                for execution in await repository.list_process_executions(batch.id):
                    await repository.update_process_execution(
                        execution.id,
                        status=ExecutionStatus.CANCELLED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                conditions = await repository.get_fabrication_batch_conditions(
                    batch.id
                )
                actual = {c.id: 3 for c in conditions}
                return batch.id, (actual, instructor.id)
            finally:
                await database.dispose()

        batch_id, (actual, instructor_id) = asyncio.run(seed())

        async def run_concurrent() -> tuple[list[Any], list[Any]]:
            databases = [Database(url), Database(url)]
            try:
                async def complete(database: Database) -> Any:
                    return await WebRepository(database).update_fabrication_batch_status(
                        batch_id,
                        BatchStatus.COMPLETED,
                        actual_substrate_counts=actual,
                        actor_user_id=instructor_id,
                    )

                outcomes = await asyncio.gather(
                    complete(databases[0]),
                    complete(databases[1]),
                    return_exceptions=True,
                )
            finally:
                for database in databases:
                    await database.dispose()
            errors = [o for o in outcomes if isinstance(o, BaseException)]
            successes = [o for o in outcomes if not isinstance(o, BaseException)]
            return successes, errors

        successes, errors = asyncio.run(run_concurrent())
        self.assertEqual(len(successes), 1, f"exactly one completion may commit: {successes!r} {errors!r}")
        self.assertEqual(len(errors), 1)

        async def verify() -> None:
            verify_db = Database(url)
            try:
                repo = WebRepository(verify_db)
                batch = await repo.get_fabrication_batch(batch_id)
                self.assertEqual(batch.status, BatchStatus.COMPLETED)
            finally:
                await verify_db.dispose()

        asyncio.run(verify())

    def test_condition_creation_serializes_with_plan_release(self) -> None:
        """create_condition and release must serialize on the parent
        experiment row: a condition creation that races a release either
        commits first or is rejected — it can never downgrade a released
        plan back to draft."""

        from web.repository import ConditionRole
        from web.condition_snapshot import build_condition_snapshot

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]

        device_recipe, deposition_process = complete_guided_setup()
        # Give the target its own layers so release does not demand manual
        # review (same contract as _create_released_experiment_with_conditions).
        import json as json_module

        for group in device_recipe["experimental_groups"]:
            if group["kind"] == "target":
                group["adjustments"] = []
                group["layers"] = [
                    dict(layer) for layer in device_recipe["layers"]
                ]
                group["deposition_process"] = json_module.loads(
                    json_module.dumps(deposition_process)
                )
        condition_snapshot = build_condition_snapshot(
            device_recipe, deposition_process=deposition_process
        )

        async def seed() -> tuple[int, int]:
            database = Database(url)
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                instructor = await repository.create_user(
                    username=f"pg-cond-race-{suffix}",
                    display_name="PostgreSQL Condition Race Instructor",
                    password_hash=hash_password(f"cond secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                await repository.create_campaign(
                    code=f"pg-cond-race-{suffix}",
                    display_name=f"Test pg-cond-race-{suffix}",
                    description="",
                    actor_user_id=instructor.id,
                )
                recipe = DepositionRecipe.from_mapping(
                    {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    }
                )
                record = await repository.add_experiment(
                    recipe,
                    campaign_id=f"pg-cond-race-{suffix}",
                    actor_user_id=instructor.id,
                )
                initial_conditions = len(
                    await repository.list_conditions_for_experiment(record.id)
                )
                return (
                    record.id,
                    instructor.id,
                    record.experiment_code,
                    initial_conditions,
                )
            finally:
                await database.dispose()

        experiment_id, instructor_id, experiment_code, initial_conditions = (
            asyncio.run(seed())
        )

        async def run_concurrent() -> tuple[list[Any], list[Any]]:
            databases = [Database(url), Database(url)]
            try:

                async def create_condition(database: Database) -> Any:
                    return await WebRepository(database).create_condition(
                        experiment_id=experiment_id,
                        role=ConditionRole.TARGET,
                        condition_code=f"{experiment_code}-T2",
                        condition_name="Raced target",
                        recipe_snapshot=condition_snapshot,
                        source_baseline_version_id=None,
                        device_layout_code="25x25_six_010",
                        planned_substrate_count=3,
                        actor_user_id=instructor_id,
                    )

                async def release(database: Database) -> Any:
                    repo = WebRepository(database)
                    for status_name in (
                        PlanStatus.PENDING_APPROVAL,
                        PlanStatus.APPROVED,
                        PlanStatus.RELEASED,
                    ):
                        await repo.update_plan_status(
                            experiment_id,
                            status_name,
                            actor_user_id=instructor_id,
                        )

                outcomes = await asyncio.gather(
                    create_condition(databases[0]),
                    release(databases[1]),
                    return_exceptions=True,
                )
            finally:
                for database in databases:
                    await database.dispose()
            successes = [o for o in outcomes if not isinstance(o, BaseException)]
            errors = [o for o in outcomes if isinstance(o, BaseException)]
            return successes, errors

        successes, errors = asyncio.run(run_concurrent())
        unexpected = [
            error
            for error in errors
            if not (
                isinstance(error, ValueError)
                and "released or closed plans" in str(error)
            )
        ]
        self.assertEqual(unexpected, [], f"unexpected errors: {unexpected!r}")

        async def verify() -> None:
            verify_db = Database(url)
            try:
                # The invariant under repair: the plan must end released, and
                # a condition creation that lost the race must not have been
                # able to downgrade it back to draft.
                connection = await verify_db.engine.connect()
                row = (
                    await connection.execute(
                        select(
                            experiments.c.plan_status,
                            func.count(experiment_conditions.c.id),
                        )
                        .join(
                            experiment_conditions,
                            experiment_conditions.c.experiment_id
                            == experiments.c.id,
                            isouter=True,
                        )
                        .where(experiments.c.id == experiment_id)
                        .group_by(experiments.c.plan_status)
                    )
                ).one()
                await connection.close()
                self.assertEqual(row[0], PlanStatus.RELEASED.value)
                if not errors:
                    # create_condition won the race: its condition exists.
                    self.assertEqual(row[1], initial_conditions + 1)
                else:
                    self.assertEqual(row[1], initial_conditions)
            finally:
                await verify_db.dispose()

        asyncio.run(verify())

    def test_0014_repairs_assignment_rows_with_legacy_substrate_ids(self) -> None:
        """Migration 0014 updates result_device_assignments.analysis_substrate_id
        from truncated legacy IDs to full laser marks when the mapping is
        unambiguous.  Files with unmapped assignment IDs stay at schema 2."""

        import json as json_module
        from pathlib import Path

        from alembic import command
        from alembic.config import Config as AlembicConfig
        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )
        from web.database import (
            result_device_assignments as rda_table,
            result_files as result_files_table,
        )

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]
        root = Path(__file__).resolve().parents[1]
        alembic_config = AlembicConfig(str(root / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(root / "migrations"))
        previous_url = os.environ.get("PEROVSKITE_DATABASE_URL")
        os.environ["PEROVSKITE_DATABASE_URL"] = url

        async def seed() -> dict[str, Any]:
            database = Database(url)
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                instructor = await repository.create_user(
                    username=f"pg-assign-{suffix}",
                    display_name="PostgreSQL Assignment Repair Instructor",
                    password_hash=hash_password(f"assign secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository,
                    f"pg-assign-{suffix}",
                    actor_user_id=instructor.id,
                )
                batch = await repository.create_fabrication_batch(
                    experiment_id,
                    actor_user_id=instructor.id,
                )
                for status_name in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                    await repository.update_fabrication_batch_status(
                        batch.id, status_name, actor_user_id=instructor.id
                    )
                for preparation in await repository.list_solution_preparations(
                    batch.id
                ):
                    await repository.update_solution_preparation(
                        preparation.id,
                        status=PreparationStatus.DISCARDED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                for execution in await repository.list_process_executions(batch.id):
                    await repository.update_process_execution(
                        execution.id,
                        status=ExecutionStatus.CANCELLED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                conditions = await repository.get_fabrication_batch_conditions(
                    batch.id
                )
                control = next(c for c in conditions if c.role == "control")
                await repository.update_fabrication_batch_status(
                    batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={c.id: 3 for c in conditions},
                    actor_user_id=instructor.id,
                )
                now = datetime.now(timezone.utc)
                # Legacy analysis with truncated substrate ID "A01" and
                # device_mark "A011", label "A011 Channel 1.Forward".
                legacy_repairable = {
                    "schema_version": 2,
                    "devices": [
                        {
                            "device_id": "device-001",
                            "label": "A011 Channel 1.Forward",
                            "device_mark": "A011",
                            "substrate_id": "A01",
                            "group_id": str(control.id),
                            "metrics": {"voc": 1.0},
                        }
                    ],
                    "substrates": [
                        {
                            "substrate_id": "A01",
                            "device_ids": ["device-001"],
                            "instrument_labels": ["A011 Channel 1.Forward"],
                            "group_id": str(control.id),
                            "batch_condition_id": control.id,
                        }
                    ],
                    "summary": {"voc": 1.0},
                    "statistics": {},
                }
                # Legacy analysis with unmapped assignment ID "Z99" —
                # the assignment row references "Z99" but the analysis
                # doesn't have a device with that substrate_id, so the
                # mapping is broken and this file must stay at schema 2.
                legacy_unmapped = {
                    "schema_version": 2,
                    "devices": [
                        {
                            "device_id": "device-002",
                            "label": "B012 Channel 1.Forward",
                            "device_mark": "B012",
                            "substrate_id": "B01",
                            "group_id": str(control.id),
                            "metrics": {"voc": 1.0},
                        }
                    ],
                    "substrates": [
                        {
                            "substrate_id": "B01",
                            "device_ids": ["device-002"],
                            "instrument_labels": ["B012 Channel 1.Forward"],
                            "group_id": str(control.id),
                            "batch_condition_id": control.id,
                        }
                    ],
                    "summary": {"voc": 1.0},
                    "statistics": {},
                }
                async with database.engine.begin() as connection:
                    for filename, analysis in (
                        ("repairable.json", legacy_repairable),
                        ("unmapped.json", legacy_unmapped),
                    ):
                        result = await connection.execute(
                            insert(result_files_table).values(
                                experiment_id=experiment_id,
                                fabrication_batch_id=batch.id,
                                filename=filename,
                                content_type="text/csv",
                                size_bytes=64,
                                sha256=uuid4().hex,
                                content=b"legacy",
                                group_assignment="",
                                metrics={"voc": 1.0},
                                analysis=json_module.loads(
                                    json_module.dumps(analysis)
                                ),
                                analysis_schema_version=2,
                                created_at=now,
                                created_by_id=instructor.id,
                            ).returning(result_files_table.c.id)
                        )
                        file_id = result.scalar_one()
                        # Insert an assignment row with the old truncated ID.
                        old_sub = "A01" if filename == "repairable.json" else "Z99"
                        await connection.execute(
                            insert(rda_table).values(
                                result_file_id=file_id,
                                analysis_device_id="device-001",
                                analysis_substrate_id=old_sub,
                                instrument_label="legacy",
                                batch_condition_id=control.id,
                                fabrication_device_id=1,
                                created_at=now,
                            )
                        )
                return {"batch_id": batch.id, "control_id": control.id}
            finally:
                await database.dispose()

        async def verify(context: dict[str, Any]) -> None:
            database = Database(url)
            try:
                async with database.engine.connect() as connection:
                    # repairable.json: analysis_schema_version=3, assignment
                    # row updated to "A011".
                    row = (
                        await connection.execute(
                            select(
                                result_files_table.c.analysis_schema_version,
                            ).where(
                                result_files_table.c.filename == "repairable.json",
                                result_files_table.c.fabrication_batch_id
                                == context["batch_id"],
                            )
                        )
                    ).one()
                    self.assertEqual(row.analysis_schema_version, 3)
                    assign_sub = (
                        await connection.execute(
                            select(rda_table.c.analysis_substrate_id).where(
                                rda_table.c.result_file_id.in_(
                                    select(result_files_table.c.id).where(
                                        result_files_table.c.filename
                                        == "repairable.json",
                                        result_files_table.c.fabrication_batch_id
                                        == context["batch_id"],
                                    )
                                )
                            )
                        )
                    ).scalar_one()
                    self.assertEqual(assign_sub, "A011")

                    # unmapped.json: analysis stays at schema 2 (assignment
                    # row references "Z99" which is not in the mapping).
                    row2 = (
                        await connection.execute(
                            select(
                                result_files_table.c.analysis_schema_version,
                            ).where(
                                result_files_table.c.filename == "unmapped.json",
                                result_files_table.c.fabrication_batch_id
                                == context["batch_id"],
                            )
                        )
                    ).one()
                    self.assertEqual(row2.analysis_schema_version, 2)
            finally:
                await database.dispose()

        try:
            # Downgrade to 0013 so seed runs at pre-0014 level.
            command.downgrade(alembic_config, "0013_substrate_laser_marks")
            context = asyncio.run(seed())
            # Upgrade to head: 0014 repairs legacy analyses + assignments.
            command.upgrade(alembic_config, "head")
            asyncio.run(verify(context))
        finally:
            if previous_url is None:
                os.environ.pop("PEROVSKITE_DATABASE_URL", None)
            else:
                os.environ["PEROVSKITE_DATABASE_URL"] = previous_url

    def test_populated_0012_to_head_to_0013_to_head_cycle(self) -> None:
        """A populated 0012-shaped database upgrades to head (0014) with
        repaired legacy analyses, downgrades to 0013, and upgrades to head
        again — all against real PostgreSQL."""

        import json as json_module
        from pathlib import Path

        from alembic import command
        from alembic.config import Config
        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )
        from web.database import (
            fabrication_batch_conditions as batch_conditions_table,
            fabrication_devices,
            result_files as result_files_table,
        )

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]
        root = Path(__file__).resolve().parents[1]
        alembic_config = Config(str(root / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(root / "migrations"))
        previous_url = os.environ.get("PEROVSKITE_DATABASE_URL")
        os.environ["PEROVSKITE_DATABASE_URL"] = url

        async def seed() -> dict[str, Any]:
            database = Database(url)
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            try:
                instructor = await repository.create_user(
                    username=f"pg-cycle-{suffix}",
                    display_name="PostgreSQL Cycle Instructor",
                    password_hash=hash_password(f"cycle secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository,
                    f"pg-cycle-{suffix}",
                    actor_user_id=instructor.id,
                )
                batch = await repository.create_fabrication_batch(
                    experiment_id,
                    actor_user_id=instructor.id,
                )
                for status_name in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                    await repository.update_fabrication_batch_status(
                        batch.id, status_name, actor_user_id=instructor.id
                    )
                for preparation in await repository.list_solution_preparations(
                    batch.id
                ):
                    await repository.update_solution_preparation(
                        preparation.id,
                        status=PreparationStatus.DISCARDED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                for execution in await repository.list_process_executions(batch.id):
                    await repository.update_process_execution(
                        execution.id,
                        status=ExecutionStatus.CANCELLED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                conditions = await repository.get_fabrication_batch_conditions(
                    batch.id
                )
                control = next(
                    condition
                    for condition in conditions
                    if condition.role == "control"
                )
                await repository.update_fabrication_batch_status(
                    batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={
                        condition.id: 3 for condition in conditions
                    },
                    actor_user_id=instructor.id,
                )
                now = datetime.now(timezone.utc)
                legacy_unambiguous = {
                    "schema_version": 2,
                    "devices": [
                        {
                            "device_id": "device-001",
                            "label": "A011 Channel 1.Forward",
                            "device_mark": "A011",
                            "substrate_id": "A01",
                            "group_id": str(control.id),
                            "metrics": {"voc": 1.0},
                        }
                    ],
                    "substrates": [
                        {
                            "substrate_id": "A01",
                            "device_ids": ["device-001"],
                            "instrument_labels": ["A011 Channel 1.Forward"],
                            "group_id": str(control.id),
                            "batch_condition_id": control.id,
                            "condition_code": control.condition_code,
                            "condition_name": control.condition_name,
                        }
                    ],
                    "summary": {"voc": 1.0},
                    "statistics": {},
                }
                legacy_ambiguous = {
                    "schema_version": 2,
                    "devices": [
                        {
                            "device_id": "device-001",
                            "label": "B012.Forward",
                            "device_mark": "B012",
                            "substrate_id": "B01",
                        },
                        {
                            "device_id": "device-002",
                            "label": "B777.Forward",
                            "device_mark": "B777",
                            "substrate_id": "B01",
                        },
                    ],
                    "substrates": [
                        {
                            "substrate_id": "B01",
                            "device_ids": ["device-001", "device-002"],
                            "instrument_labels": ["B012.Forward", "B777.Forward"],
                        }
                    ],
                    "summary": {},
                    "statistics": {},
                }
                async with database.engine.begin() as connection:
                    await connection.execute(
                        update(batch_conditions_table)
                        .where(
                            batch_conditions_table.c.fabrication_batch_id
                            == batch.id
                        )
                        .values(actual_substrate_count=None)
                    )
                    for filename, analysis in (
                        ("legacy-unambiguous.json", legacy_unambiguous),
                        ("legacy-ambiguous.json", legacy_ambiguous),
                    ):
                        await connection.execute(
                            insert(result_files_table).values(
                                experiment_id=experiment_id,
                                fabrication_batch_id=batch.id,
                                filename=filename,
                                content_type="application/json",
                                size_bytes=64,
                                sha256=uuid4().hex,
                                content=b"legacy",
                                group_assignment="",
                                metrics={"voc": 1.0},
                                analysis=json_module.loads(
                                    json_module.dumps(analysis)
                                ),
                                analysis_schema_version=2,
                                created_at=now,
                                created_by_id=instructor.id,
                            )
                        )
                return {
                    "batch_id": batch.id,
                    "control_id": control.id,
                    "condition_count": len(conditions),
                }
            finally:
                await database.dispose()

        async def verify(context: dict[str, Any]) -> None:
            database = Database(url)
            try:
                async with database.engine.connect() as connection:
                    counts = (
                        await connection.execute(
                            select(
                                batch_conditions_table.c.id,
                                batch_conditions_table.c.actual_substrate_count,
                                batch_conditions_table.c.planned_substrate_count,
                            ).where(
                                batch_conditions_table.c.fabrication_batch_id
                                == context["batch_id"]
                            )
                        )
                    ).all()
                    self.assertEqual(len(counts), context["condition_count"])
                    for _, actual, planned in counts:
                        self.assertEqual(
                            actual,
                            planned,
                            "completed pre-0013 conditions must backfill the "
                            "planned count as the conservative actual value",
                        )
                    # Unambiguous legacy analysis repaired to schema 3.
                    repaired = (
                        await connection.execute(
                            select(
                                result_files_table.c.analysis,
                                result_files_table.c.analysis_schema_version,
                            ).where(
                                result_files_table.c.filename
                                == "legacy-unambiguous.json",
                                result_files_table.c.fabrication_batch_id
                                == context["batch_id"],
                            )
                        )
                    ).one()
                    self.assertEqual(repaired.analysis_schema_version, 3)
                    self.assertEqual(repaired.analysis["schema_version"], 3)
                    self.assertEqual(
                        repaired.analysis["devices"][0]["device_ordinal"], 1
                    )
                    self.assertEqual(
                        repaired.analysis["devices"][0]["substrate_id"], "A011"
                    )
                    self.assertEqual(
                        repaired.analysis["substrates"][0]["substrate_id"], "A011"
                    )
                    preserved = repaired.analysis["substrates"][0]
                    self.assertEqual(preserved["group_id"], str(context["control_id"]))
                    self.assertEqual(
                        preserved["batch_condition_id"], context["control_id"]
                    )
                    # Ambiguous legacy analysis left at schema 2.
                    ambiguous = (
                        await connection.execute(
                            select(
                                result_files_table.c.analysis,
                                result_files_table.c.analysis_schema_version,
                            ).where(
                                result_files_table.c.filename
                                == "legacy-ambiguous.json",
                                result_files_table.c.fabrication_batch_id
                                == context["batch_id"],
                            )
                        )
                    ).one()
                    self.assertEqual(ambiguous.analysis_schema_version, 2)
                    self.assertEqual(ambiguous.analysis["schema_version"], 2)
                    device_count = int(
                        await connection.scalar(
                            select(func.count())
                            .select_from(fabrication_devices)
                            .where(
                                fabrication_devices.c.substrate_id.in_(
                                    select(
                                        fabrication_substrates.c.id
                                    ).where(
                                        fabrication_substrates.c.batch_condition_id
                                        == context["control_id"]
                                    )
                                )
                            )
                        )
                        or 0
                    )
                    self.assertGreater(device_count, 0)
            finally:
                await database.dispose()

        try:
            # Start at 0013 (downgrade from head first so seed runs at the
            # 0013 schema level, before 0014's backfill/repair).
            command.downgrade(alembic_config, "0013_substrate_laser_marks")
            context = asyncio.run(seed())
            # 0013 → head (0014): backfill actual counts + legacy repair.
            command.upgrade(alembic_config, "head")
            asyncio.run(verify(context))
            # head → 0013: downgrade 0014 only (safe).
            command.downgrade(alembic_config, "0013_substrate_laser_marks")
            # 0013 → head: upgrade again, repairs remain idempotent.
            command.upgrade(alembic_config, "head")
            asyncio.run(verify(context))
        finally:
            if previous_url is None:
                os.environ.pop("PEROVSKITE_DATABASE_URL", None)
            else:
                os.environ["PEROVSKITE_DATABASE_URL"] = previous_url

    def test_0013_to_0012_downgrade_blocked_with_unchanged_fingerprint(self) -> None:
        """Downgrading from 0013 to 0012 must raise RuntimeError immediately
        (before any DDL/DML) and leave the schema/data fingerprint unchanged."""

        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        root = Path(__file__).resolve().parents[1]
        alembic_config = Config(str(root / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(root / "migrations"))
        previous_url = os.environ.get("PEROVSKITE_DATABASE_URL")
        os.environ["PEROVSKITE_DATABASE_URL"] = url

        async def fingerprint() -> dict[str, Any]:
            database = Database(url)
            try:
                async with database.engine.connect() as connection:
                    revision = await connection.scalar(
                        text("SELECT version_num FROM alembic_version LIMIT 1")
                    )
                    sub_width = await connection.scalar(
                        text(
                            "SELECT character_maximum_length "
                            "FROM information_schema.columns "
                            "WHERE table_name='fabrication_substrates' "
                            "AND column_name='substrate_mark'"
                        )
                    )
                    actual_col = await connection.scalar(
                        text(
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_name='fabrication_batch_conditions' "
                            "AND column_name='actual_substrate_count'"
                        )
                    )
                    dev_type_col = await connection.scalar(
                        text(
                            "SELECT count(*) FROM information_schema.columns "
                            "WHERE table_name='execution_deviations' "
                            "AND column_name='deviation_type'"
                        )
                    )
                    sub_count = await connection.scalar(
                        text("SELECT count(*) FROM fabrication_substrates")
                    )
                    return {
                        "revision": str(revision),
                        "sub_mark_width": sub_width,
                        "has_actual_count": int(actual_col or 0),
                        "has_deviation_type": int(dev_type_col or 0),
                        "substrate_rows": int(sub_count or 0),
                    }
            finally:
                await database.dispose()

        try:
            # Start at 0013 (downgrade from head first).
            command.downgrade(alembic_config, "0013_substrate_laser_marks")
            before = asyncio.run(fingerprint())
            self.assertEqual(before["revision"], "0013_substrate_laser_marks")

            # The downgrade must raise RuntimeError immediately.
            with self.assertRaises(RuntimeError) as context_manager:
                command.downgrade(alembic_config, "0012_baseline_scope_owner")
            self.assertIn("intentionally blocked", str(context_manager.exception))

            # Schema/data fingerprint must be identical after the failed attempt.
            after = asyncio.run(fingerprint())
            self.assertEqual(before, after)

            # Restore to head for subsequent tests.
            command.upgrade(alembic_config, "head")
        finally:
            if previous_url is None:
                os.environ.pop("PEROVSKITE_DATABASE_URL", None)
            else:
                os.environ["PEROVSKITE_DATABASE_URL"] = previous_url

    def test_completion_materializes_actual_counts_on_postgresql(self) -> None:
        """An actual>planned completion materializes substrate, device, and
        execution-member rows under the real PostgreSQL constraints, and a
        failed or repeated completion leaves no duplicates behind."""

        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        async def exercise() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            suffix = uuid4().hex[:12]
            try:
                instructor = await repository.create_user(
                    username=f"pg-actual-{suffix}",
                    display_name="PostgreSQL Actual Counts Instructor",
                    password_hash=hash_password(
                        f"actual counts secret {suffix}"
                    ),
                    role=UserRole.INSTRUCTOR,
                )
                experiment_id = await _create_released_experiment_with_conditions(
                    repository,
                    f"pg-actual-{suffix}",
                    actor_user_id=instructor.id,
                )
                batch = await repository.create_fabrication_batch(
                    experiment_id,
                    actor_user_id=instructor.id,
                )
                for status_name in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                    await repository.update_fabrication_batch_status(
                        batch.id, status_name, actor_user_id=instructor.id
                    )
                for preparation in await repository.list_solution_preparations(
                    batch.id
                ):
                    await repository.update_solution_preparation(
                        preparation.id,
                        status=PreparationStatus.DISCARDED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                for execution in await repository.list_process_executions(batch.id):
                    await repository.update_process_execution(
                        execution.id,
                        status=ExecutionStatus.CANCELLED,
                        fabrication_batch_id=batch.id,
                        actor_user_id=instructor.id,
                    )
                conditions = await repository.get_fabrication_batch_conditions(
                    batch.id
                )
                control = next(
                    condition
                    for condition in conditions
                    if condition.role == "control"
                )

                async def substrate_rows() -> list[Any]:
                    rows = await repository.get_fabrication_substrates_for_batch(
                        batch.id
                    )
                    return sorted(
                        (
                            row
                            for row in rows
                            if row.batch_condition_id == control.id
                        ),
                        key=lambda row: row.substrate_ordinal,
                    )

                # A payload missing one condition rolls back completely.
                with self.assertRaisesRegex(ValueError, "must cover exactly"):
                    await repository.update_fabrication_batch_status(
                        batch.id,
                        BatchStatus.COMPLETED,
                        actual_substrate_counts={control.id: 5},
                        actor_user_id=instructor.id,
                    )
                self.assertEqual(len(await substrate_rows()), 3)

                await repository.update_fabrication_batch_status(
                    batch.id,
                    BatchStatus.COMPLETED,
                    actual_substrate_counts={
                        condition.id: 5 for condition in conditions
                    },
                    actor_user_id=instructor.id,
                )
                rows = await substrate_rows()
                self.assertEqual(len(rows), 5)
                self.assertEqual(
                    [row.substrate_ordinal for row in rows],
                    [1, 2, 3, 4, 5],
                )
                self.assertTrue(all(row.substrate_mark is None for row in rows))

                devices = await repository.get_fabrication_devices_for_batch(
                    batch.id
                )
                control_device_codes = sorted(
                    device.device_code
                    for device in devices
                    if device.substrate_id in {row.id for row in rows}
                )
                self.assertEqual(
                    control_device_codes,
                    sorted(
                        f"{row.substrate_code}-D0{index}"
                        for row in rows
                        for index in (1, 2)
                    ),
                )

                executions = await repository.list_process_executions(batch.id)
                control_ids = {row.id for row in rows}
                for execution in executions:
                    members = await repository.list_process_execution_members(
                        execution.id
                    )
                    if not any(
                        int(member["batch_condition_id"]) == control.id
                        for member in members
                    ):
                        continue
                    self.assertTrue(
                        control_ids
                        <= {
                            int(member["substrate_id"]) for member in members
                        },
                        f"execution {execution.execution_code} is missing "
                        "members for materialized substrates",
                    )

                with self.assertRaisesRegex(ValueError, "cannot change"):
                    await repository.update_fabrication_batch_status(
                        batch.id,
                        BatchStatus.COMPLETED,
                        actual_substrate_counts={
                            condition.id: 5 for condition in conditions
                        },
                        actor_user_id=instructor.id,
                    )
                self.assertEqual(len(await substrate_rows()), 5)
                devices = await repository.get_fabrication_devices_for_batch(
                    batch.id
                )
                self.assertEqual(len(devices), 2 * 5 * 2)
            finally:
                await database.dispose()

        asyncio.run(exercise())

    def test_concurrent_same_mark_assignment_commits_exactly_once(self) -> None:
        """Two transactions assigning the same laser mark in one batch must
        serialize on the parent batch row: exactly one may commit."""

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]
        accounts = {
            "instructor": (
                f"pg3-race-instructor-{suffix}",
                f"PostgreSQL race instructor password {suffix}",
                UserRole.INSTRUCTOR,
            ),
            "owner": (
                f"pg3-race-owner-{suffix}",
                f"PostgreSQL race owner password {suffix}",
                UserRole.STUDENT,
            ),
        }
        setup_database = Database(url)
        try:
            async def seed_users() -> None:
                for username, password, role in accounts.values():
                    await WebRepository(setup_database).create_user(
                        username=username,
                        display_name=username,
                        password_hash=hash_password(password, username=username),
                        role=role,
                    )

            asyncio.run(seed_users())
        finally:
            asyncio.run(setup_database.dispose())

        def channel_csv(current: float) -> bytes:
            rows = [
                ["No.", "1", "", "", "", "", ""],
                [
                    "[Information]",
                    "",
                    "[Volt (V)]",
                    "[Current (mA)]",
                    "[J (mA/cm^2)]",
                    "",
                    "",
                ],
                ["Name", "A001 Channel 1.Forward", "0", "-2", str(-current), "", ""],
                ["", "", "0.5", "-2", str(-current), "", ""],
                ["", "", "1", "0", "0", "", ""],
                ["No.", "2", "", "", "", "", ""],
                [
                    "[Information]",
                    "",
                    "[Volt (V)]",
                    "[Current (mA)]",
                    "[J (mA/cm^2)]",
                    "",
                    "",
                ],
                ["Name", "A001 Channel 1.Reverse", "0", "-2", str(-current), "", ""],
                ["", "", "0.5", "-2", str(-current), "", ""],
                ["", "", "1", "0", "0", "", ""],
            ]
            return (
                "\n".join(",".join(row) for row in rows) + "\n"
            ).encode("utf-8")

        app = create_app(url, secure_cookies=False)
        with TestClient(app, base_url="https://testserver") as client:
            def login(account: str) -> None:
                username, password, _ = accounts[account]
                login_csrf = client.get("/api/auth/login-csrf")
                self.assertEqual(login_csrf.status_code, 200)
                response = client.post(
                    "/api/auth/login",
                    json={
                        "username": username,
                        "password": password,
                        "login_csrf": login_csrf.json()["login_csrf_token"],
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                client.headers["X-CSRF-Token"] = client.cookies.get(
                    "perovskite_csrf"
                )

            def logout() -> None:
                response = client.post("/api/auth/logout")
                self.assertEqual(response.status_code, 204, response.text)
                client.headers.pop("X-CSRF-Token", None)

            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = deepcopy(device_recipe["layers"])
                    group["deposition_process"] = deepcopy(deposition_process)

            login("instructor")
            campaign = client.post(
                "/api/campaigns",
                json={
                    "code": f"pg3-race-{suffix}",
                    "display_name": f"PostgreSQL race campaign {suffix}",
                    "description": "Disposable laser-mark race campaign",
                },
            )
            self.assertEqual(campaign.status_code, 201, campaign.text)
            baseline = client.post(
                "/api/baselines",
                json={
                    "name": f"PostgreSQL race baseline {suffix}",
                    "device_recipe": deepcopy(device_recipe),
                    "deposition_process": deepcopy(deposition_process),
                },
            )
            self.assertEqual(baseline.status_code, 201, baseline.text)
            logout()

            login("owner")
            created = client.post(
                "/api/experiments",
                json={
                    "recipe": {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    },
                    "campaign_id": f"pg3-race-{suffix}",
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
            self.assertEqual(created.status_code, 201, created.text)
            experiment_id = int(created.json()["id"])
            submitted = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "pending_approval"},
            )
            self.assertEqual(submitted.status_code, 204, submitted.text)
            logout()
            login("instructor")
            for status_name in ("approved", "released"):
                transition = client.patch(
                    f"/api/experiments/{experiment_id}/plan-status",
                    json={"status": status_name},
                )
                self.assertEqual(transition.status_code, 204, transition.text)
            logout()
            login("owner")
            batch = client.post(
                f"/api/experiments/{experiment_id}/fabrication-batches",
                json={"notes": "PostgreSQL laser-mark race batch"},
            )
            self.assertEqual(batch.status_code, 201, batch.text)
            batch_id = int(batch.json()["id"])
            for status_name in ("ready", "in_progress"):
                transition = client.patch(
                    f"/api/fabrication-batches/{batch_id}/status",
                    json={"status": status_name},
                )
                self.assertEqual(transition.status_code, 204, transition.text)
            for path, terminal in (
                ("solution-preparations", "discarded"),
                ("process-executions", "cancelled"),
            ):
                rows = client.get(f"/api/fabrication-batches/{batch_id}/{path}")
                self.assertEqual(rows.status_code, 200, rows.text)
                for row in rows.json():
                    transition = client.patch(
                        f"/api/fabrication-batches/{batch_id}/{path}/{row['id']}",
                        json={"status": terminal},
                    )
                    self.assertEqual(transition.status_code, 200, transition.text)
            conditions = client.get(
                f"/api/fabrication-batches/{batch_id}/conditions"
            ).json()
            actual_counts = {}
            shortfall_deviations = []
            for condition in conditions:
                actual_counts[str(condition["id"])] = 1
                shortfall_deviations.append({
                    "condition_id": condition["id"],
                    "description": "Race setup: one substrate per condition was measured.",
                })
            completed = client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={
                    "status": "completed",
                    "actual_substrate_counts": actual_counts,
                    "shortfall_deviations": shortfall_deviations,
                },
            )
            self.assertEqual(completed.status_code, 204, completed.text)

            file_ids = []
            condition_by_role = {}
            for index, current in enumerate((20.0, 21.0), start=1):
                uploaded = client.post(
                    f"/api/experiments/{experiment_id}/results",
                    files={
                        "result_file": (
                            f"race-{index}.csv",
                            channel_csv(current),
                            "text/csv",
                        )
                    },
                    data={"fabrication_batch_id": str(batch_id)},
                )
                self.assertEqual(uploaded.status_code, 201, uploaded.text)
                file_ids.append(int(uploaded.json()["id"]))
            detail = client.get(f"/api/results/{file_ids[0]}").json()
            for group in detail["groups"]:
                condition_by_role[group["kind"]] = int(
                    group["batch_condition_id"]
                )
            control_id = condition_by_role["control"]
            target_id = condition_by_role["target"]
            analyses = [
                client.get(f"/api/results/{file_id}").json()["analysis"]
                for file_id in file_ids
            ]
            for analysis in analyses:
                self.assertEqual(
                    analysis["substrates"][0]["substrate_id"], "A001"
                )
            logout()

        async def run_race() -> list[Any]:
            groups = [
                {
                    "group_id": str(control_id),
                    "name": "Control",
                    "kind": "control",
                },
                {
                    "group_id": str(target_id),
                    "name": "Target 1",
                    "kind": "target",
                },
            ]
            databases = [Database(url), Database(url)]
            try:
                async def assign(
                    database: Database,
                    file_id: int,
                    analysis: dict[str, Any],
                    condition_id: int,
                ) -> Any:
                    grouped = assign_substrates_to_groups(
                        analysis, {"A001": str(condition_id)}, groups
                    )
                    return await WebRepository(database) \
                        .update_result_analysis_and_complete(
                            file_id,
                            grouped,
                            substrate_assignments={"A001": condition_id},
                            group_assignment="concurrent race",
                            actor_user_id=1,
                        )

                return await asyncio.gather(
                    assign(databases[0], file_ids[0], analyses[0], control_id),
                    assign(databases[1], file_ids[1], analyses[1], target_id),
                    return_exceptions=True,
                )
            finally:
                for database in databases:
                    await database.dispose()

        outcomes = asyncio.run(run_race())
        errors = [
            outcome for outcome in outcomes if isinstance(outcome, BaseException)
        ]
        successes = [
            outcome for outcome in outcomes if not isinstance(outcome, BaseException)
        ]
        self.assertEqual(
            len(successes), 1, f"exactly one assignment may commit: {outcomes!r}"
        )
        self.assertEqual(len(errors), 1, outcomes)
        self.assertIn("already associated", str(errors[0]))

        verify_database = Database(url)
        try:
            async def verify() -> tuple[list[str | None], list[int]]:
                async with verify_database.engine.connect() as connection:
                    marked = (
                        await connection.execute(
                            select(fabrication_substrates.c.substrate_mark)
                            .select_from(fabrication_substrates)
                            .join(
                                fabrication_batch_conditions,
                                fabrication_batch_conditions.c.id
                                == fabrication_substrates.c.batch_condition_id,
                            )
                            .where(
                                fabrication_batch_conditions.c.fabrication_batch_id
                                == batch_id,
                                fabrication_substrates.c.substrate_mark == "A001",
                            )
                        )
                    ).scalars().all()
                    file_ids_with_assignments = (
                        await connection.execute(
                            select(
                                result_device_assignments.c.result_file_id
                            )
                            .distinct()
                            .where(
                                result_device_assignments.c.result_file_id.in_(
                                    file_ids
                                )
                            )
                        )
                    ).scalars().all()
                return list(marked), list(file_ids_with_assignments)

            marks, assigned_files = asyncio.run(verify())
            self.assertEqual(
                marks, ["A001"], "the same glass mark must exist once per batch"
            )
            self.assertEqual(len(assigned_files), 1, assigned_files)
            self.assertIn(assigned_files[0], file_ids)
        finally:
            asyncio.run(verify_database.dispose())

    async def _exercise_fabrication_batch(self) -> None:
        from tests.test_fabrication_batches import (
            _create_released_experiment_with_conditions,
        )

        database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
        repository = WebRepository(database)
        await seed_standard_layouts_async(database)
        suffix = uuid4().hex[:12]
        try:
            instructor = await repository.create_user(
                username=f"pg-batch-{suffix}",
                display_name="PostgreSQL Batch Instructor",
                password_hash=hash_password(f"batch integration secret {suffix}"),
                role=UserRole.INSTRUCTOR,
            )
            experiment_id = await _create_released_experiment_with_conditions(
                repository,
                f"pg-batch-{suffix}",
                actor_user_id=instructor.id,
            )
            batch = await repository.create_fabrication_batch(
                experiment_id,
                actor_user_id=instructor.id,
            )
            preparations = await repository.list_solution_preparations(batch.id)
            executions = await repository.list_process_executions(batch.id)
            methods = {item.method for item in executions}
            self.assertTrue(
                {"spin_coating", "vcd", "annealing"}.issubset(methods)
            )
            self.assertTrue(preparations)
            self.assertTrue(
                await repository.list_solution_preparation_uses(preparations[0].id)
            )
            self.assertTrue(
                await repository.list_process_execution_members(executions[0].id)
            )
            deviation = await repository.create_deviation(
                fabrication_batch_id=batch.id,
                category="process",
                severity="warning",
                description="PostgreSQL Batch integration deviation",
                process_execution_id=executions[0].id,
                actor_user_id=instructor.id,
            )
            self.assertEqual(deviation.fabrication_batch_id, batch.id)
            with self.assertRaises(ValueError):
                await repository.create_deviation(
                    fabrication_batch_id=batch.id,
                    category="process",
                    severity="warning",
                    description="invalid multiple target",
                    solution_preparation_id=preparations[0].id,
                    process_execution_id=executions[0].id,
                    actor_user_id=instructor.id,
                )
        finally:
            await database.dispose()

    async def _exercise_repository(self) -> None:
        database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
        repository = WebRepository(database)
        await seed_standard_layouts_async(database)
        suffix = uuid4().hex[:12]
        try:
            user = await repository.create_user(
                username=f"ci-{suffix}",
                display_name="CI Student",
                password_hash=hash_password(f"integration test secret {suffix}"),
                role=UserRole.INSTRUCTOR,
            )
            attempted_at = datetime.now(timezone.utc)
            reservations = await asyncio.gather(
                *(
                    repository.reserve_login_attempt(
                        user.id,
                        attempted_at=attempted_at,
                        failure_limit=5,
                        lockout_until=attempted_at + timedelta(minutes=15),
                    )
                    for _ in range(20)
                )
            )
            self.assertEqual(sum(reservations), 5)
            await repository.record_successful_login(user.id)
            await repository.create_campaign(
                code=f"ci-{suffix}",
                display_name=f"CI campaign {suffix}",
                description="PostgreSQL integration test",
                actor_user_id=user.id,
            )
            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["layers"] = deepcopy(device_recipe["layers"])
                    group["deposition_process"] = deepcopy(deposition_process)
                    group["adjustments"] = []
            baseline = await repository.save_baseline(
                f"CI baseline {suffix}",
                device_recipe,
                deposition_process,
                actor_user_id=user.id,
            )
            guided_recipe = DepositionRecipe.from_mapping(
                {
                    **deposition_recipe_from_process(deposition_process),
                    "device_recipe": device_recipe,
                }
            )
            experiment = await repository.add_experiment(
                guided_recipe,
                campaign_id=f"ci-{suffix}",
                source_baseline_version_id=baseline["current_version_id"],
                actor_user_id=user.id,
            )
            conditions = await repository.list_conditions_for_experiment(
                experiment.id
            )
            for target in (
                PlanStatus.PENDING_APPROVAL,
                PlanStatus.APPROVED,
                PlanStatus.RELEASED,
            ):
                await repository.update_plan_status(
                    experiment.id,
                    target,
                    actor_user_id=user.id,
                )
            batch = await repository.create_fabrication_batch(
                experiment.id,
                actor_user_id=user.id,
            )
            for batch_status in (BatchStatus.READY, BatchStatus.IN_PROGRESS):
                await repository.update_fabrication_batch_status(
                    batch.id,
                    batch_status,
                    actor_user_id=user.id,
                )
            analysis = parse_jv_analysis(
                b"voltage,current_density\n0,-20\n1,0\n",
                source_filename="A001 Channel 1.csv",
            )
            result = await repository.add_result(
                experiment.id,
                fabrication_batch_id=batch.id,
                filename="A001 Channel 1.csv",
                content_type="text/csv",
                content=b"voltage,current_density\n0,-20\n1,0\n",
                # The metrics column is a write-time cache pooled from the
                # stored traces; the analysis itself carries no aggregates.
                metrics=_flat_metrics_from_analysis(analysis),
                analysis=analysis,
                actor_user_id=user.id,
                complete_experiment=True,
            )
            completed = await repository.get_experiment(experiment.id)
            async with database.engine.connect() as connection:
                audit_count = int(
                    await connection.scalar(
                        select(func.count())
                        .select_from(audit_events)
                        .where(audit_events.c.actor_user_id == user.id)
                    )
                    or 0
                )
            self.assertEqual(database.engine.dialect.name, "postgresql")
            self.assertEqual(completed.status.value, "completed")
            self.assertEqual([row.role.value for row in conditions], ["control", "target"])
            self.assertTrue(
                all(
                    row.source_baseline_version_id == baseline["current_version_id"]
                    for row in conditions
                )
            )
            self.assertEqual(len(result["sha256"]), 64)
            self.assertGreaterEqual(audit_count, 3)
        finally:
            await database.dispose()

    def test_result_upload_and_assignment_share_one_lock_order(self) -> None:
        """Upload (experiment -> batch) and assignment (experiment -> batch ->
        result file) take their parent row locks in the same order, so running
        them concurrently on one batch commits both without an AB/BA
        deadlock."""

        url = os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"]
        suffix = uuid4().hex[:12]
        accounts = {
            "instructor": (
                f"pg3-lockorder-instructor-{suffix}",
                f"PostgreSQL lock-order instructor password {suffix}",
                UserRole.INSTRUCTOR,
            ),
            "owner": (
                f"pg3-lockorder-owner-{suffix}",
                f"PostgreSQL lock-order owner password {suffix}",
                UserRole.STUDENT,
            ),
        }
        setup_database = Database(url)
        try:
            async def seed_users() -> None:
                for username, password, role in accounts.values():
                    await WebRepository(setup_database).create_user(
                        username=username,
                        display_name=username,
                        password_hash=hash_password(password, username=username),
                        role=role,
                    )

            asyncio.run(seed_users())
        finally:
            asyncio.run(setup_database.dispose())

        def channel_csv(current: float) -> bytes:
            rows = []
            for direction in ("Forward", "Reverse"):
                rows.extend(
                    [
                        ["No.", "1", "", "", "", "", ""],
                        [
                            "[Information]",
                            "",
                            "[Volt (V)]",
                            "[Current (mA)]",
                            "[J (mA/cm^2)]",
                            "",
                            "",
                        ],
                        ["Name", f"A001 Channel 1.{direction}", "0", "-2", str(-current), "", ""],
                        ["", "", "0.5", "-2", str(-current), "", ""],
                        ["", "", "1", "0", "0", "", ""],
                    ]
                )
            return ("\n".join(",".join(row) for row in rows) + "\n").encode("utf-8")

        app = create_app(url, secure_cookies=False)
        with TestClient(app, base_url="https://testserver") as client:
            def login(account: str) -> None:
                username, password, _ = accounts[account]
                login_csrf = client.get("/api/auth/login-csrf")
                self.assertEqual(login_csrf.status_code, 200)
                response = client.post(
                    "/api/auth/login",
                    json={
                        "username": username,
                        "password": password,
                        "login_csrf": login_csrf.json()["login_csrf_token"],
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                client.headers["X-CSRF-Token"] = client.cookies.get(
                    "perovskite_csrf"
                )

            def logout() -> None:
                response = client.post("/api/auth/logout")
                self.assertEqual(response.status_code, 204, response.text)
                client.headers.pop("X-CSRF-Token", None)

            device_recipe, deposition_process = complete_guided_setup()
            for group in device_recipe["experimental_groups"]:
                if group["kind"] == "target":
                    group["adjustments"] = []
                    group["layers"] = deepcopy(device_recipe["layers"])
                    group["deposition_process"] = deepcopy(deposition_process)

            login("instructor")
            campaign = client.post(
                "/api/campaigns",
                json={
                    "code": f"pg3-lockorder-{suffix}",
                    "display_name": f"PostgreSQL lock-order campaign {suffix}",
                    "description": "Disposable upload/assignment lock-order campaign",
                },
            )
            self.assertEqual(campaign.status_code, 201, campaign.text)
            baseline = client.post(
                "/api/baselines",
                json={
                    "name": f"PostgreSQL lock-order baseline {suffix}",
                    "device_recipe": deepcopy(device_recipe),
                    "deposition_process": deepcopy(deposition_process),
                },
            )
            self.assertEqual(baseline.status_code, 201, baseline.text)
            logout()

            login("owner")
            created = client.post(
                "/api/experiments",
                json={
                    "recipe": {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    },
                    "campaign_id": f"pg3-lockorder-{suffix}",
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
            self.assertEqual(created.status_code, 201, created.text)
            experiment_id = int(created.json()["id"])
            submitted = client.patch(
                f"/api/experiments/{experiment_id}/plan-status",
                json={"status": "pending_approval"},
            )
            self.assertEqual(submitted.status_code, 204, submitted.text)
            logout()
            login("instructor")
            for status_name in ("approved", "released"):
                transition = client.patch(
                    f"/api/experiments/{experiment_id}/plan-status",
                    json={"status": status_name},
                )
                self.assertEqual(transition.status_code, 204, transition.text)
            logout()
            login("owner")
            batch = client.post(
                f"/api/experiments/{experiment_id}/fabrication-batches",
                json={"notes": "PostgreSQL lock-order batch"},
            )
            self.assertEqual(batch.status_code, 201, batch.text)
            batch_id = int(batch.json()["id"])
            for status_name in ("ready", "in_progress"):
                transition = client.patch(
                    f"/api/fabrication-batches/{batch_id}/status",
                    json={"status": status_name},
                )
                self.assertEqual(transition.status_code, 204, transition.text)
            for path, terminal in (
                ("solution-preparations", "discarded"),
                ("process-executions", "cancelled"),
            ):
                rows = client.get(f"/api/fabrication-batches/{batch_id}/{path}")
                self.assertEqual(rows.status_code, 200, rows.text)
                for row in rows.json():
                    transition = client.patch(
                        f"/api/fabrication-batches/{batch_id}/{path}/{row['id']}",
                        json={"status": terminal},
                    )
                    self.assertEqual(transition.status_code, 200, transition.text)
            conditions = client.get(
                f"/api/fabrication-batches/{batch_id}/conditions"
            ).json()
            actual_counts = {}
            shortfall_deviations = []
            for condition in conditions:
                actual_counts[str(condition["id"])] = 1
                shortfall_deviations.append({
                    "condition_id": condition["id"],
                    "description": "Lock-order setup: one substrate per condition was measured.",
                })
            completed = client.patch(
                f"/api/fabrication-batches/{batch_id}/status",
                json={
                    "status": "completed",
                    "actual_substrate_counts": actual_counts,
                    "shortfall_deviations": shortfall_deviations,
                },
            )
            self.assertEqual(completed.status_code, 204, completed.text)

            uploaded = client.post(
                f"/api/experiments/{experiment_id}/results",
                files={
                    "result_file": (
                        "lock-order-a.csv",
                        channel_csv(20.0),
                        "text/csv",
                    )
                },
                data={"fabrication_batch_id": str(batch_id)},
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            assigned_file_id = int(uploaded.json()["id"])
            detail = client.get(f"/api/results/{assigned_file_id}").json()
            groups = detail["groups"]
            condition_by_role = {
                group["kind"]: int(group["batch_condition_id"]) for group in groups
            }
            control_id = condition_by_role["control"]
            analysis = deepcopy(detail["analysis"])
            logout()

        owner_database = Database(url)
        try:
            async def fetch_owner_id() -> int:
                owner_username, _, _ = accounts["owner"]
                owner = await WebRepository(owner_database).get_user_by_username(
                    owner_username
                )
                assert owner is not None
                return owner.id

            owner_id = asyncio.run(fetch_owner_id())
        finally:
            asyncio.run(owner_database.dispose())

        async def run_race() -> list[Any]:
            from web.jv_parser import parse_jv_analysis

            second_content = channel_csv(22.0)
            databases = [Database(url), Database(url)]
            try:
                async def upload_second(database: Database) -> Any:
                    parsed = parse_jv_analysis(second_content)
                    return await WebRepository(database).add_result(
                        experiment_id,
                        fabrication_batch_id=batch_id,
                        filename="lock-order-b.csv",
                        content_type="text/csv",
                        content=second_content,
                        metrics={},
                        analysis=parsed,
                        actor_user_id=owner_id,
                    )

                async def assign_first(database: Database) -> Any:
                    return await WebRepository(
                        database
                    ).update_result_analysis_and_complete(
                        assigned_file_id,
                        analysis,
                        substrate_assignments={"A001": control_id},
                        group_assignment="lock-order race",
                        actor_user_id=owner_id,
                    )

                return await asyncio.gather(
                    upload_second(databases[0]),
                    assign_first(databases[1]),
                    return_exceptions=True,
                )
            finally:
                for database in databases:
                    await database.dispose()

        outcomes = asyncio.run(run_race())
        errors = [
            outcome for outcome in outcomes if isinstance(outcome, BaseException)
        ]
        self.assertEqual(
            errors, [], f"upload and assignment must both commit: {outcomes!r}"
        )

        verify_database = Database(url)
        try:
            async def verify() -> int:
                async with verify_database.engine.connect() as connection:
                    uploads = (
                        await connection.execute(
                            select(func.count())
                            .select_from(result_files)
                            .where(result_files.c.experiment_id == experiment_id)
                        )
                    ).scalar_one()
                return int(uploads)

            self.assertEqual(asyncio.run(verify()), 2)
        finally:
            asyncio.run(verify_database.dispose())

    def test_baseline_scope_promotion_and_membership_guard_use_postgresql(self) -> None:
        """Personal/Shared role isolation, promotion provenance, and the
        composite promoted-version membership foreign key on PostgreSQL."""

        async def exercise() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            repository = WebRepository(database)
            await seed_standard_layouts_async(database)
            suffix = uuid4().hex[:12]
            try:
                instructor = await repository.create_user(
                    username=f"pg-baseline-instructor-{suffix}",
                    display_name="PostgreSQL Baseline Instructor",
                    password_hash=hash_password(f"baseline integration secret {suffix}"),
                    role=UserRole.INSTRUCTOR,
                )
                owner = await repository.create_user(
                    username=f"pg-baseline-owner-{suffix}",
                    display_name="PostgreSQL Baseline Owner",
                    password_hash=hash_password(f"baseline owner secret {suffix}"),
                    role=UserRole.STUDENT,
                )
                peer = await repository.create_user(
                    username=f"pg-baseline-peer-{suffix}",
                    display_name="PostgreSQL Baseline Peer",
                    password_hash=hash_password(f"baseline peer secret {suffix}"),
                    role=UserRole.STUDENT,
                )
                await repository.create_campaign(
                    code=f"pg-baseline-{suffix}",
                    display_name="PostgreSQL baseline campaign",
                    description="Disposable integration-test campaign",
                    actor_user_id=instructor.id,
                )
                device_recipe, deposition_process = complete_guided_setup()
                personal = await repository.save_baseline(
                    f"PG personal {suffix}",
                    device_recipe,
                    deposition_process,
                    actor_user_id=owner.id,
                )
                # Student creation is Personal; the peer cannot see it.
                self.assertEqual(personal["scope"], "personal")
                self.assertEqual(personal["owner_user_id"], owner.id)
                peer_visible = await repository.list_baselines(
                    actor_user_id=peer.id
                )
                self.assertNotIn(
                    personal["id"], [row["id"] for row in peer_visible]
                )
                with self.assertRaises(KeyError):
                    await repository.get_baseline(
                        personal["id"], actor_user_id=peer.id
                    )
                # Instructors have oversight visibility but no source-use right.
                instructor_visible = await repository.list_baselines(
                    actor_user_id=instructor.id,
                    include_archived=True,
                )
                self.assertIn(
                    personal["id"], [row["id"] for row in instructor_visible]
                )
                guided_recipe = DepositionRecipe.from_mapping(
                    {
                        **deposition_recipe_from_process(deposition_process),
                        "device_recipe": device_recipe,
                    }
                )
                with self.assertRaises(KeyError):
                    await repository.add_experiment(
                        guided_recipe,
                        campaign_id=f"pg-baseline-{suffix}",
                        source_baseline_version_id=personal["current_version_id"],
                        actor_user_id=instructor.id,
                    )
                # Explicit promotion records provenance and the audit event.
                promoted = await repository.promote_baseline(
                    personal["id"],
                    promoted_by_user_id=instructor.id,
                    note="PostgreSQL promotion",
                )
                self.assertEqual(promoted["scope"], "shared")
                self.assertEqual(promoted["owner_user_id"], owner.id)
                self.assertEqual(
                    promoted["promoted_version_id"],
                    personal["current_version_id"],
                )
                async with database.engine.connect() as connection:
                    actions = [
                        str(row.action)
                        for row in await connection.execute(
                            select(audit_events.c.action).where(
                                audit_events.c.entity_type == "baseline",
                                audit_events.c.entity_id
                                == str(personal["id"]),
                            )
                        )
                    ]
                self.assertIn("baseline.promote", actions)
                # After promotion every student may use it as a source.
                shared_for_peer = await repository.get_baseline(
                    promoted["id"], actor_user_id=peer.id
                )
                self.assertEqual(shared_for_peer["scope"], "shared")
                peer_experiment = await repository.add_experiment(
                    guided_recipe,
                    campaign_id=f"pg-baseline-{suffix}",
                    source_baseline_version_id=promoted["current_version_id"],
                    actor_user_id=peer.id,
                )
                peer_conditions = await repository.list_conditions_for_experiment(
                    peer_experiment.id
                )
                peer_control = next(
                    condition
                    for condition in peer_conditions
                    if condition.role == ConditionRole.CONTROL
                )
                self.assertEqual(
                    peer_control.recipe_snapshot["device"]["layers"],
                    device_recipe["layers"],
                )
                # The former owner loses revision rights after promotion.
                with self.assertRaises(KeyError):
                    await repository.update_baseline(
                        personal["id"],
                        f"PG renamed {suffix}",
                        device_recipe,
                        deposition_process,
                        actor_user_id=owner.id,
                    )
                # Composite membership FK: a promoted_version_id must belong to
                # the same baseline.
                instructor_shared = await repository.save_baseline(
                    f"PG shared {suffix}",
                    device_recipe,
                    deposition_process,
                    actor_user_id=instructor.id,
                )
                self.assertEqual(instructor_shared["scope"], "shared")
                self.assertIsNone(instructor_shared["owner_user_id"])
                with self.assertRaises(IntegrityError):
                    async with database.engine.begin() as connection:
                        await connection.execute(
                            update(baselines)
                            .where(baselines.c.id == instructor_shared["id"])
                            .values(
                                promoted_version_id=promoted["current_version_id"]
                            )
                        )
                async with database.engine.begin() as connection:
                    await connection.execute(
                        update(baselines)
                        .where(baselines.c.id == instructor_shared["id"])
                        .values(
                            promoted_version_id=(
                                instructor_shared["current_version_id"]
                            )
                        )
                    )
            finally:
                await database.dispose()

        asyncio.run(exercise())

    def test_baseline_promoted_version_foreign_key_is_restrict(self) -> None:
        """The composite promotion-membership foreign key must be RESTRICT.

        With a composite foreign key, SET NULL would apply to both local
        columns - including the non-nullable primary key baselines.id - so the
        generated definition is verified directly through pg_constraint
        rather than only through a deletion attempt.
        """

        async def exercise() -> None:
            database = Database(os.environ["PEROVSKITE_TEST_POSTGRESQL_URL"])
            try:
                async with database.engine.connect() as connection:
                    definition = (
                        await connection.execute(
                            text(
                                "SELECT pg_get_constraintdef(oid) "
                                "FROM pg_constraint "
                                "WHERE conname = "
                                "'fk_baselines_promoted_version_belongs_to_baseline'"
                            )
                        )
                    ).scalar()
                self.assertIsNotNone(definition)
                self.assertIn(
                    "FOREIGN KEY (id, promoted_version_id) "
                    "REFERENCES baseline_versions(baseline_id, id)",
                    definition,
                )
                self.assertIn("ON DELETE RESTRICT", definition)
                self.assertNotIn("ON DELETE SET NULL", definition)
            finally:
                await database.dispose()

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
