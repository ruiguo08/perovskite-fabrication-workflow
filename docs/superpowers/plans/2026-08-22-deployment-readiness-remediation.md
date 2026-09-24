# Deployment Readiness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the confirmed data-integrity, migration, transaction, frontend-state, and release-pipeline blockers before the first controlled deployment.

**Architecture:** PostgreSQL remains the source of truth and the transaction boundary. Result parsing preserves physical substrate and channel identity, batch completion is one backend transaction, and plan workflow mutations serialize on the parent experiment row. React supplies clear recovery and destructive-change UX, but never replaces backend validation or database constraints.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, PostgreSQL 18, Alembic, React 19, TypeScript, Vite, Vitest, pnpm 11 through Corepack, GitHub Actions, systemd, Chrome.

## Confirmed owner decisions

1. **The first deployment is a controlled trial only.** It is for workflow validation and training, not authoritative research-data collection. Until P0-1 environment capture and P0-2 material-lot provenance are implemented end to end, trial data must not be used as authoritative research evidence or optimizer/model training data.
2. **The application release version remains `0.4.0`.** This remediation must not bump `src/web/version.py`. The private frontend package's `0.1.0` is not the product release version and is not changed merely for cosmetic alignment.
3. **No pre-squash database contains data that must be preserved.** The current database contains disposable initial test data. Formal deployment uses a new empty PostgreSQL database upgraded through the current squashed chain. The old test database may be backed up for troubleshooting, but it is never promoted or migrated into production.

## Global constraints

- Execute on branch `codex/deployment-readiness`; never work on `main`.
- Work test-first. For every behavior change, add a focused regression, run it, and record the expected RED failure before editing production code.
- Preserve authorization, CSRF, origin checks, upload limits, snapshot integrity, audit logging, and append-only deviation history.
- Do not renumber or rewrite migration upgrades already present. Add all new forward schema/data work in `0014_deployment_integrity_repairs`. The only edit allowed in `0013` is replacing its unsafe downgrade body with an immediate explicit irreversible-migration failure before any DDL.
- PostgreSQL is the production contract. SQLite-only or mocked success is not acceptance for migrations, locking, constraint enforcement, or concurrency.
- Do not add empty environment/material-lot columns. Those require a separate end-to-end schema, API, UI, snapshot, export, and test design.
- Do not introduce a general undo framework, split the large repository/router modules, or upgrade unrelated dependencies.
- Preserve unrelated user changes. Never use destructive reset/checkout commands.
- Each Task ends in an independently reviewable commit using its specified message.
- Do not deploy, push, merge, or announce deployment readiness during this plan.

## Required execution report

For Step 0 and every Task, report:

- files changed;
- the exact test that failed before implementation and why;
- verification commands, exit codes, pass/fail/skip counts;
- commit hash;
- residual risks or assumptions.

If code, schema, or domain evidence contradicts a Task, pause that Task and report the evidence. Do not silently change the contract.

---

## Step 0: Establish a clean, real baseline

**Files:**
- Modify: this plan only to incorporate any owner-approved corrections made before execution

- [ ] Confirm `git branch --show-current` prints `codex/deployment-readiness`.
- [ ] Confirm the only initial worktree change is this plan file. Do not delete it.
- [ ] Commit the finalized plan separately as `docs: finalize deployment remediation plan`, then confirm `git status --short` is empty.
- [ ] Run `scripts/Configure-LocalTestDatabase.ps1`, then `scripts/Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`, to configure and verify the disposable database. Refuse any URL whose database or role identifies the application/production database.
- [ ] Run `uv run --no-sync python -m unittest tests.test_postgresql_integration -v`. The module must execute rather than skip.
- [ ] Run `uv run --no-sync python -m unittest discover -s tests -v` and record the complete baseline, including every skip name and reason. If any baseline test fails, stop and report before changing code.
- [ ] Under `frontend/`, run `corepack pnpm --version`, `node --version`, `corepack pnpm install --frozen-lockfile`, `corepack pnpm test`, `corepack pnpm typecheck`, and `corepack pnpm lint`.
- [ ] Run `uv run --no-sync python -m unittest tests.test_browser_cutover -v` and report the Chrome executable path. A browser-suite skip means Step 0 is blocked.
- [ ] If PostgreSQL, Python 3.14, Node 24, pnpm 11, or Chrome cannot be made available, stop before Task 1. Do not substitute SQLite or mocks.

### Task 1: Preserve physical laser-mark and channel identity

**Files:**
- Modify: `src/web/jv_parser.py`
- Modify: `src/web/repository.py`
- Modify: `src/web/models.py`
- Modify: `src/web/routes.py` upload call site so it supplies the source filename
- Modify: `frontend/src/types/api.ts`
- Test: `tests/test_jv_parser.py`
- Test: `tests/test_phase3_api.py`
- Test: `tests/test_postgresql_integration.py`

**Interfaces:**
- Produce `ANALYSIS_SCHEMA_VERSION = 3`.
- Produce `normalize_laser_mark(value: str) -> str`, accepting canonical `^[A-Z]\d{3,8}$` after trim and uppercase normalization and raising `ValueError` otherwise.
- Produce `parse_channel_ordinal(label: str) -> int | None`, parsing case-insensitive `Channel N` with `N >= 1`.
- Every schema-3 analysis device contains positive integer `device_ordinal`; every substrate ID is its full canonical laser mark.

- [ ] Add parser regressions for `A001 Channel 2` and `A001 Channel 5` in reversed trace order. Assert substrate `A001`, device ordinals 2 and 5, and schema version 3.
- [ ] Add a regression proving forward/reverse traces for the same substrate/channel form one device rather than a duplicate-device error.
- [ ] Add regressions for missing, conflicting, zero, negative, duplicate normalized device, and out-of-layout channel ordinals. Result assignment must return a domain 400 with no mark or assignment changes.
- [ ] Add canonical-mark tests covering lowercase normalization, `A001`, a 9-character maximum mark, `Device 1`, short marks, multiple leading letters, punctuation, whitespace inside the mark, and overlength marks.
- [ ] For multi-device exports, derive mark and channel only from unambiguous instrument labels.
- [ ] For a simple export with no instrument identity, derive both the mark and `Channel N` from the source filename only when each occurs exactly once. Otherwise reject the upload before inserting `result_files`; the error must state the required naming shape, such as `A001 Channel 1.csv`.
- [ ] Replace appearance-order mapping with lookup by explicit `device_ordinal`. Verify channel 2/5 map to database device ordinals 2/5 rather than 1/2.
- [ ] Increment stored `analysis_schema_version` to 3 and update API/frontend types and existing schema-version assertions.
- [ ] In result association, lock the result row, then its parent `fabrication_batches` row, before loading conditions, marked substrates, blank substrates, or deleting old assignment rows. Use this same lock order in every assignment path.
- [ ] Add a real PostgreSQL two-transaction test: two distinct result rows in one batch attempt the same laser mark for different substrates. Exactly one transaction commits; the loser returns a domain conflict/error and leaves no partial rows.
- [ ] Run `uv run --no-sync python -m unittest tests.test_jv_parser tests.test_phase3_api tests.test_postgresql_integration -v` with PostgreSQL enabled.
- [ ] Commit as `fix: preserve result substrate and channel identity`.

### Task 2: Materialize actual counts above the plan

**Files:**
- Modify: `src/web/repository.py`
- Test: `tests/test_fabrication_batches.py`
- Test: `tests/test_phase3_api.py`
- Test: `tests/test_postgresql_integration.py`

**Interfaces:**
- Preserve the accepted rule that `actual_substrate_count > planned_substrate_count` is allowed and does not require a deviation.
- After completion, a condition has `max(planned_substrate_count, actual_substrate_count)` substrate slots. Existing planned slots are not deleted when actual is lower.
- Every added slot has all devices required by the frozen device-layout snapshot and membership in every existing frozen process-execution group for that condition/layer.

- [ ] Add a failing test completing a condition planned for 1 substrate with actual 3. Assert ordinals 2 and 3, their full device sets, and later result assignment to both new substrates.
- [ ] Assert added substrates have deterministic unique `substrate_code`, null `substrate_mark`, and added devices have deterministic unique `device_code`.
- [ ] Assert `planned_substrate_count` and `expected_device_count` remain the original plan values; actual capacity is represented by `actual_substrate_count` and the added rows, not by rewriting the frozen plan.
- [ ] Add each extra substrate to every existing `process_executions` group whose members contain the same `batch_condition_id` and `layer_ordinal`. Create only missing member rows and reuse the group's frozen execution identity.
- [ ] If a required condition/layer has no frozen execution group, fail completion instead of inventing execution history.
- [ ] Record the added substrate/device/member counts in the existing batch-completion audit event details.
- [ ] Extract one repository helper used by batch creation and completion for substrate/device/member materialization so identifier and layout logic cannot drift.
- [ ] Add rollback and retry tests proving no duplicate rows survive a failed or repeated completion.
- [ ] Add an `actual < planned` regression proving planned slots remain, no rows are deleted, and result association still rejects CSV substrate counts above actual.
- [ ] Run `uv run --no-sync python -m unittest tests.test_fabrication_batches tests.test_phase3_api tests.test_postgresql_integration -v` with PostgreSQL enabled.
- [ ] Commit as `fix: materialize actual batch substrate capacity`.

### Task 3: Add migration 0014 and typed deviation semantics

**Files:**
- Create: `migrations/versions/0014_deployment_integrity_repairs.py`
- Modify: `src/web/database.py`
- Modify: `src/web/models.py`
- Modify: `src/web/repository.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/pages/BatchDetailPage.tsx`
- Test: `tests/test_migrations.py`
- Test: `tests/test_fabrication_batches.py`
- Test: `tests/test_phase3_api.py`
- Test: `tests/test_postgresql_integration.py`
- Test: `frontend/src/pages/BatchDetailPage.test.tsx`

**Interfaces:**
- Add non-null `execution_deviations.deviation_type` with allowed values `general`, `fabrication_shortfall`, and `measurement_shortfall`.
- Add index `ix_execution_deviations_condition_type` on `(condition_id, deviation_type)`.
- An active deviation is a matching row for which no later row has `supersedes_deviation_id == candidate.id`.

- [ ] Add migration graph/metadata tests for revision `0014_deployment_integrity_repairs` revising `0013_substrate_laser_marks`.
- [ ] Add failing schema tests for `deviation_type`, its values check, the condition/type index, and an `at_most_one_deviation_target` check whose sum includes preparation, execution, substrate, device, and condition targets.
- [ ] In 0014, add `deviation_type` with a temporary server default `general`, backfill existing deviations, make it non-null, then remove the server default. Application inserts must always provide a type explicitly.
- [ ] Drop and recreate the target check so `condition_id` cannot coexist with any other specific target.
- [ ] In the same 0014 upgrade, backfill `actual_substrate_count = planned_substrate_count` only for completed batches whose actual count is null. Leave draft, ready, and in-progress values null.
- [ ] In the same 0014 upgrade, migrate stored analysis from schema 2 to 3 only when every affected device has one unambiguous canonical full mark and channel ordinal. Set full substrate IDs, explicit device ordinals, rebuild substrate grouping while preserving group/condition fields, and update `analysis_schema_version`.
- [ ] Leave ambiguous historical analyses unchanged at schema 2. Document `SELECT id, filename FROM result_files WHERE analysis_schema_version < 3` as the operator review query; never fabricate marks or channels.
- [ ] Implement a repository helper for active qualifying deviations using `NOT EXISTS` against superseding rows.
- [ ] Make fabrication shortfall gates require `fabrication_shortfall` for the same condition. Make measured-below-actual gates require `measurement_shortfall` for the same condition. `general` and unrelated category/type rows never qualify.
- [ ] Remove the duplicate `actual == 0` deviation query; zero actual is a fabrication shortfall with structured planned/actual values.
- [ ] Extend the manual deviation form with a deviation-type selector. Shortfall types are enabled only for a condition target; batch/preparation/execution/substrate/device deviations use `general`.
- [ ] Display and export `deviation_type` so operators can audit why a gate was unlocked.
- [ ] Add negative tests for wrong condition, general, unrelated, and superseded deviations. Add API and direct-PostgreSQL tests proving multiple targets are rejected at both layers.
- [ ] Run `uv run --no-sync python -m unittest tests.test_migrations tests.test_fabrication_batches tests.test_phase3_api tests.test_postgresql_integration -v`, then under `frontend/` run `corepack pnpm exec vitest run src/pages/BatchDetailPage.test.tsx`, `corepack pnpm typecheck`, and `corepack pnpm lint`.
- [ ] Commit as `fix: enforce typed condition deviations`.

### Task 4: Complete batches atomically

**Files:**
- Modify: `src/web/models.py`
- Modify: `src/web/routes.py`
- Modify: `src/web/repository.py`
- Modify: `frontend/src/components/CompleteBatchDialog.tsx`
- Modify: `frontend/src/pages/BatchDetailPage.tsx`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/components/CompleteBatchDialog.test.tsx`
- Modify: `frontend/src/pages/BatchDetailPage.test.tsx`
- Test: `tests/test_fabrication_batches.py`
- Test: `tests/test_phase3_api.py`
- Test: `tests/test_postgresql_integration.py`

**Interfaces:**
- Add `CompletionDeviationPayload` containing only positive `condition_id` and nonblank `description` up to 5000 characters.
- For `status == completed`, the status PATCH accepts exact condition coverage in `actual_substrate_counts` plus `completion_deviations`.
- The server derives category `substrate`, severity `warning`, type `fabrication_shortfall`, and structured planned/actual values.

- [ ] Add a backend RED test where completion supplies two shortfall explanations and a later validation fails. Assert deviations, actual counts, added capacity rows, status, timestamps, and audit events all roll back.
- [ ] Add a success test asserting the same records commit together in one transaction.
- [ ] Add a two-transaction PostgreSQL test submitting completion concurrently. Exactly one `in_progress -> completed` transition and one set of deviations/audit rows may commit.
- [ ] Move completion deviation insertion inside `update_fabrication_batch_status`'s existing transaction. Do not call a repository method that opens a nested/separate transaction.
- [ ] Validate that each actual-below-planned condition has exactly one matching completion explanation and that explanations cannot target another batch's condition.
- [ ] Remove the frontend loop that POSTs deviations individually. Submit one completion PATCH and refetch only after it succeeds.
- [ ] Model the count input as `number | ""`. Clearing the field produces `""`, disables submission, and shows a field-level validation message; it never silently becomes zero.
- [ ] Add frontend tests for one PATCH, failed PATCH retry without duplicates, empty-input behavior, condition coverage, and accessible error display.
- [ ] Run `uv run --no-sync python -m unittest tests.test_fabrication_batches tests.test_phase3_api tests.test_postgresql_integration -v`, then under `frontend/` run `corepack pnpm exec vitest run src/components/CompleteBatchDialog.test.tsx src/pages/BatchDetailPage.test.tsx`, `corepack pnpm typecheck`, and `corepack pnpm lint`.
- [ ] Commit as `fix: complete fabrication batches atomically`.

### Task 5: Make migration boundaries explicit and isolate pre-squash databases

**Files:**
- Modify: `migrations/versions/0013_substrate_laser_marks.py` downgrade only
- Modify: `src/web/admin_cli.py`
- Modify: `tests/test_migrations.py`
- Modify: `tests/test_release_config.py`
- Modify: `DEPLOYMENT.md`

**Interfaces:**
- 0014 supports downgrade to 0013.
- 0013 downgrade fails before executing DDL because its upgrade irreversibly discarded generated legacy marks.
- Schema preflight identifies an old pre-squash 0007-derived database by a recorded revision at/after old 0007 combined with missing `fabrication_substrates.substrate_mark` or `fabrication_devices.device_mark` columns.

- [ ] Add a populated PostgreSQL test upgrading an 0012-shaped squashed database with completed batches and both unambiguous and ambiguous schema-2 analyses to head. Verify the Task 3 backfills.
- [ ] Add a PostgreSQL cycle test `0012 -> head -> 0013 -> head`, verifying 0014's upgrade/downgrade behavior and data constraints.
- [ ] Replace 0013 downgrade's DDL with an immediate `RuntimeError` explaining that rollback requires restoration from a verified backup. Add a test attempting `0013 -> 0012`; it must fail before changing columns, constraints, data, or `alembic_version`.
- [ ] Do not generate replacement legacy marks. They would be fabricated physical identity.
- [ ] Add a pre-squash detection test representing revision `0007_fabrication_batches` without the two mark columns. `check-database` must reject it with a message that the database is incompatible and must not receive the squashed chain.
- [ ] Add a control test where the squashed 0007 schema contains both mark columns and passes the compatibility fingerprint.
- [ ] Document the exact information-schema preflight query, the incompatibility of old 0007-derived databases, and the owner decision to use a new empty production database.
- [ ] Document that the disposable test database may be recreated and that rollback of 0013+ production data is backup restoration, not Alembic downgrade to 0012.
- [ ] Run `uv run --no-sync python -m unittest tests.test_migrations tests.test_release_config tests.test_postgresql_integration -v` with PostgreSQL enabled.
- [ ] Commit as `fix: isolate incompatible migration histories`.

### Task 6: Serialize condition edits with plan workflow transitions

**Files:**
- Modify: `src/web/repository.py`
- Modify: `src/web/routes.py` for unknown-condition 404 translation
- Test: `tests/test_fabrication_batches.py`
- Test: `tests/test_phase2_api.py`
- Test: `tests/test_postgresql_integration.py`

**Interfaces:**
- Condition create/update/delete and plan status/freeze lock the same parent `experiments` row first.
- Lock order is experiment, then condition/exception, then dependent rows.

- [ ] Add PostgreSQL concurrency tests interleaving condition create/update/delete with approval, release, and batch freeze. Assert no released/frozen snapshot contains an unvalidated concurrent change.
- [ ] For update/delete, first resolve `experiment_id` from `condition_id` without making a workflow decision, then lock the experiment row with `FOR UPDATE`, then re-read the condition and current plan status under the lock before mutation.
- [ ] For condition creation, lock the supplied experiment row before checking status or inserting.
- [ ] Preserve the rule that substantive edits invalidate exceptions and return the plan to draft.
- [ ] Verify exception mutation does not acquire locks in the reverse order.
- [ ] Translate an unknown update/delete condition ID to the established 404 response rather than generic 400.
- [ ] Run `uv run --no-sync python -m unittest tests.test_fabrication_batches tests.test_phase2_api tests.test_postgresql_integration -v`, then run each new PostgreSQL concurrency test at least five times individually.
- [ ] Commit as `fix: serialize plan and condition mutations`.

### Task 7: Guard React route state and destructive plan changes

**Files:**
- Modify: `frontend/src/pages/ExperimentDetailPage.tsx`
- Modify: `frontend/src/pages/ExperimentDetailPage.test.tsx`
- Modify: `frontend/src/features/baseline-builder/BaselineAuthoring.tsx`
- Modify: `frontend/src/pages/BaselinesPage.test.tsx`
- Modify: `frontend/src/features/experiment-builder/ConditionPlanner.tsx`
- Modify: `frontend/src/features/experiment-builder/state.ts`
- Modify: `frontend/src/features/experiment-builder/state.test.ts`
- Modify: `frontend/src/components/ConfirmDialog.tsx`
- Modify: `frontend/src/components/ConfirmDialog.test.tsx`

**Interfaces:**
- Route-local async work carries a generation token and may update state/toasts only for the route that started it.
- A pure plan-type preview reports the specific conditions/condition-level recipe edits that would be discarded.

- [ ] Add an Experiment detail test navigating A to B without remounting while A's mutation completes late. A must never render or mutate under B.
- [ ] Mirror the proven Result detail pattern: synchronous route reset, active-detail ID guard, and generation checks before local state or toast updates.
- [ ] Add Baseline catalog-load rejection and retry tests. Replace the bare `.then()` loader with `useApiResource` and render loading, error/retry, and success states.
- [ ] Add state tests showing exactly what standalone/comparative switching preserves and discards after control/target edits.
- [ ] Implement a pure destructive-change preview. If nothing condition-specific is lost, switch immediately; otherwise open a confirmation listing the loss.
- [ ] The confirmation's initial safe action is Cancel. It has an accessible name/description, traps focus, supports Escape, and restores focus to the plan-type control.
- [ ] Do not implement a global undo system. Do not add confirmation to ordinary layer removal in this Task.
- [ ] Under `frontend/`, run `corepack pnpm exec vitest run src/pages/ExperimentDetailPage.test.tsx src/pages/BaselinesPage.test.tsx src/features/experiment-builder/state.test.ts src/components/ConfirmDialog.test.tsx`, `corepack pnpm typecheck`, and `corepack pnpm lint`.
- [ ] Commit as `fix: guard route state and destructive plan changes`.

### Task 8: Harden result rendering, logout recovery, and next-path handling

**Files:**
- Modify: `frontend/src/pages/ResultDetailPage.tsx`
- Modify: `frontend/src/pages/ResultDetailPage.test.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/components/AppShell.test.tsx`
- Modify: `frontend/src/auth/session.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/LoginPage.test.tsx`
- Modify: `src/web/auth.py`
- Test: `tests/test_auth_security.py`

- [ ] Add focused runtime type predicates for the schema-2/schema-3 analysis fields Result detail actually reads. Invalid required structure renders an unavailable-data state with result metadata rather than throwing; invalid optional statistics remain hidden.
- [ ] Do not add a new schema-validation dependency for this guard.
- [ ] Add a logout failure test. A failed server logout keeps/reports uncertain server-session state, displays retry, and does not silently claim revocation. A deliberately offered local-only exit must be explicitly labelled.
- [ ] Update both backend safe-next helpers and frontend `sanitizeNext` to reject backslashes, encoded backslashes after decoding, ASCII control characters, protocol-relative paths, API/health/login destinations, and export endpoints.
- [ ] Add backend and frontend cases for `/\\evil.example`, `//evil.example`, `%2F%5Cevil.example`, encoded control characters, valid `/app/experiments/42`, query strings, and fragments.
- [ ] Preserve BrowserRouter basename behavior: strip at most one `/app` prefix and reject repeated `/app/app` prefixes.
- [ ] Run `uv run --no-sync python -m unittest tests.test_auth_security -v`; under `frontend/`, run `corepack pnpm exec vitest run src/pages/ResultDetailPage.test.tsx src/components/AppShell.test.tsx src/pages/LoginPage.test.tsx`, `corepack pnpm typecheck`, and `corepack pnpm lint`.
- [ ] Commit as `fix: harden client recovery paths`.

### Task 9: Enforce schema head and the deployable frontend artifact

**Files:**
- Modify: `src/web/admin_cli.py`
- Modify: `deploy/perovskite-web.service`
- Modify: `deploy/perovskite-migrate.service`
- Modify: `.github/workflows/tests.yml`
- Modify: `tests/test_release_config.py`
- Modify: `tests/test_browser_builder.py`
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml` only as produced by the pinned package-manager metadata
- Test: admin CLI, release configuration, browser, Vite proxy, and installed-wheel smoke tests

- [ ] Add an admin CLI RED test where PostgreSQL is reachable and structurally compatible but `alembic_version` is behind head. `check-database` must exit nonzero and print current and expected revisions.
- [ ] Load expected head through Alembic `ScriptDirectory`; do not hard-code `0014_deployment_integrity_repairs` in application code.
- [ ] Preserve Task 5 pre-squash fingerprint rejection and run it before ordinary table probes that would fail obscurely.
- [ ] Make `perovskite-web.service` `Requires=` and `After=` the migration service while retaining `ExecStartPre=... check-database`. Add exact service-file tests for dependency and ordering.
- [ ] Add a frontend CI job with Node `24.x`. Set `frontend/package.json` to `packageManager: "pnpm@11.21.0"` and `engines.node: ">=24 <25"`; Corepack and CI consume those exact constraints.
- [ ] Run frozen install, Vitest, typecheck, lint, and production build in CI.
- [ ] After build, fail CI on `git diff --exit-code -- src/web/static-app`.
- [ ] Build a fresh Python wheel in CI and run installed-wheel smoke against that exact wheel, not a pre-existing `dist` artifact.
- [ ] Extend shared `tests.test_browser_builder.chrome_path()` with GitHub Ubuntu Chrome/Chromium locations. Run at least one real browser suite in CI and fail if browser detection returns None.
- [ ] Run Vite proxy smoke in a job where frontend dependencies are installed; it must execute rather than skip.
- [ ] Keep `src/web/version.py` at `0.4.0` and keep the private frontend version unchanged.
- [ ] Run `uv run --no-sync python -m unittest tests.test_release_config tests.test_vite_proxy_smoke tests.test_browser_cutover -v`; under `frontend/`, run frozen install, test, typecheck, lint, and build; then run `uv build` and finally `uv run --no-sync python -m unittest tests.test_installed_wheel_smoke -v` against the newly created wheel.
- [ ] Commit as `ci: enforce deployable frontend and schema head`.

### Task 10: Apply the controlled-trial release gate

**Files:**
- Modify: `DEPLOYMENT.md`
- Create: `docs/deployment-checklists/0.4.0-controlled-trial.md`
- Do not change product code in this Task; failures return to their owning Task

- [ ] Run `uv lock --check` and `uv build`; record exit codes and the new wheel filename.
- [ ] Run the full Python suite with the disposable PostgreSQL URL. `tests.test_postgresql_integration` must execute. Report every remaining skip by test name/reason; browser, PostgreSQL, and Vite smoke skips fail the gate, while documented platform-inapplicable skips may remain.
- [ ] Under `frontend/`, run frozen install, Vitest, typecheck, lint, and production build.
- [ ] Run `git diff --exit-code -- src/web/static-app` after the build.
- [ ] On a fresh empty PostgreSQL database, run Alembic upgrade head, Alembic check, schema-head preflight, and application database check.
- [ ] Run the populated `0012 -> head -> 0013 -> head` migration test and the separate fail-before-DDL `0013 -> 0012` test.
- [ ] Build a fresh wheel and run installed-wheel smoke against that wheel.
- [ ] Run all required real-browser suites and report the executable path.
- [ ] Run the result-assignment, batch-completion, and plan-condition concurrency tests at least five times each.
- [ ] Verify `src/web/version.py` reports `0.4.0` and record the static artifact hash.
- [ ] Rehearse backup and restore using the disposable staging database; record commands and outcome.
- [ ] Create the controlled-trial checklist containing database origin/fingerprint, current/expected Alembic revision, backup/restore evidence, version, wheel/static hashes, commands and exit codes, intentional skips, and unresolved risks.
- [ ] Add an explicit gate: P0-1 environment capture and P0-2 material-lot provenance must be implemented end to end before authoritative data collection. Until then, access is limited to trial workflow validation/training and trial data is excluded from research analysis and optimizer/model training.
- [ ] State that formal deployment uses a new empty database and that the disposable initial-test database is never promoted.
- [ ] Do not mark the system deployable and do not perform deployment. Report only whether the controlled-trial verification gates passed and what remains.
- [ ] Commit as `docs: define controlled trial release gate`.

## Explicitly deferred

- P0-1 environment humidity/temperature/O2/glovebox capture and P0-2 material lot/opened-on provenance, pending a separate end-to-end design.
- Migration/import of pre-squash test data; the owner has chosen a new empty formal database.
- General repository/router decomposition, N+1 optimization, expired-session cleanup jobs, and global undo.
- Writing `device_mark` solely because the nullable column exists. Physical identity remains canonical substrate mark plus validated device ordinal.
- Cosmetic UI additions that do not affect the integrity, workflow, accessibility, or release gates above.

## Stop conditions

- PostgreSQL integration, Chrome, Node 24, pnpm 11, or Python 3.14 cannot be made available.
- A RED test fails for a reason other than the intended missing behavior.
- A Task requires weakening a security, authorization, audit, or snapshot invariant.
- The actual physical laser-mark/channel convention differs from canonical `A001 Channel 1` semantics.
- A non-disposable database is discovered. Stop all database mutation and request a separate preservation/import design.
