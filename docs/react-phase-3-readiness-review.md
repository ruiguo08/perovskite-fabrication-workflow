# React Phase 3 Readiness Review — Execution, Results, and Provenance

**Status:** Resolved — Phase 3 accepted August 14, 2026. Review date: 2026-08-12. No implementation code,
schema, migration, configuration, or tests were changed during this review (read-only exploration). The
findings below are the original pre-implementation review context; each is marked RESOLVED with the phase
that delivered the correction.

## 1. Executive assessment

**Classification: READY — Phase 3 accepted August 14, 2026.**

All Critical and Important findings (C1–C4, I1–I8) were resolved during
implementation. The five required API gaps plus one additional run-sheet
aggregate contract were delivered in Phase 3A; the React run-sheet, upload, and
analysis pages were delivered in Phase 3B/3C; the Phase 3D acceptance matrix
(full frontend, SQLite, Vite-smoke, PostgreSQL, wheel + installed-package smoke)
passed with exit 0 on every command. See
[docs/superpowers/plans/2026-08-12-react-phase-3.md](docs/superpowers/plans/2026-08-12-react-phase-3.md)
for the acceptance evidence.

The backend execution/provenance domain model is complete, and **no blocking data-integrity
defects were found in the reviewed paths**: every fabrication-batch API (create, status,
conditions, substrates, devices, preparations, executions, splits, merges, deviations) exists
with correct ownership checks, the 404-not-found convention, CSRF on every mutation, and
frozen-snapshot integrity as covered by `tests/test_fabrication_batches.py` and
`tests/test_execution_snapshots.py`.

The only blocker identified at review time was the **Phase 3 API surface** (5 endpoints, all
previously scoped in `docs/react-migration.md` as Phase 3 deliverables and confirmed absent at
review time): global role-scoped `GET /api/fabrication-batches` and `GET /api/results`, plus
`GET /api/results/{file_id}`, `GET /api/results/{file_id}/assignments`, and a JSON
`POST /api/results/{file_id}/assignments`. At review time, result analysis and assignment data
existed only in Jinja template context or inside the batch `export.json` attachment, and the
React run sheet needed an aggregated run-sheet JSON (uses/members existed only per-entity)
plus editor-config constants injected only into Jinja. **All of these contracts were delivered
in Phase 3A**, and the React pages consuming them were delivered in Phase 3B/3C. The findings
below are preserved as historical review context; their "blocks" and "does not exist" wording
described the pre-implementation state and is now resolved.

None of the corrections required a schema or migration change. The recommended order was exactly
the 3A → 3B → 3C → 3D structure: add the missing contracts first, then build the React pages
against them.

## 2. Findings

### Critical (all resolved in Phase 3A)

**C1. (RESOLVED in Phase 3A) `GET /api/results/{file_id}` did not exist — result analysis data was Jinja-only.**
- Reference: [src/web/routes.py:569-595](src/web/routes.py#L569) (HTML `result_analysis_page`, the only result-detail route); `ResultSummaryResponse` at [src/web/models.py:226](src/web/models.py#L226) omits `analysis`; the full `analysis` dict is stored in `result_files.analysis` ([src/web/database.py:501](src/web/database.py#L501)) and served only via `| tojson` template context ([src/web/routes.py:593](src/web/routes.py#L593)).
- Existing behavior: the analysis page renders `{experiment, result, groups, analysis}` where `groups` comes from `_batch_result_groups` ([src/web/routes.py:3002](src/web/routes.py#L3002)) and `analysis` is the stored JV parse.
- Why it matters: the React `/app/results/:resultId` page cannot render assignments, JV curves, metrics, or statistics without this JSON.
- Correction: add `GET /api/results/{file_id}` returning a `ResultDetailResponse` that embeds the full result row (including `created_by_id` for provenance, which requires a repository change — see I9), `analysis`, `groups` (frozen batch conditions as assignment targets), and assignment rows.
- Blocks: yes (3C).

**C2. (RESOLVED in Phase 3A) No JSON assignment read/write endpoints existed.**
- Reference: `GET /api/results/{file_id}/assignments` — assignment rows exist in `result_device_assignments` ([src/web/database.py:699](src/web/database.py#L699)) readable via `repository.list_result_device_assignments` ([src/web/repository.py:1601](src/web/repository.py#L1601)) but that method is called only by the batch export builder ([src/web/routes.py:2628-2632](src/web/routes.py#L2628)); `POST /api/results/{file_id}/assignments` exists only as an HTML form route ([src/web/routes.py:597-665](src/web/routes.py#L597)) reading `group_{index}` form fields and returning a 303 redirect.
- Existing behavior: assignments are validated by `assign_substrates_to_groups` (every substrate must map to a known group, [src/web/jv_parser.py:199-223](src/web/jv_parser.py#L199)) and persisted by `update_result_analysis_and_complete` ([src/web/repository.py:1646](src/web/repository.py#L1646)), which also auto-completes the experiment.
- Why it matters: React needs a JSON variant that returns the updated analysis (not a redirect) and a GET to render current assignment state.
- Correction: add `GET /api/results/{file_id}/assignments` (rows) and `POST /api/results/{file_id}/assignments` (CSRF; contract in section 4; 200 with updated `ResultDetailResponse`; 400 on validation errors; reuse `assign_substrates_to_groups` + `update_result_analysis_and_complete`).
- Blocks: yes (3C).

**C3. (RESOLVED in Phase 3A) No global `GET /api/fabrication-batches` list existed.**
- Reference: only `GET /api/experiments/{experiment_id}/fabrication-batches` exists ([src/web/routes.py:1861](src/web/routes.py#L1861)); no `list_all_fabrication_batches` repository method; the nav item is disabled in React ([frontend/src/components/AppShell.tsx:30](frontend/src/components/AppShell.tsx#L30)).
- Why it matters: `/app/fabrication-batches` requires a server-role-scoped global list; client-side aggregation across experiments is prohibited by the migration plan.
- Correction: add `GET /api/fabrication-batches` filtered server-side by role (students: own experiments only via `_student_owner_id` semantics), optional `status` and `experiment_id` query filters, `created_at DESC` ordering, no pagination (consistent with every existing list endpoint); each item = `FabricationBatchResponse` + `experiment_code`.
- Blocks: yes (3B).

**C4. (RESOLVED in Phase 3A) No global `GET /api/results` list existed.**
- Reference: results appear only as summaries inside `ExperimentDetailResponse.results` ([src/web/models.py:553-560](src/web/models.py#L553)) or inside the batch export payload; repository has `list_results_for_experiment`/`list_results_for_batch` ([src/web/repository.py:1555,1578](src/web/repository.py#L1555)) with no top-level route.
- Correction: add `GET /api/results` with the same role-scoping/filter policy as C3 (`experiment_id`, `fabrication_batch_id` filters); items = `ResultSummaryResponse` + `experiment_code` + `batch_code`.
- Blocks: yes (3C).

### Important

**I1. (RESOLVED in Phase 3A) No aggregated run-sheet JSON; uses/members were per-entity only.**
- Reference: `preparation_uses` and `execution_members` are attached only to the Jinja context ([src/web/routes.py:2498-2514](src/web/routes.py#L2498)); JSON exists only as `GET /api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}/uses` ([src/web/routes.py:2058](src/web/routes.py#L2058)) and `.../process-executions/{execution_id}/members` ([src/web/routes.py:2253](src/web/routes.py#L2253)) — N+M calls, and the split UI needs every membership.
- Correction: add `GET /api/fabrication-batches/{batch_id}/run-sheet` returning batch + conditions + substrates + devices + preparations (with uses) + executions (with members) + deviations + editor_config in one ownership-guarded response. This mirrors the legacy page context exactly and is the single read model for the React run sheet.
- Blocks: no (composition is possible but chatty; the aggregate endpoint is the recommended contract and is scheduled in 3A).

**I2. (RESOLVED in Phase 3A) Editor-config constants were Jinja-only.**
- Reference: `batch_editor_config` (`vcd_valves`, `max_solid_chemicals`, `max_solvents`) injected at [src/web/routes.py:2509-2513](src/web/routes.py#L2509) into `#batch-editor-config` ([src/web/templates/batch.html:392](src/web/templates/batch.html#L392)); consumed by the snapshot editor ([src/web/static/batch-dashboard.js:10-87](src/web/static/batch-dashboard.js#L10)).
- Correction: include `editor_config` in the run-sheet response (I1). No separate `/api/config` endpoint.
- Blocks: no (hardcoding the three constants would work but violates "no lab data hardcoded in React" and drifts from the server).

**I3. (RESOLVED in Phase 3A) Ownership hazard in the new un-nested result routes.**
- Reference: `_get_result_or_404` ([src/web/routes.py:3015-3026](src/web/routes.py#L3015)) checks only `result["experiment_id"] == experiment_id`; ownership comes from the preceding `_get_record_or_404` call in every existing result route. The new `GET/POST /api/results/{file_id}` routes have no enclosing experiment path.
- Correction: fetch the result first, then `await _get_record_or_404(repository, result["experiment_id"], auth_context)`; a student accessing another student's result must get 404. Add an explicit cross-student 404 test.
- Blocks: no (implementation discipline; must be in the 3A test list).

**I4. (RESOLVED — decision: no pagination for Phase 3) No pagination abstraction; global lists use bare arrays with server-side filtering.**
- Reference: `useApiResource` + bare-array responses ([frontend/src/lib/useApiResource.ts](frontend/src/lib/useApiResource.ts)); `types/api.ts` has no `Paginated<T>`.
- Correction (decision): **no pagination** for Phase 3 global lists — server-side role filtering plus optional query filters, fixed `created_at DESC` ordering, bare JSON arrays; consistent with every existing list endpoint and with the lab's data volumes. `ponytail: add limit/offset only if a measured volume demands it.` Document this decision in the API contracts.
- Blocks: no.

**I5. (RESOLVED in Phase 3B/3C) Phase 2 React wiring left users on the legacy pages for batches/results.**
- Reference: batch cards link to the legacy dashboard via plain `<a href>` ([frontend/src/pages/ExperimentDetailPage.tsx:215](frontend/src/pages/ExperimentDetailPage.tsx#L215)); the upload anchor targets legacy `/experiments/{id}/upload` ([ExperimentDetailPage.tsx:227](frontend/src/pages/ExperimentDetailPage.tsx#L227)); AppShell disables "Fabrication batches" and "Results" ([AppShell.tsx:30-31](frontend/src/components/AppShell.tsx#L30-L31)); no React routes exist beyond Phase 2 ([frontend/src/App.tsx](frontend/src/App.tsx)).
- Correction: 3B/3C add the routes, enable the nav items, and switch the ExperimentDetailPage anchors to React `<Link>`s.
- Blocks: no (scheduled work, not a defect).

**I6. (RESOLVED in Phase 3B/3C) The only batch/result browser coverage exercised the legacy JS; genuine CDP coverage was added.**
- Reference: `BatchDashboardBrowserTests` ([tests/test_browser_builder.py:661-808](tests/test_browser_builder.py#L661)) drives `batch-dashboard.js` via an inline-script harness blocked by the production CSP — a source-marker false positive, not genuine coverage.
- Correction (delivered): `tests/test_browser_run_sheet.py` and `tests/test_browser_results.py` use the genuine CDP top-document driver in `tests/cdp_driver.py` (forced 320px viewport, real mouse/keyboard input, error tracking) to drive the production React bundle. The legacy `BatchDashboardBrowserTests` false positive is retained as technical debt deferred to Phase 4 (CSP is not weakened).
- Blocks: no.

**I7. (RESOLVED in Phase 3A) Uses/members route signatures declared a response model but returned raw dict lists.**
- Reference: `response_model=list[SolutionPreparationUseResponse]` / `list[ProcessExecutionMemberResponse]` at [src/web/routes.py:2060,2255](src/web/routes.py#L2060) while returning `list[dict(row)]` from the repository ([src/web/repository.py:3672-3684](src/web/repository.py#L3672)).
- Existing behavior: shapes match the models (no `created_at` on either table, so no missing fields); FastAPI serializes the dicts.
- Correction: keep as-is, but 3A contract tests must pin the exact use/member response fields so the React types cannot drift.
- Blocks: no.

**I8. (RESOLVED in Phase 3B/3C) Legacy save pattern was a full-page reload; assignment POST returned a redirect; merge had no UI.**
- Reference: every batch save does `window.location.reload()` ([src/web/static/batch-dashboard.js:399](src/web/static/batch-dashboard.js#L399)); assignment POST returns a 303 redirect ([src/web/routes.py:662-665](src/web/routes.py#L662)); merge endpoints exist ([src/web/routes.py:2109,2304](src/web/routes.py#L2109)) with no UI anywhere.
- Correction: React uses per-mutation synchronization — PATCH preparation/execution updates the local row from the returned record; PATCH batch status (204) and split/merge (topology and membership changes) trigger a full run-sheet refetch; deviation POST appends the returned record; assignment POST replaces local state with the returned complete `ResultDetailResponse`. No browser-level full-page reload. BatchDetailPage ships the first merge UI (Phase 3B).
- Blocks: no.

**I9. (RESOLVED in Phase 3A) `created_by_id` was missing from result read models.**
- Reference: `get_result` selects fourteen columns but not `result_files.c.created_by_id` ([src/web/repository.py:1531-1548](src/web/repository.py#L1531)); `_result_record` builds the dict without it ([src/web/repository.py:5317-5331](src/web/repository.py#L5317)). `result_files.created_by_id` exists in the schema (nullable, FK users SET NULL).
- Why it matters: the Phase 3 result detail page shows upload provenance.
- Correction: add `result_files.c.created_by_id` to the selects of `get_result`, `list_results_for_experiment`, and `list_results_for_batch` so `_result_record` has one consistent row contract ([repository.py:1531,1555,1578](src/web/repository.py#L1531)), and emit `"created_by_id": int(row["created_by_id"]) if row["created_by_id"] is not None else None` from `_result_record` ([repository.py:5317](src/web/repository.py#L5317)); include `created_by_id` in `ResultDetailResponse` — `int | None` in Pydantic, `number | null` in TypeScript (`created_by_id` is nullable, FK users SET NULL); add a response-contract test asserting it and a regression test that the existing experiment-detail results list (`ExperimentDetailResponse.results`) still works with the extended row contract. The summary response models simply do not expose the field.
- Blocks: no.

### Minor

- **M1. Dead code in result-analysis.js**: `bulk-group-select`, `apply-bulk-group`, `.device-group-select` references ([src/web/static/result-analysis.js:12,15-16,77-87](src/web/static/result-analysis.js#L12)) target elements that do not exist in the template. Do not port.
- **M2. No `ErrorBoundary` / lazy loading in the React app** ([frontend/src/App.tsx:13-24](frontend/src/App.tsx#L13)) — a render error in a new page would blank the shell. Add an error boundary alongside the new routes (cheap, optional).
- **M3. `device_active_area_cm2` is a `str` in JSON** (Numeric(10,4) serialization, [src/web/routes.py:3144](src/web/routes.py#L3144)) — Phase 3 TS types must type it as `string` (already the pattern for `DeviceLayout`).
- **M4. Experiment auto-completion on assignment** ([src/web/repository.py:1780-1789](src/web/repository.py#L1780)) — the result page should reflect the resulting `plan_status` change (re-fetch or accept next visit); no code change needed.
- **M5. Legacy login `next` defaults to `/experiments`** ([src/web/auth_routes.py:54](src/web/auth_routes.py#L54)) — Phase 4 concern; unchanged in Phase 3.
- **M6. `result_files.content` holds up to 10 MiB blobs** ([src/web/database.py:499](src/web/database.py#L499)) — size-boundary behavior is covered by targeted API/unit tests; the PG suite exercises a small valid CSV upload plus a binary-content round-trip (see plan 3A.5).

## 3. Existing backend API inventory

Auth/session: `GET /login`, `POST /login` (login_csrf), `POST /logout`, `GET /api/session`, `GET /api/auth/login-csrf`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET|POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/password`, `GET|POST /admin/users`, `POST /admin/users/{id}/access`, `POST /admin/users/{id}/password` ([src/web/auth_routes.py](src/web/auth_routes.py)).

Every route on the main router requires login ([src/web/routes.py:130-137](src/web/routes.py#L130)).

Experiments: HTML `GET /`, `GET /experiments`, `GET /experiments/new`, `POST /experiments`, `GET /experiments/{id}`, `GET|POST /experiments/{id}/substrate-exceptions`, `POST /experiments/{id}/substrate-exceptions/{eid}/decision` (instructor), `POST /experiments/{id}/plan-status`, `GET /experiments/{id}/upload`, `POST /experiments/{id}/results`, `GET /experiments/{id}/results/{fid}/analysis`, `POST /experiments/{id}/results/{fid}/assignments` (form). JSON: `POST|GET /api/experiments`, `GET /api/experiments/{id}`, `POST /api/experiments/{id}/results` (multipart JSON upload, the only existing result JSON API, [src/web/routes.py:751](src/web/routes.py#L751)).

Conditions/exceptions: `GET|POST /api/experiments/{id}/conditions`, `PUT|DELETE /api/conditions/{cid}`, `POST /api/conditions/{cid}/substrate-exceptions`, `POST /api/substrate-exceptions/{eid}/decision` (instructor), `PATCH /api/experiments/{id}/plan-status`.

Library: `GET|POST /api/baselines`, `PUT|DELETE /api/baselines/{id}`, `GET /api/baselines/{id}` and `/versions`; `GET|POST /api/layer-presets`, `PUT|DELETE /api/layer-presets/{id}`, `GET /api/layer-presets/{id}/versions`; `GET|POST /api/materials`, `PATCH /api/materials/{id}`, `POST /api/materials/{id}/products`, `PATCH /api/material-products/{id}`; `GET|POST /api/campaigns`, `PATCH /api/campaigns/{code}`; `GET /api/device-layouts`.

Fabrication batches (all JSON, all login + ownership-checked, CSRF on every POST/PATCH):
- `POST /api/experiments/{id}/fabrication-batches` (201), `GET /api/experiments/{id}/fabrication-batches`, `GET /api/fabrication-batches/{batch_id}` (200/404), `PATCH /api/fabrication-batches/{batch_id}/status` (204, payload `{status}`).
- `GET /api/fabrication-batches/{batch_id}/conditions` (`FrozenBatchConditionResponse`), `.../substrates`, `.../devices`, `.../solution-preparations` (+ `POST` create, `PATCH` update, `POST .../split`, `POST .../merge`, `GET .../uses`), `.../process-executions` (+ `POST`, `PATCH`, `POST .../split`, `POST .../merge`, `GET .../members`), `.../deviations` (+ `POST`).
- HTML dashboard `GET /experiments/{id}/batches/{batch_id}`; exports `GET /experiments/{id}/batches/{batch_id}/export.json` (schema v5) and `export.pdf`; plan exports `GET /experiments/{id}/export.json|pdf`.

All mutations map `KeyError → 404`, `PermissionError → 403`, `ValueError/TypeError → 400`; status transitions table at [src/web/repository.py:4542](src/web/repository.py#L4542); batch write ops require `DRAFT` for create/split/merge, `{DRAFT, READY, IN_PROGRESS}` for actual recording, via `_batch_for_actor` ([src/web/repository.py:4603](src/web/repository.py#L4603)); readiness gate ([repository.py:4643](src/web/repository.py#L4643)) and completion gate ([repository.py:4678](src/web/repository.py#L4678)) enforced server-side.

Upload bounds: 10 MiB cap ([routes.py:113](src/web/routes.py#L113)), 1 MiB chunks, `.csv` extension + content-type allowlist ([routes.py:115-123,2978-2999](src/web/routes.py#L2978)), duplicate SHA-256 rejection ([repository.py:1480-1487](src/web/repository.py#L1480)).

## 4. Missing API contracts (exact required contracts)

Conventions for all: login required (router-level `require_user`); ownership via the 404 convention; students restricted to their own experiments (`_student_owner_id`, [routes.py:3046](src/web/routes.py#L3046)); CSRF on the POST only; no pagination (bare arrays, `created_at DESC`); responses are complete records/snapshots, never live references.

### `GET /api/fabrication-batches`
- Auth/min role: login, any role.
- Student ownership: students receive only batches whose experiment `created_by_id == user.id`; instructors/admins receive all. Filtered server-side in the repository query.
- Query params: `status` (optional enum: draft/ready/in_progress/completed/cancelled), `experiment_id` (optional int). Ordering fixed `created_at DESC`.
- Response: `list[FabricationBatchListItemResponse]` = `FabricationBatchResponse` fields + `experiment_code` (needed for list display; legacy history list shows codes).
- Status codes: 200; 404 for an `experiment_id` filter the actor cannot see (via `_get_record_or_404`).
- Repository: new `list_fabrication_batches_for_actor(owner_user_id, status, experiment_id)` joining `fabrication_batches` → `experiments`; reuse `_student_owner_id` semantics.
- Snapshot completeness: summaries (each carries `condition_set_hash`); full snapshots come from the run-sheet detail.
- Jinja-only info replaced: none (new page; per-experiment list existed).

### `GET /api/results`
- Auth/min role: login, any role. Same ownership policy as above.
- Query params: `experiment_id`, `fabrication_batch_id` (optional ints). Ordering `created_at DESC`.
- Response: `list[ResultListItemResponse]` = `ResultSummaryResponse` fields + `experiment_code` + `batch_code`.
- Repository: new `list_results_for_actor(owner_user_id, experiment_id, fabrication_batch_id)`.
- Status codes: 200; 404 for filtered experiments/batches outside the actor's scope.

### `GET /api/results/{file_id}`
- Auth/min role: login, any role.
- Student ownership: fetch result, then `_get_record_or_404(repository, result["experiment_id"], auth_context)` — **must precede any data use** (finding I3); non-owner → 404.
- Response: `ResultDetailResponse` = result row (id, experiment_id, fabrication_batch_id, filename, content_type, size_bytes, sha256, group_assignment, metrics, analysis, analysis_schema_version, created_at, **created_by_id** — provenance, I9; `int | None` in Pydantic, `number | null` in TypeScript) + `groups` (frozen batch conditions via `_batch_result_groups`, [routes.py:3002](src/web/routes.py#L3002)) + `assignments` (provenance/detail rows from `repository.list_result_device_assignments`, which already join condition/device/substrate codes, [repository.py:1601-1620](src/web/repository.py#L1601)).
- Status codes: 200 / 404.
- Repository: add `result_files.c.created_by_id` to the selects of `get_result`, `list_results_for_experiment`, and `list_results_for_batch` (one consistent row contract for `_result_record`, [repository.py:1531,1555,1578](src/web/repository.py#L1531)) and emit it from `_result_record` ([repository.py:5317](src/web/repository.py#L5317)); add a regression test that the existing experiment-detail results list still works; reuse `list_result_device_assignments`, `get_fabrication_batch_conditions`.
- CSRF: none (GET).
- Jinja-only info replaced: the entire `result_analysis.html` context (`result`, `groups`, `analysis` — [routes.py:586-595](src/web/routes.py#L586)).

### `GET /api/results/{file_id}/assignments`
- Auth/min role: login, any role; same ownership gate as the detail route.
- Response: `list[ResultAssignmentRowResponse]` = rows from `list_result_device_assignments` (per-device rows: analysis_device_id, analysis_substrate_id, instrument_label, fabrication_device_id + joined device_code/mark, substrate codes, batch_condition_id + condition_code/name).
- Status codes: 200 / 404.
- Repository: reuse `list_result_device_assignments` as-is.
- Jinja-only info replaced: assignments were previously reachable only via the batch `export.json` payload ([routes.py:2628-2632](src/web/routes.py#L2628)).
- **Role in the React page**: provenance/detail display only — the canonical form source is `analysis.substrates` (see the plan, 3C.3).

### `POST /api/results/{file_id}/assignments`
- Auth/min role: login, any role; same ownership gate.
- CSRF: required (`require_csrf`).
- Request model:
  ```json
  {
    "assignments": [
      { "analysis_substrate_id": "A01", "batch_condition_id": 42 }
    ]
  }
  ```
  - `analysis_substrate_id`: the substrate identifier as it appears in the parsed JV analysis (`analysis.substrates[].substrate_id`, e.g. `"A01"`).
  - `batch_condition_id`: the database `fabrication_batch_conditions.id` of the frozen condition (the same value the legacy UI offered as `group_id` via `_batch_result_groups`, [routes.py:3002-3012](src/web/routes.py#L3002)).
- Route validation (new, Pydantic + explicit checks):
  1. Duplicate `analysis_substrate_id` entries are rejected with 400.
  2. The submitted substrate ID set must **exactly equal** the analysis substrate ID set — missing or extra substrates are rejected with 400 (mirrors the legacy "every substrate must be assigned" rule, [jv_parser.py:216-217](src/web/jv_parser.py#L216)).
  3. Every `batch_condition_id` must belong to the result's fabrication batch (preserved server-side: `assign_substrates_to_groups` rejects unknown groups and `update_result_analysis_and_complete` verifies conditions belong to the result's batch, [repository.py:1684-1694](src/web/repository.py#L1684)).
- Behavior after validation: convert to the legacy shape `{substrate_id: str(batch_condition_id)}`; `run_in_threadpool(assign_substrates_to_groups, analysis, assignments, groups)`; build the legacy `assignment_summary` string; `repository.update_result_analysis_and_complete(file_id, analysis, substrate_assignments={k: int(v)}, group_assignment=summary, actor_user_id, client_ip)`.
- Response: 200 `ResultDetailResponse` (recomputed analysis with statistics) — replaces the legacy 303 redirect; the client replaces its local state with this response.
- Status codes: 200 / 400 (validation) / 404.
- Required tests: 401 anonymous; CSRF missing → 403; student cross-access → 404; duplicate `analysis_substrate_id` → 400; missing substrate (set mismatch) → 400; extra substrate (set mismatch) → 400; `batch_condition_id` from another batch → 400; successful assignment updates analysis + assignment rows + `group_assignment` and returns a complete `ResultDetailResponse`; instructor can assign into student's result.

### `GET /api/fabrication-batches/{batch_id}/run-sheet` (recommended, finding I1)
- Auth/min role: login, any role; ownership via the existing `_batch_for_actor_or_404` pattern ([routes.py:2594](src/web/routes.py#L2594)).
- Response: `RunSheetResponse` = batch (`FabricationBatchResponse`) + `conditions` (frozen) + `substrates` + `devices` + `preparations` (each with `uses`) + `executions` (each with `members`) + `deviations` + `editor_config` (`{vcd_valves, max_solid_chemicals, max_solvents}` from the constants used at [routes.py:2509-2513](src/web/routes.py#L2509)).
- Repository: new `get_batch_run_sheet(batch_id)` composing the existing batch-scoped list methods (all already exist; no new queries of substance).
- Status codes: 200 / 404. No CSRF (GET).
- Required tests: shape test pinning uses/members/editor_config fields; 404 for cross-student access; PG isolation test.

## 5. Complete legacy behavior inventory (what must be preserved or deliberately dropped)

### Batch dashboard ([batch.html](src/web/templates/batch.html), [batch-dashboard.js](src/web/static/batch-dashboard.js))

1. **Status transitions**: server table `draft→ready/cancelled, ready→in_progress/cancelled, in_progress→completed/cancelled`, terminal completed/cancelled ([repository.py:4542](src/web/repository.py#L4542)). UI shows the form only for non-terminal batches; the submit button's `value` is the target status ([batch.html:53-66](src/web/templates/batch.html#L53)); **Cancel batch rendered only for instructor/administrator** ([batch.html:62-64](src/web/templates/batch.html#L62)); readiness gate (every prep has ≥1 use, every exec has ≥1 member) and completion gate (preps consumed/discarded, execs terminal) enforced server-side. Port: role-gated button visibility + server-enforced transitions; React must not trust client gating.
2. **Run-sheet layout**: header (batch code, status badge, timestamps, export links), status card, frozen-conditions card (layout, counts, `source_condition_hash[:16]`), substrates & devices card (marks, status badges), solution-preparations card, process-executions card, deviations card. Preparations and executions are parallel tables — no interleaved step sequence. Port as-is.
3. **Preparation recording**: per-prep form gated by prep status; status select options gated by the server transition table (`planned→preparing/ready/discarded`, `preparing→ready/discarded`, `ready→consumed/discarded`); three-way recording choice — not recorded / `copied_from_plan` / `entered` — which maps to payload `actual_matches_planned: true` or `actual_solution_snapshot: {...}` ([batch-dashboard.js:331-341](src/web/static/batch-dashboard.js#L331)); `actual_recording_mode` is **server-derived, never sent** ([repository.py:3904-3920](src/web/repository.py#L3904)); PATCH `.../solution-preparations/{id}` ([routes.py:2137](src/web/routes.py#L2137)).
4. **Snapshot editor**: client-side widget rendering planned/actual JSON snapshots — field labels/units, numeric/integer fields, array add/remove with min/max from `arrayRules` (solids 1–`max_solid_chemicals`, solvents 1–`max_solvents`, spin_steps 1–4, anneal_steps 1–2, vcd_stages 1–5, gas_backfill_stages 0–5), formulation-type swap (`weighed_solids` vs `diluted_dispersion`), `sputter_mode` select, valve select from server `vcd_valves`, VCD `vcd_step_sequence` reorder with ↑/↓ and add/remove keeping the sequence in sync ([batch-dashboard.js:10-312](src/web/static/batch-dashboard.js#L10)). Pure client behavior — reimplement as a shared React `SnapshotEditor` (the field tables duplicate what the experiment builder does; share once in React). Seed from API JSON, not `#batch-editor-config`.
5. **Execution recording**: same three-way choice; `equipment_identifier`; status options `planned→ready/cancelled`, `planned|ready→running`, `running→completed/failed/cancelled`; PATCH `.../process-executions/{id}`; VCD snapshots preserve `vcd_step_sequence` ([tests/test_fabrication_batches.py:1021-1044](tests/test_fabrication_batches.py#L1021)).
6. **Split**: `<details>` disclosure, only when `batch.status == 'draft'` and >1 uses/members; checkboxes per use/member; POST `{member_ids: [int], notes: ""}` ([batch-dashboard.js:328-330](src/web/static/batch-dashboard.js#L328)); **no client-side quantity math** — server divides. Port: selection UI + server division.
7. **Merge**: no legacy UI exists ([batch-dashboard.js](src/web/static/batch-dashboard.js) has no merge kind; endpoints at [routes.py:2109,2304](src/web/routes.py#L2109)); React ships the first UI: pick a `{source_id}` with identical planned hash + status planned; POST merge.
8. **Deviations**: append-only list (category/severity badges, supersedes anchor links, recorded timestamp); form with category (7 values), severity (4 values), target select (`""` = batch, plus `solution_preparation_id:{id}` / `process_execution_id:{id}` / `substrate_id:{id}` / `device_id:{id}`), required description, optional `planned_value`/`actual_value` JSON textareas parsed client-side ([batch-dashboard.js:354-370](src/web/static/batch-dashboard.js#L354)); JSON API takes the decoded fields directly (the `field:id` encoding is a form artifact — React sends the fields). `supersedes_deviation_id` accepted by the server but never exposed in the legacy UI; keep out of Phase 3 UI scope.
9. **Save pattern**: full-page reload after every save ([batch-dashboard.js:399](src/web/static/batch-dashboard.js#L399)) — replaced by per-mutation synchronization (finding I8): PATCH preparation/execution updates the row from the returned record; PATCH batch status (204) and split/merge refetch the run-sheet; deviation POST appends the returned record. No browser-level full-page reload.
10. **Client-side calculations: none.** All math/validation/hashing is server-side.
11. **Dead code to drop**: nothing in batch-dashboard.js; the `<details>` splits and JSON textarea parsing are the only client logic.

### Result upload ([upload.html](src/web/templates/upload.html))

1. Batch select filtered to `IN_PROGRESS`/`COMPLETED` batches only ([routes.py:503-509](src/web/routes.py#L503)); empty state "Start a fabrication batch before uploading results."
2. Expected-groups badge strip from `experiment.recipe.device_recipe.experimental_groups` (control → secondary, others → primary) — a hint for the assignment page; requires the experiment JSON.
3. Multipart POST with hidden `csrf_token`, `accept=".csv,text/csv"`; server enforces 10 MiB cap, empty/NUL/control-char/extension/content-type rules ([routes.py:113-123,2961-2999](src/web/routes.py#L2961)); SHA-256 dedupe per batch; JV parse in threadpool; success → analysis page.
4. No JS, no chunking, no progress UI, no hash display on this page.
5. React portrait: use the existing `POST /api/experiments/{experiment_id}/results` JSON API ([routes.py:751](src/web/routes.py#L751)) with `FormData` through `apiFetch` (CSRF header automatic); client-side 10 MB guard + `accept=".csv"` as UX only; surface JSON `detail` errors; navigate to `/app/results/{id}` on success.

### Result analysis ([result_analysis.html](src/web/templates/result_analysis.html), [result-analysis.js](src/web/static/result-analysis.js))

1. **Assignment workflow**: per-substrate group `<select>` (all groups must be assigned — server rejects any unassigned substrate); submit text switches on `assignments_complete` (`statistics.groups` present, [result_analysis.html:23](src/web/templates/result_analysis.html#L23)); server recomputes `analysis.statistics`, writes assignment rows, embeds assignment info into the analysis JSON (including `batch_condition_id` per substrate, [repository.py:1716-1758](src/web/repository.py#L1716)), auto-completes the experiment ([repository.py:1780-1789](src/web/repository.py#L1780)). React: JSON POST, replace local state with the returned detail. **Preselection source**: the canonical unique substrate list is `analysis.substrates`; preselect each row from `analysis.substrates[].batch_condition_id`; the `result_device_assignments` rows are provenance/detail rows, not the form-row source — always derive the form from the analysis, and render an explicit inconsistency notice if per-device assignment rows disagree with the substrate-level condition (or with each other) instead of silently picking one.
2. **JV curves**: hand-built SVG (no library) — polarity normalization (zero-crossing nearest V=0, current sign, keep V≥0/I≥0 quadrant, [result-analysis.js:174-183](src/web/static/result-analysis.js#L174)); viewBox 430×300, 5 gridlines, Forward solid `#D97706` / Reverse dashed `#0891B2`, sample dots, native `<title>` tooltips, per-device 4-cell metrics table; plot controls: select-all, toggle-all with indeterminate, **select best device per group** (max PCE), plot caps at 12 devices, clear ([result-analysis.js:242-256](src/web/static/result-analysis.js#L242)). React: reimplement as SVG components (CSP `script-src 'self'` forbids CDN chart libs; no dependency needed).
3. **Box plots**: hand-built SVG per metric (voc/jsc/ff/pce) — whisker min–max, Q1–Q3 box, median, mean, jittered points, per-group colors palette of 5, `n=` labels, auto-padded axes ([result-analysis.js:102-168](src/web/static/result-analysis.js#L102)). Data comes from server-computed `analysis.statistics` — **no client-side statistics**.
4. **Metrics tables**: per-group mean±SD and median [Q1,Q3] for Voc/Jsc/FF/PCE; FF ×100; comparisons table (mean diff, percent diff, effect size, permutation p-value, adjusted p-value, `title={test_method}`), "Insufficient data" colspan row — all server-rendered from `statistics`; React renders the same JSON.
5. **Integrity metadata**: minimal in legacy — filename + device/trace counts only; **no file hash displayed**. React may show sha256/size/creator from the new detail API (data exists; display is an enhancement, keep parity at minimum).
6. **No editing/re-parse/delete** of parsed data in legacy; none planned.
7. **Zero fetch calls** in result-analysis.js — it renders only inline JSON; the only mutation is the form POST. Dead code (`bulk-group-select` etc.) must not be ported.
8. Accessibility heritage: `role="img"` + `aria-label` on SVG charts, `aria-label` on checkboxes, sticky device-table headers, `container-fluid` responsive grid with `minmax(320px, 1fr)` chart columns — replicate in React.

## 6. Data-integrity review

No blocking data-integrity defects were found in the reviewed paths. Per-invariant verdicts:

- **Frozen planned snapshots**: `create_fabrication_batch` copies each condition's `recipe_snapshot`, `device_layout_snapshot`, `canonical_hash`, and schema version into `fabrication_batch_conditions`, re-validating hash consistency at freeze time ([repository.py:3004-3036,2927-2931](src/web/repository.py#L3004)); the frozen row is independent of the live condition thereafter. `source_condition_id` FK RESTRICT prevents the source from disappearing. **Holds.**
- **Actual snapshots**: `solution_preparations`/`process_executions` pair planned/actual columns with all-or-nothing CHECK constraints and `actual_recording_mode` ∈ {NULL, copied_from_plan, entered} ([database.py:776-791,868-887](src/web/database.py#L776)); recording actual values never mutates the planned snapshot (separate columns + separate hashes). **Holds** — the "recording must not mutate planned" requirement is satisfied by schema.
- **Immutable hashes**: `snapshot_hash` = SHA-256 over canonical JSON ([execution_snapshots.py:192-203](src/web/execution_snapshots.py#L192)); condition `canonical_hash` uses `default=str` canonicalization ([condition_snapshot.py:153-160](src/web/condition_snapshot.py#L153)) — two different canonicalizations exist; both are stable and round-trip through validation. No mutation path exists for snapshot columns. **Holds.**
- **Split/merge**: split copies the source's planned snapshot/hash/schema to the child and reparents selected members ([repository.py:3739-3743,4160-4164](src/web/repository.py#L3739)); merge requires identical planned hashes + both `planned` status + no deviation references + no overlap ([repository.py:3798-3813,4233-4246](src/web/repository.py#L3798)). Frozen-parents invariant holds: children derive from the frozen planned snapshot, never from a live reference. **Holds.**
- **Deviations**: append-only with `supersedes_deviation_id` self-FK chain; at-most-one-target CHECK + model validator + repository link validation across batch boundaries ([database.py:947-970](src/web/database.py#L947), [repository.py:4715-4788](src/web/repository.py#L4715)). **Holds.**
- **Result provenance**: `result_files` carries filename/content_type/size/sha256/analysis/metrics/schema-version/created_by; `result_device_assignments` FK RESTRICT to batch conditions and devices with double-unique constraints; upload dedupe by (batch, sha256). The new `ResultDetailResponse` adds `created_by_id` (I9), sourced from one consistent row contract across all three result read methods. **Holds.**
- **Export completeness**: batch export v5 includes frozen conditions + both planned and actual snapshots + deviations + results (analysis, metrics, group_assignment) + assignment rows ([plan_export.py:268-462](src/web/plan_export.py#L268)); canonical JSON serialization rejects NaN/Infinity. **Holds** — React reuses these URLs unchanged.
- **Reference-dependency audit**: every saved record that references a template also carries an expanded snapshot (baseline_versions immutable + RESTRICT; batch conditions frozen; preset versions immutable; material specs JSONB). One soft dependency: `device_layout_code` is re-checked against the live catalog at plan release ([repository.py:4966-4970](src/web/repository.py#L4966)) — the only mutation path is a data migration (0011), and the frozen snapshot remains authoritative. **Holds.**

## 7. Authorization matrix

| Operation | Student | Instructor | Administrator |
|---|---|---|---|
| View own-experiment batches/results | ✅ | ✅ | ✅ |
| View other students' batches/results | ❌ 404 (server-scoped lists) | ✅ (all) | ✅ (all) |
| Create batch (own released plan) | ✅ | ✅ | ✅ |
| Record preparations / executions / deviations / actuals | ✅ (own) | ✅ | ✅ |
| Status transitions (draft→ready→in_progress→completed) | ✅ (own) | ✅ | ✅ |
| **Cancel batch** | ❌ 403 | ✅ | ✅ |
| Plan-status approve (instructor step) | ❌ 403 | ✅ | ✅ |
| Substrate-exception decision | ❌ | ✅ | ✅ |
| Upload results (own experiment, eligible batch) | ✅ | ✅ | ✅ |
| Assign results substrates→conditions | ✅ (own) | ✅ | ✅ |
| Campaigns / materials / baselines management | ❌ (read-only) | ✅ | ✅ (baseline edit/archive: admin) |
| User management | ❌ | ❌ | ✅ |

Enforcement points: router-level `require_user` ([routes.py:137](src/web/routes.py#L137)); `_get_record_or_404` + `_student_owner_id` (404 convention, [routes.py:3029-3051](src/web/routes.py#L3029)); `_batch_for_actor` lock + re-check ([repository.py:4603-4631](src/web/repository.py#L4603)); student-cancel rejection ([repository.py:3461-3464](src/web/repository.py#L3461)); `require_role` for instructor actions; CSRF via `require_csrf` + same-origin middleware ([src/web/middleware.py:101-111](src/web/middleware.py#L101)). React role gating is presentational only.

## 8. Phase 2 compatibility risks

1. ExperimentDetailPage anchors to legacy batch/upload pages ([ExperimentDetailPage.tsx:215,227](frontend/src/pages/ExperimentDetailPage.tsx#L215)) — must flip to React `<Link>`s in 3B/3C or Phase 3 pages are unreachable from the SPA shell.
2. `test_phase2_api.py` and `test_phase3_api.py` share the legacy form-login session setup ([test_phase2_api.py:50-68](tests/test_phase2_api.py#L50)) — keep that coupling; it mirrors the legacy login `next` default ([auth_routes.py:54](src/web/auth_routes.py#L54)).
3. No pagination anywhere (I4) — global lists are the first large lists; server-side filtering keeps them bounded.
4. `useApiResource` has no mutation-refresh primitive — batch/result pages use the per-mutation synchronization strategy (I8) built on the established `localDetail` override pattern ([ExperimentDetailPage.tsx:55](frontend/src/pages/ExperimentDetailPage.tsx#L55)).
5. Bundle growth without lazy loading ([App.tsx:13-24](frontend/src/App.tsx#L13)) — optional `React.lazy` for the new pages; not required.
6. Overview/Experiments pages list experiments only; no change needed for Phase 3.

## 9. Migration and PostgreSQL risks

1. **No schema/migration changes are required for Phase 3** — every needed column and table exists (0007 schema). Any 3A work must not introduce a migration.
2. `with_for_update()` is a no-op on SQLite ([repository.py:3614](src/web/repository.py#L3614) et al.) — SQLite tests cannot exercise lock semantics; the new repository queries (global lists, run-sheet composition) are introduced in 3A, so **PostgreSQL testing is mandatory at the 3A gate** (extend `test_postgresql_integration.py` `_exercise_fabrication_batch`, [test_postgresql_integration.py:332-389](tests/test_postgresql_integration.py#L332)).
3. JSONB/JSON transparent via `with_variant` ([database.py:46](src/web/database.py#L46)); advisory locks dialect-guarded; no ILIKE/raw ON CONFLICT outside the catalog service. Low risk.
4. `result_files.content` LargeBinary: the PG suite uploads a **small valid CSV** and round-trips **binary content**; the 10 MiB size-boundary behavior stays in targeted API/unit tests (upload bounds, [routes.py:113](src/web/routes.py#L113)).
5. `Numeric(10,4)` → `str` serialization (M3) — TS `string` typing.
6. Alembic env requires `postgresql+asyncpg://` and refuses SQLite ([migrations/env.py:22-35](migrations/env.py#L22)) — PG acceptance runs via `PEROVSKITE_TEST_POSTGRESQL_URL` / `scripts/Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`.

## 10. Recommended internal Phase 3 checkpoints

- **3A gate**: all new endpoint contracts + authorization + run-sheet shape tests green; **PostgreSQL isolation tests green (mandatory at 3A — new repository queries)**; TS types compile; no React pages added. External review.
- **3B gate**: batch list + run sheet fully functional (status, recording, split, merge, deviations, exports) with vitest + browser tests; 320 px verified. External review.
- **3C gate**: results list, upload, analysis, assignments, charts, exports with vitest + browser tests; 320 px verified. External review.
- **3D gate**: full acceptance matrix (React suite incl. build, complete SQLite suite, Vite smoke, PostgreSQL suite, wheel inspection, `git diff --check`); docs updated; legacy pages untouched. Phase 3 sign-off.