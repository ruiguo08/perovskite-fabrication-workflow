"""Local preview server for the schema-v7 result UI (not committed).

Starts the app on http://127.0.0.1:8300 with an isolated SQLite database
and seeds the two real instrument exports from docs/test-data:

- 20260906.csv (conditions Control / T1 / T2 / T3, 16 substrates, 94 devices)
- 20260916.csv (conditions Control1 / Control2 / T1 / T2 / T3, 20 substrates, 120 devices)

The instrument naming (`{condition}-{substrate}-{device}.CH_Ref.Forward(n)`,
often wrapped in a date prefix) does not carry laser marks, so the preview
maps labels onto synthetic substrate marks: Control->C0xxx, Control1->C1xxx,
Control2->C2xxx, T1->T1xxx, T2->T2xxx, T3->T3xxx (xxx = substrate number),
and the trailing device number becomes `Channel N`. Everything else in the
CSV is untouched; metrics come verbatim from the instrument summary table.

Login: demo / preview-pass-123.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from web.app import create_app  # noqa: E402
from web.repository import (  # noqa: E402
    BatchStatus,
    ExecutionStatus,
    PreparationStatus,
    UserRole,
)

DB_PATH = ROOT / "demo-preview.sqlite3"
PORT = 8300
USERNAME = "demo"
PASSWORD = "preview-pass-123"

STEM_RE = re.compile(
    r"(?:[^,()]*\(\s*)?(Control\d*|T\d+)-(\d+)-(\d+)\.CH_Ref\.(Forward|Reverse)(\(\d+\))?\s*\)?"
)
MARK_PREFIX = {
    "Control": "C0",
    "Control1": "C1",
    "Control2": "C2",
    "T1": "T1",
    "T2": "T2",
    "T3": "T3",
}


def transform_labels(text: str) -> str:
    """Rewrite instrument stems into `{mark} Channel {n}.{Direction}(k)` form."""

    def repl(match: re.Match) -> str:
        condition = match.group(1)
        substrate = int(match.group(2))
        device = int(match.group(3))
        direction = match.group(4)
        repeat = match.group(5) or ""
        mark = f"{MARK_PREFIX[condition]}{substrate:03d}"
        return f"{mark} Channel {device}.{direction}{repeat}"

    return STEM_RE.sub(repl, text)


async def seed(app) -> dict[str, list[int]]:
    repository = app.state.repository
    from tests.layout_fixtures import seed_standard_layouts_async
    from tests.test_fabrication_batches import (
        _create_released_experiment_with_conditions,
    )

    await seed_standard_layouts_async(app.state.database)

    from web.jv_parser import _flat_metrics_from_analysis, parse_jv_analysis
    from web.operations.result_assignment import (
        ResultAssignmentInput,
        save_result_analysis,
    )

    files: dict[str, dict] = {
        "20260906.csv": {"control_marks": 4, "target_marks": 12},
        "20260916.csv": {"control_marks": 8, "target_marks": 12},
    }
    result_ids: dict[str, list[int]] = {}
    for filename, counts in files.items():
        raw = (ROOT / "docs/test-data" / filename).read_bytes().decode("gb18030")
        converted = transform_labels(raw)

        experiment_id = await _create_released_experiment_with_conditions(
            repository,
            f"demo-{Path(filename).stem}",
            layout_code="25x25_six_010",
            substrate_count=12,
        )
        batch = await repository.create_fabrication_batch(
            experiment_id, actor_user_id=1
        )
        for preparation in await repository.list_solution_preparations(batch.id):
            await repository.update_solution_preparation(
                preparation.id,
                status=PreparationStatus.DISCARDED,
                fabrication_batch_id=batch.id,
                actor_user_id=1,
            )
        for execution in await repository.list_process_executions(batch.id):
            await repository.update_process_execution(
                execution.id,
                status=ExecutionStatus.CANCELLED,
                fabrication_batch_id=batch.id,
                actor_user_id=1,
            )
        conditions = await repository.get_fabrication_batch_conditions(batch.id)
        control_id = next(c.id for c in conditions if c.role == "control")
        target_id = next(c.id for c in conditions if c.role == "target")
        await repository.update_fabrication_batch_status(
            batch.id, BatchStatus.READY, actor_user_id=1
        )
        await repository.update_fabrication_batch_status(
            batch.id, BatchStatus.IN_PROGRESS, actor_user_id=1
        )
        actual_counts = {
            control_id: counts["control_marks"],
            target_id: counts["target_marks"],
        }
        await repository.update_fabrication_batch_status(
            batch.id,
            BatchStatus.COMPLETED,
            actual_substrate_counts=actual_counts,
            # A shortfall explanation is required exactly when fewer
            # substrates were measured than planned; an equal count with
            # an explanation is rejected.
            shortfall_deviations=[
                (c.id, "Demo setup: real instrument export.")
                for c in conditions
                if actual_counts[c.id] < 12
            ],
            actor_user_id=1,
        )

        analysis = parse_jv_analysis(converted.encode("utf-8"))
        result = await repository.add_result(
            experiment_id,
            fabrication_batch_id=batch.id,
            filename=filename,
            content_type="text/csv",
            content=converted.encode("utf-8"),
            metrics=_flat_metrics_from_analysis(analysis),
            analysis=analysis,
            actor_user_id=1,
        )
        file_id = int(result["id"])
        substrate_rows = []
        for substrate in analysis["substrates"]:
            mark = str(substrate["substrate_id"])
            condition_id = target_id if mark.startswith("T") else control_id
            substrate_rows.append(
                ResultAssignmentInput(
                    analysis_substrate_id=mark,
                    batch_condition_id=condition_id,
                )
            )
        await save_result_analysis(
            repository,
            file_id=file_id,
            assignments=substrate_rows,
            exclusions=[],
            group_assignment=None,
            actor_user_id=1,
            actor_role=UserRole.ADMINISTRATOR,
        )
        result_ids[filename] = [file_id]
        print(f"seeded {filename}: experiment {experiment_id}, result {file_id}, "
              f"{len(analysis['devices'])} devices")
    return result_ids


def main() -> None:
    DB_PATH.unlink(missing_ok=True)
    app = create_app(
        DB_PATH,
        secure_cookies=False,
        _test_user=(USERNAME, PASSWORD, UserRole.ADMINISTRATOR),
    )

    async def prepare() -> dict[str, list[int]]:
        from web.auth import hash_password, normalize_username

        await app.state.database.initialize()
        await app.state.repository.create_user(
            username=normalize_username(USERNAME),
            display_name="Demo User",
            password_hash=hash_password(PASSWORD, username=normalize_username(USERNAME)),
            role=UserRole.ADMINISTRATOR,
        )
        return await seed(app)

    seeded = asyncio.run(prepare())

    print()
    print(f"preview ready: http://127.0.0.1:{PORT}/app/")
    print(f"login: {USERNAME} / {PASSWORD}")
    for filename, file_ids in seeded.items():
        for file_id in file_ids:
            print(f"{filename}: http://127.0.0.1:{PORT}/app/results/{file_id}")
    print()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
