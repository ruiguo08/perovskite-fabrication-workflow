# React Phase 3 Implementation Plan — Execution, Results, and Provenance

**Status:** Complete and accepted on August 14, 2026. Date: 2026-08-12. Companion document: `docs/react-phase-3-readiness-review.md`.
Legacy Jinja pages and their JavaScript remain untouched until Phase 4.

Ground rules: TDD for every backend contract (write the failing test first); vitest for React
components/pages; browser tests use the genuine CDP top-document driver in `tests/cdp_driver.py`
(see `tests/test_browser_run_sheet.py` and `tests/test_browser_results.py`); the legacy
inline-script harness in `tests/test_browser_builder.py` is a known CSP false positive, not
genuine coverage, and is deferred to Phase 4 for retirement; legacy Jinja pages and their JS
are **not modified** (removal is Phase 4); no schema/migration changes; every state-changing
React request goes through `apiFetch` (CSRF header automatic); no browser-level full-page reload.

Testing roles:
- **Checkpoint tests (3A, 3B, 3C):**
  - 3A: targeted Phase 3 API tests (`tests.test_phase3_api`), **mandatory PostgreSQL tests**
    (`tests.test_postgresql_integration` — new repository queries), and `corepack pnpm typecheck`.
  - 3B: affected Vitest/browser tests (frontend vitest suite, `tests.test_browser_run_sheet`)
    plus `corepack pnpm typecheck` and `corepack pnpm lint`.
  - 3C: affected Vitest/browser tests (frontend vitest suite, `tests.test_browser_results`)
    plus `corepack pnpm typecheck` and `corepack pnpm lint`.
  - The complete regression matrix runs only at 3D: complete SQLite suite
    (`python -m unittest discover -s tests -v`), PostgreSQL suite
    (`$env:PEROVSKITE_TEST_POSTGRESQL_URL='postgresql+asyncpg://…'; python -m unittest tests.test_postgresql_integration -v`
    or `Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`), Vite proxy smoke
    (`$env:PEROVSKITE_VITE_SMOKE='1'; python -m unittest tests.test_vite_proxy_smoke -v`),
    complete frontend suite and build (`corepack pnpm test`, `corepack pnpm lint`,
    `corepack pnpm typecheck`, `corepack pnpm build`), wheel inspection (`uv build` + contents
    check), and `git diff --check`.

## Phase 3A — Backend contracts and shared frontend types

- [x] **3A.1 Result detail + assignments JSON contracts** (`src/web/models.py`, `src/web/routes.py`, `src/web/repository.py`)
  - Files created: none. Files modified: `src/web/models.py`, `src/web/routes.py`, `src/web/repository.py`.
  - Interfaces consumed: `require_user` (router-level), `require_csrf`, `_get_record_or_404`, `_get_result_or_404`, `_student_owner_id`, `_batch_result_groups`, `repository.get_result`, `repository.list_result_device_assignments`, `repository.update_result_analysis_and_complete`, `assign_substrates_to_groups`, `run_in_threadpool`.
  - Interfaces produced: `GET /api/results/{file_id}` → `ResultDetailResponse` (result row incl. `created_by_id` + `analysis` + `groups` + `assignments`); `GET /api/results/{file_id}/assignments` → `list[ResultAssignmentRowResponse]`; `POST /api/results/{file_id}/assignments` (CSRF, body `{assignments: [{analysis_substrate_id, batch_condition_id}]}`) → 200 `ResultDetailResponse` / 400 / 404. Ownership gate: fetch result → `_get_record_or_404(result.experiment_id)` → 404 on cross-student access (finding I3).
  - **Repository change for provenance (finding I9):** add `result_files.c.created_by_id` to the selects of `get_result`, `list_results_for_experiment`, and `list_results_for_batch` ([repository.py:1531,1555,1578](src/web/repository.py#L1531)) so `_result_record` has one consistent row contract, and emit `"created_by_id": int(row["created_by_id"]) if row["created_by_id"] is not None else None` from `_result_record` ([repository.py:5317](src/web/repository.py#L5317)). `ResultDetailResponse.created_by_id` is `int | None` (Pydantic; nullable, FK users SET NULL); the summary response models do not expose the field.
  - **Assignment request validation (new):** reject duplicate `analysis_substrate_id` entries (400); require the submitted substrate ID set to exactly equal the `analysis.substrates` ID set — missing or extra → 400; preserve the server-side checks that every `batch_condition_id` belongs to the result's fabrication batch ([repository.py:1684-1694](src/web/repository.py#L1684)) and that every substrate is assigned ([jv_parser.py:216-217](src/web/jv_parser.py#L216)). Then convert to the legacy shape and reuse `assign_substrates_to_groups` + `update_result_analysis_and_complete` with the legacy `assignment_summary` string.
  - Tests to add (in `tests/test_phase3_api.py`, created here): 401 anonymous ×3; CSRF-missing 403 on POST; student gets own result, 404 on another student's result (both GET and POST); instructor/admin get any result; **`created_by_id` present and correct in `ResultDetailResponse`** (response-contract test); **regression: `GET /api/experiments/{id}` (`ExperimentDetailResponse.results`) still returns the results list with the extended row contract**; duplicate `analysis_substrate_id` → 400; missing substrate (set mismatch) → 400; extra substrate (set mismatch) → 400; `batch_condition_id` from another batch → 400; assignment success updates `statistics.groups`, assignment rows, `group_assignment` and returns a complete `ResultDetailResponse`; upload→assign→detail round trip; detail response embeds `analysis` + `groups` + `assignments`.
  - Commands: `.venv/Scripts/python.exe -m unittest tests.test_phase3_api -v`.
  - Acceptance: all new tests pass; no existing test changes; no React changes.
- [x] **3A.2 Global role-scoped list contracts** (`src/web/models.py`, `src/web/routes.py`, `src/web/repository.py`)
  - Files modified: `src/web/models.py`, `src/web/routes.py`, `src/web/repository.py`.
  - Interfaces consumed: `_student_owner_id` semantics; existing batch/result row accessors.
  - Interfaces produced: `GET /api/fabrication-batches` (filters `status`, `experiment_id`; `created_at DESC`; items = `FabricationBatchListItemResponse` incl. `experiment_code`); `GET /api/results` (filters `experiment_id`, `fabrication_batch_id`; items = `ResultListItemResponse` incl. `experiment_code`, `batch_code`). Students see own experiments only; instructor/admin see all. No pagination (documented decision, finding I4).
  - Tests to add (same file): student sees only own batches/results (create two students' data, assert filtering); `status`/`experiment_id` filters; instructor sees all; 404 when `experiment_id` filter is outside scope; anonymous 401.
  - Commands: `.venv/Scripts/python.exe -m unittest tests.test_phase3_api -v`.
  - Acceptance: all pass; responses are bare arrays; no legacy behavior changed.
- [x] **3A.3 Run-sheet aggregate contract** (`src/web/models.py`, `src/web/routes.py`, `src/web/repository.py`)
  - Files modified: the same three.
  - Interfaces consumed: `_batch_for_actor_or_404`; existing batch-scoped list methods (`get_fabrication_batch_conditions`, `get_fabrication_substrates_for_batch`, `get_fabrication_devices_for_batch`, `list_solution_preparations` + `list_solution_preparation_uses`, `list_process_executions` + `list_process_execution_members`, `list_deviations`); editor-config constants from `perovskite_bo`.
  - Interfaces produced: `GET /api/fabrication-batches/{batch_id}/run-sheet` → `RunSheetResponse` (findings I1/I2): batch + conditions + substrates + devices + preparations-with-uses + executions-with-members + deviations + `editor_config {vcd_valves, max_solid_chemicals, max_solvents}`.
  - Tests to add: shape test pinning every section and the uses/members/editor_config fields (finding I7 — pins the real shapes); cross-student 404; batch not found 404.
  - Commands: `.venv/Scripts/python.exe -m unittest tests.test_phase3_api -v`.
  - Acceptance: single GET returns the full run-sheet read model; shape pinned by tests.
- [x] **3A.4 Shared TypeScript contracts** (`frontend/src/types/api.ts`)
  - Files modified: `frontend/src/types/api.ts`.
  - Interfaces consumed: existing `FabricationBatchSummary`, `ResultSummary`, `Condition`, role union.
  - Interfaces produced: `BatchRunSheet`, `FrozenBatchCondition`, `FabricationSubstrate`, `FabricationDevice`, `SolutionPreparation` (+`SolutionPreparationUse`), `ProcessExecution` (+`ProcessExecutionMember`), `Deviation`, `EditorConfig`, `ResultDetail` (+`ResultGroup`, `ResultAssignment`, `created_by_id: number | null`), `FabricationBatchListItem`, `ResultListItem`, `AssignmentsPayload` (`{assignments: [{analysis_substrate_id: string, batch_condition_id: number}]}`). `device_active_area_cm2` typed `string` (M3).
  - Tests to add: none new (types are compile-time) — but `corepack pnpm typecheck` must pass.
  - Commands: `cd frontend && corepack pnpm typecheck`.
  - Acceptance: types mirror the 3A response models field-for-field; typecheck green.
- [x] **3A.5 PostgreSQL tests** (`tests/test_postgresql_integration.py`)
  - Files modified: `tests/test_postgresql_integration.py` (extend `_exercise_fabrication_batch`; add a results/global-list exercise).
  - Interfaces consumed: the new 3A endpoints through the HTTP harness.
  - Tests to add (mandatory at 3A — new repository queries): global batch/result lists role-scoped against PG (two students + instructor); run-sheet GET; result detail (incl. `created_by_id`); assignment POST persistence; **small valid CSV upload + binary-content round-trip** (LargeBinary through asyncpg). The 10 MiB size-boundary stays in targeted API/unit tests (3A.1/upload tests).
  - Commands (mandatory at 3A, repeated at 3D — PowerShell): `$env:PEROVSKITE_TEST_POSTGRESQL_URL='postgresql+asyncpg://…'; .venv\Scripts\python.exe -m unittest tests.test_postgresql_integration -v` or `powershell -File scripts/Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`.
  - Acceptance: PG suite green; no SQLite-only assumptions in the new queries.

**Checkpoint 3A — COMPLETE (accepted August 14, 2026).** Review: new API contracts (assignment validation rules, `created_by_id`), authorization tests, TS types, PG isolation. Do not start 3B until approved. GLM runs `tests.test_phase3_api`, the mandatory PostgreSQL tests, and `corepack pnpm typecheck`. The complete regression matrix runs only at 3D.

## Phase 3B — Fabrication batch lists and run sheet

- [x] **3B.1 Global batch list page** (`frontend/src/pages/FabricationBatchesPage.tsx`, new `FabricationBatchesPage.test.tsx`)
  - Files created: both files. Files modified: `frontend/src/App.tsx` (route `/fabrication-batches`), `frontend/src/components/AppShell.tsx` (enable "Fabrication batches" nav item, [AppShell.tsx:30](frontend/src/components/AppShell.tsx#L30)), `frontend/src/styles.css` (list styles; reuse `.batch-summary-card`, `.data-table`, `.status-badge`).
  - Interfaces consumed: `GET /api/fabrication-batches`; `useApiResource`; `StatusBadge`; `ErrorState`; `useSession` for role.
  - Interfaces produced: page with server-filtered list (status filter), batch cards linking to `/experiments/:id/batches/:batchId` (React `Link`), loading/error/empty states.
  - Tests to add: vitest page test (renders rows, status filter, empty state, error state); asserted against the 3A list contract.
  - Commands: `cd frontend && corepack pnpm test`, then `corepack pnpm typecheck`, then `corepack pnpm lint`.
  - Acceptance: list renders from the JSON API with no client-side aggregation; 320 px no horizontal overflow (reuse `.table-scroll`).
- [x] **3B.2 Snapshot editor component** (`frontend/src/components/SnapshotEditor.tsx`, new `SnapshotEditor.test.tsx`)
  - Files created: both. Files modified: none (consumed by 3B.3 — implemented and tested **before** the run-sheet page).
  - Interfaces consumed: snapshot JSON from the run-sheet API; `editor_config` bounds.
  - Interfaces produced: editable renderer for solution/process snapshots — field labels/units, numeric/integer inputs, array add/remove with `arrayRules` bounds, formulation-type swap, `sputter_mode`, valve select, VCD `vcd_step_sequence` reorder with add/remove sync; emits a full snapshot object (or `actual_matches_planned` semantics handled by its consumer).
  - Tests to add: vitest — array min/max enforcement, formulation swap, vcd sequence reorder/add/remove, numeric coercion (reuse the fixtures/patterns from `frontend/src/features/experiment-builder/` tests).
  - Commands: `cd frontend && corepack pnpm test`.
  - Acceptance: snapshot round-trips through validation-compatible JSON (assert against `tests/test_execution_snapshots.py` fixtures).
- [x] **3B.3 Run-sheet page** (`frontend/src/pages/BatchDetailPage.tsx`, new `BatchDetailPage.test.tsx`)
  - Files created: both. Files modified: `frontend/src/App.tsx` (route `/experiments/:experimentId/batches/:batchId`), `frontend/src/pages/ExperimentDetailPage.tsx` (batch card anchor → React `Link`, [ExperimentDetailPage.tsx:215](frontend/src/pages/ExperimentDetailPage.tsx#L215)), `frontend/src/styles.css`.
  - Interfaces consumed: `GET /api/fabrication-batches/{batch_id}/run-sheet`; batch mutation endpoints (`PATCH .../status`, `PATCH .../solution-preparations/{id}`, `PATCH .../process-executions/{id}`, `POST .../split`, `POST .../merge`, `POST .../deviations`); `SnapshotEditor` (3B.2); export anchors `…/export.json|pdf` (keep as plain anchors); `apiFetch` (CSRF automatic).
  - Interfaces produced: header (code, status badge, timestamps, exports, back link); status card with role-gated buttons (cancel hidden for students — presentational only); frozen conditions table; substrates & devices table; preparations card (status select per server transition table, three-way recording choice, snapshot editor, split disclosure, merge controls); executions card (equipment identifier, recording choice, split, merge); deviations table + form (category/severity/required description/optional JSON textareas, direct payload fields); conditional empty states.
  - **Mutation synchronization (finding I8):** PATCH preparation/execution updates the local row from the returned record; PATCH batch status (204) **refetches the run-sheet**; split/merge (topology and membership changes) **refetch the run-sheet**; deviation POST appends the returned record. No browser-level full-page reload.
  - Tests to add: vitest — status button set per (status, role); preparation payload mapping (`actual_matches_planned` vs `actual_solution_snapshot`); split payload `{member_ids}`; deviation payload field encoding; merge payload `{source_id}`; refetch triggered for status/split/merge; error surfaces from `detail`.
  - Commands: `cd frontend && corepack pnpm test`, then `corepack pnpm typecheck`, then `corepack pnpm lint`.
  - Acceptance: all run-sheet behaviors ported per the readiness-review section-5 inventory; sync strategy per above.
- [x] **3B.4 Browser tests for lists and run sheet** (new `tests/test_browser_run_sheet.py`)
  - Files created: `tests/test_browser_run_sheet.py`. Files modified: none.
  - Interfaces consumed: the genuine CDP top-document driver in `tests/cdp_driver.py` (forced 320px viewport, real mouse/keyboard input, `Runtime.evaluate` waits, network/console error tracking); fixtures: released experiment with conditions (reuse `test_fabrication_batches.py` helper logic).
  - Tests to add: login → `/app/fabrication-batches` lists the batch and links to the run sheet; run sheet at 320×900 has no horizontal overflow; record a preparation actual (`entered`), assert the row updates; split a preparation into two; record a deviation; transition `draft→ready`; student sees no cancel button; accessing another student's run-sheet URL shows the 404 state.
  - Commands: `.venv/Scripts/python.exe -m unittest tests.test_browser_run_sheet -v` (requires Chrome; skipped otherwise, matching existing gating).
  - Acceptance: browser suite green; legacy `BatchDashboardBrowserTests` still green (unchanged).
- [x] **3B.5 Merge UI (first UI for merge)** — inside 3B.3's page: for each planned preparation/execution with a merge-compatible sibling (identical `planned_canonical_hash` + `planned_snapshot_schema_version`), show a "Merge into" control posting `{source_id}`; surface 400 `detail` (hash mismatch) inline; after merge, refetch the run-sheet. Vitest covers the payload; browser test covers one merge.

**Checkpoint 3B — COMPLETE (accepted August 14, 2026).** Review: run-sheet fidelity against the readiness-review section-5 inventory, split/merge/deviation behavior, mutation synchronization, 320 px, authorization UX. GLM runs the affected Vitest/browser tests plus `corepack pnpm typecheck` and `corepack pnpm lint`. The complete regression matrix runs only at 3D.

## Phase 3C — Result upload and analysis

- [x] **3C.1 Global results list page** (`frontend/src/pages/ResultsPage.tsx`, new `ResultsPage.test.tsx`)
  - Files created: both. Files modified: `frontend/src/App.tsx` (route `/results`), `frontend/src/components/AppShell.tsx` (enable "Results" nav, [AppShell.tsx:31](frontend/src/components/AppShell.tsx#L31)), `frontend/src/styles.css`.
  - Interfaces consumed: `GET /api/results`; `useApiResource`; `StatusBadge`/`.result-summary-card`.
  - Interfaces produced: server-filtered list (experiment/batch filters), rows linking to `/app/results/:resultId`, integrity metadata (sha256 preview, size), metrics summary.
  - Tests: vitest page test (rows, filters, empty/error states).
  - Commands: `cd frontend && corepack pnpm test`, then `corepack pnpm typecheck`, then `corepack pnpm lint`.
  - Acceptance: list renders from the JSON API only.
- [x] **3C.2 Upload page** (`frontend/src/pages/UploadResultPage.tsx`, new `UploadResultPage.test.tsx`)
  - Files created: both. Files modified: `frontend/src/App.tsx` (route `/experiments/:experimentId/upload`), `frontend/src/pages/ExperimentDetailPage.tsx` (upload anchor → React `Link`, [ExperimentDetailPage.tsx:227](frontend/src/pages/ExperimentDetailPage.tsx#L227)).
  - Interfaces consumed: `GET /api/experiments/{id}` (eligible batches = `fabrication_batches` with status in_progress/completed, plus `experiment.recipe.experimental_groups` for the badge strip); `POST /api/experiments/{id}/results` via `apiFetch` with `FormData` (multipart + CSRF header automatic, [api.ts:88-90](frontend/src/lib/api.ts#L88)).
  - Interfaces produced: batch select (eligibility rule ported from [routes.py:503-509](src/web/routes.py#L503)), file input `accept=".csv,text/csv"`, client 10 MB guard (server remains authoritative), expected-groups badge strip, inline `detail` error display, navigate to `/app/results/{id}` on success.
  - Tests: vitest — eligibility filtering, FormData construction, error rendering, 10 MB guard.
  - Commands: `cd frontend && corepack pnpm test`.
  - Acceptance: upload works end-to-end against the existing JSON API; bounds and CSRF preserved.
- [x] **3C.3 JV curves and box plots** (`frontend/src/components/JvChart.tsx`, `frontend/src/components/BoxPlotChart.tsx`, both with `.test.tsx`)
  - Files created: four. Files modified: none (consumed by 3C.4 — implemented and tested **before** the result detail page).
  - Interfaces consumed: `analysis.devices[].traces`, `analysis.statistics` (server-computed; **no client-side statistics**).
  - Interfaces produced: SVG JV curves with the legacy rendering rules (polarity normalization, forward/reverse line styles `#D97706`/`#0891B2`, 5 gridlines, sample dots, `<title>` tooltips, per-device metrics table) and plot controls (select-all, toggle-all indeterminate, select best per group, cap 12, clear); SVG box plots per metric (whisker/box/median/mean/jitter, group palette, `n=` labels). No chart library (CSP `script-src 'self'`); `role="img"` + `aria-label` per legacy.
  - Tests: vitest — render from a fixture analysis (build fixtures from `tests/test_jv_parser.py` sample data), polarity normalization output, best-per-group selection, 12-device cap.
  - Commands: `cd frontend && corepack pnpm test`.
  - Acceptance: charts match legacy rendering on the same fixture data.
- [x] **3C.4 Result detail + assignment workflow** (`frontend/src/pages/ResultDetailPage.tsx`, new `ResultDetailPage.test.tsx`)
  - Files created: both. Files modified: `frontend/src/App.tsx` (route `/results/:resultId`), `frontend/src/styles.css`.
  - Interfaces consumed: `GET /api/results/{file_id}`; `GET /api/results/{file_id}/assignments`; `POST /api/results/{file_id}/assignments`; `JvChart`/`BoxPlotChart` (3C.3); the `experiment_id` from the detail response for the back link.
  - Interfaces produced: header (filename, batch link, sha256/size/`created_by_id` — integrity and provenance metadata); assignment form (**canonical substrate list = `analysis.substrates`**; one group select per substrate, pre-selected from `analysis.substrates[].batch_condition_id`; **`result_device_assignments` rows are provenance/detail display only** — if the per-device rows disagree with the substrate-level condition (or with each other), render an explicit inconsistency notice instead of silently selecting a value); submit disabled until all substrates are assigned (server remains authoritative); after POST, **replace local state with the returned complete `ResultDetailResponse`**; sections gated on `analysis.statistics.groups` presence (legacy `assignments_complete` parity, [result_analysis.html:23](src/web/templates/result_analysis.html#L23)); parsed-devices table with valid/invalid trace badges and metrics; per-metric statistics tables (mean±SD, median [Q1,Q3]); comparisons table with p-values and `title={test_method}`; plot controls wired to the chart components.
  - Tests: vitest — assignment payload from the select values, preselection from `analysis.substrates`, gating on `statistics.groups`, inconsistency detection rendering, local-state replacement with the POST response, error display, 404 state.
  - Commands: `cd frontend && corepack pnpm test`.
  - Acceptance: full assign→statistics flow client-driven; experiment auto-completion reflected on next detail fetch.
- [x] **3C.5 Browser tests for results** (new `tests/test_browser_results.py`)
  - Files created: `tests/test_browser_results.py`. Files modified: none.
  - Interfaces consumed: the genuine CDP top-document driver in `tests/cdp_driver.py` (forced 320px viewport, real mouse/keyboard input, `DOM.setFileInputFiles` for genuine file selection, `Runtime.evaluate` waits, network/console error tracking); fixture: released experiment + in_progress batch + a small CSV fixture (reuse `tests/test_jv_parser.py` sample content).
  - Tests to add: upload via `/app/experiments/{id}/upload` → lands on `/app/results/{resultId}`; assignment form submits and statistics sections appear; JV chart grid renders for ≤12 selected devices; 320×900 no horizontal overflow; student 404 on another student's result URL.
  - Commands: `.venv/Scripts/python.exe -m unittest tests.test_browser_results -v`.
  - Acceptance: browser suite green; legacy upload/analysis pages untouched.
- [x] **3C.6 Result list/detail links from experiment detail** — Results panel rows in `ExperimentDetailPage.tsx` link to `/results/:resultId` (React `Link`), keeping the sha256/metrics display.

**Checkpoint 3C — COMPLETE (accepted August 14, 2026).** Review: upload bounds, assignment workflow (preselection + inconsistency detection), chart fidelity, integrity/provenance metadata, 320 px. GLM runs the affected Vitest/browser tests plus `corepack pnpm typecheck` and `corepack pnpm lint`. The complete regression matrix runs only at 3D.

## Phase 3D — Acceptance and documentation

- [x] **3D.1 Full frontend suite**: `cd frontend && corepack pnpm test && corepack pnpm lint && corepack pnpm typecheck && corepack pnpm build` — build must emit `src/web/static-app/` with hashed assets.
- [x] **3D.2 Complete SQLite suite**: `.venv/Scripts/python.exe -m unittest discover -s tests -v` — all green, including untouched legacy tests.
- [x] **3D.3 Vite proxy smoke**: `$env:PEROVSKITE_VITE_SMOKE='1'; .venv\Scripts\python.exe -m unittest tests.test_vite_proxy_smoke -v`.
- [x] **3D.4 PostgreSQL suite**: `$env:PEROVSKITE_TEST_POSTGRESQL_URL='postgresql+asyncpg://…'; .venv\Scripts\python.exe -m unittest tests.test_postgresql_integration -v` (or `powershell -File scripts/Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`).
- [x] **3D.5 Wheel build + inspection**: `uv build`; verify `dist/*.whl` contains `web/static-app/index.html`, the hashed `assets/*`, and `web/services/material_catalog_seed.json` (`python -m zipfile -l dist/*.whl`).
- [x] **3D.6 `git diff --check`** — no whitespace errors.
- [x] **3D.7 Documentation**: update `docs/react-migration.md` (Phase 3 status, route table, mark the **five required API gaps plus one additional run-sheet aggregate contract** delivered), `DEPLOYMENT.md`, `LOCAL_DEVELOPMENT_WINDOWS.md`, `ARCHITECTURE.md`, `README.md` as needed; record checkpoint completion in this plan document.
- [x] **3D.8 Legacy preservation check**: The workspace was already dirty before Phase 3 began (pre-existing modifications and untracked migrations from earlier project work), so `git status` alone cannot prove that Phase 3 left legacy paths untouched. Scope attribution is based on the recorded per-checkpoint change reports and external review, not a clean working tree. Phase 3 did not intentionally modify database schema/migrations, Jinja templates, or legacy JavaScript; the existing changes in those paths predate Phase 3 and were preserved. Legacy pages remain reachable (`/login`, `/experiments`, and export routes return their legacy responses, confirmed by the installed-wheel route smoke in 3D.5) and the complete regression suite passed.
- [x] **3D.9 Phase 3 sign-off**: reviewer confirms the readiness-review corrected items are all closed; Phase 4 (cutover + legacy removal) remains out of scope.

**Checkpoint 3D — COMPLETE (Phase 3 sign-off, August 14, 2026).** No Phase 4 work (default-route cutover, Jinja removal) is started here.

### Phase 3D acceptance evidence

- Frontend: 163/163 Vitest tests pass with clean stderr; typecheck and lint pass;
  production build emits `src/web/static-app/index.html` plus hashed assets
  `index-W2AYGwrX.js` (430.96 kB, gzip 119.11 kB) and `index-C7odFSax.css`
  (30.90 kB, gzip 6.14 kB).
- SQLite regression: 341 tests, 11 skipped (all environment-gated), exit 0.
- Vite proxy smoke: 4 tests, exit 0.
- PostgreSQL integration: 7 tests, exit 0 (role isolation, global lists,
  run sheet, result detail, assignment persistence, repository transactions,
  catalog integrity, restricted runtime role).
- Wheel: `perovskite_deposition_bo-0.3.0-py3-none-any.whl` contains
  `web/static-app/index.html`, the hashed JS/CSS assets, and
  `web/services/material_catalog_seed.json`. Installed into a fresh temporary
  virtual environment: the application imports, `/app/` serves the React entry,
  deep `/app/...` routes return the SPA entry, hashed assets load, and
  `/api`, `/static`, `/healthz`, exports, and legacy routes are not shadowed.

## Known technical debt (recorded at the Phase 3B gate)

[tests/test_browser_builder.py:661-808](tests/test_browser_builder.py#L661) ``BatchDashboardBrowserTests``
uses an inline ``<script>`` harness that the production CSP blocks (``script-src 'self'`` with no
``'unsafe-inline'``, [src/web/middleware.py:74](src/web/middleware.py#L74)) and asserts marker strings
("BATCH_BROWSER_OK", "Chrome-recorded batch deviation") that also appear verbatim in the dumped
harness source, so the assertions pass without any harness JavaScript executing. It is a
CSP/source-marker false positive, not genuine browser coverage. The Phase 3B run-sheet coverage has
been moved to the genuine CDP-driven suite ([tests/cdp_driver.py](tests/cdp_driver.py),
[tests/test_browser_run_sheet.py](tests/test_browser_run_sheet.py)); the legacy harness should be
retired or reworked during Phase 4.