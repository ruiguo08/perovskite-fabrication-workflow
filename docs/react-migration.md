# React frontend migration design

Migration inventory, design, and implementation status for the Perovskite Solar
Cell Fabrication Workflow. This document is the reference for migrating the server-rendered
Jinja2/Bootstrap UI to a Vite-built React + TypeScript application served by the
existing FastAPI application.

Status: Phase 1 and Phase 2 were implemented and accepted on August 12, 2026.
Phase 3 (execution, results, and provenance) was implemented and accepted on
August 14, 2026. Phase 4 (complete frontend cutover) was completed and accepted
on August 16, 2026: the React application under `/app/` is the canonical
frontend, all legacy GET URLs return 303 redirects to their React equivalents,
the legacy Jinja templates, static JavaScript, and form-POST routes are
removed, and the production wheel ships only the React static-app assets. The
experiment records, detail view, complete experiment-planning workspace,
fabrication-batch run sheet, result upload, result analysis, and assignment
workflow are all served by React under `/app/`.

## 1. Current architecture summary

- FastAPI serves the React application from `src/web/static-app/` (the
  committed Vite build output) at `/app/`; `/app/assets/*` carries the hashed
  bundle with immutable cache headers, and `/app/{path}` falls back to the
  entry point for client-side routes. No Jinja templates, no Bootstrap CDN, and
  no legacy static JavaScript remain — the legacy `templates/`, `static/`, and
  `forms.py` were removed in Phase 4C.
- The full JSON API surface already exists under `/api/...` for experiments,
  conditions, baselines, layer presets, materials, campaigns, device layouts,
  fabrication batches, solution preparations, process executions, deviations,
  and result uploads. Bidirectional Pydantic models in `src/web/models.py`
  define the JSON contracts.
- Authentication is cookie-based (session + CSRF cookies), enforced by
  `src/web/auth.py` and `src/web/middleware.py`. State-changing requests require
  same-origin checks plus an `X-CSRF-Token` header or `csrf_token` form field.
- The legacy browser logic that previously lived in `src/web/static/` was
  ported to React and the files were deleted in Phase 4C: the experiment
  builder (layer/stack ordering, plan-type conversion, comparative target
  diffing, substrate catalog syncing) now lives in
  `frontend/src/features/experiment-builder/`; the batch dashboard
  orchestration in `frontend/src/pages/BatchDetailPage.tsx`; and the result
  analysis charts (box plots, J-V curves, statistics) in
  `frontend/src/components/JvChart.tsx` / `BoxPlotChart.tsx`, rendering
  server-computed statistics as hand-written SVG.
- The repository now contains a frontend build toolchain under `frontend/`:
  Vite + React + TypeScript (strict) built with `pnpm` (via corepack). The
  production build writes directly to `src/web/static-app/` and ships inside the
  Python wheel, so the production server needs no Node/pnpm at runtime. The
  production CSP (`script-src 'self'; style-src 'self'`) permits the
  self-hosted bundle; no chart library is used (charts are hand-written SVG).

Domain rules that must be preserved through the React port:

- Baselines and layer presets are input templates only. The experiment builder
  must expand a selected template into complete editable values and submit a
  complete `device_recipe`; the server rejects any create that contains only a
  reference (`repository.add_experiment` raises "a complete device_recipe is
  required; baselines and presets must be expanded before an experiment is
  saved").
- Saved experiments, conditions, batches, and exports must contain complete
  expanded snapshots, never template references.
- Server-side validation is authoritative. The React builder may show live
  hints but must not duplicate validation rules in a way that can diverge from
  the backend.
- Authorization is enforced by FastAPI. Frontend role gating is presentational
  only.

## 2. Route mapping

### 2.1 Legacy routes — final disposition (after Phase 4 cutover)

After Phase 4, no legacy HTML page exists. Every legacy GET URL returns a 303
redirect to its React equivalent (exactly one hop, no login round trip), every
legacy form-POST route returns 404/405 (its JSON `/api` equivalent is the
permanent contract), and the export download URLs remain unchanged as active
attachments. The removed form-POST routes were: `/login`, `/logout`,
`/experiments`, `/experiments/{id}/substrate-exceptions`,
`/experiments/{id}/substrate-exceptions/{eid}/decision`,
`/experiments/{id}/plan-status`, `/experiments/{id}/results`,
`/experiments/{id}/results/{file_id}/assignments`,
`/experiments/{id}/fabrication-batches`, `/campaigns`, `/campaigns/update`,
`/materials`, `/materials/{id}/products`, `/materials/{id}/update`,
`/material-products/{id}/update`, `/admin/users`, `/admin/users/{id}/access`,
`/admin/users/{id}/password`.

| Legacy GET (303 redirect) | Redirects to | JSON API dependencies |
| --- | --- | --- |
| `/login` (preserves `?next=...`, sanitized) | `/app/login` | `GET /api/auth/login-csrf`, `POST /api/auth/login`, `POST /api/auth/logout` |
| `/` | `/app/` | `GET /api/experiments` |
| `/experiments` | `/app/experiments` | `GET /api/experiments` |
| `/experiments/new` | `/app/experiments/new` | `GET /api/baselines`, `GET /api/layer-presets`, `GET /api/materials`, `GET /api/device-layouts`, `GET /api/campaigns` |
| `/experiments/{id}` | `/app/experiments/:experimentId` | `GET /api/experiments/{id}`, `.../conditions`, `.../substrate-exceptions`, `.../fabrication-batches`, `.../results` |
| `/experiments/{id}/upload` | `/app/experiments/:experimentId/upload` | `GET /api/experiments/{id}/fabrication-batches` |
| `/experiments/{id}/results/{file_id}/analysis` | `/app/results/:resultId` | `GET /api/results/{file_id}`, `GET /api/fabrication-batches/{id}/conditions`, `GET /api/results/{file_id}/assignments` |
| `/experiments/{id}/batches/{batch_id}` | `/app/experiments/:experimentId/batches/:batchId` | `GET /api/fabrication-batches/{batch_id}` aggregate run-sheet + per-entity reads |
| `/campaigns` | `/app/campaigns` | `GET/POST /api/campaigns`, `PATCH /api/campaigns/{code}` |
| `/materials` | `/app/materials` | `GET/POST /api/materials`, `PATCH /api/materials/{id}`, `.../products`, `PATCH /api/material-products/{product_id}` |
| `/admin/users` | `/app/users` (admin only) | `GET/POST /api/users`, `PATCH /api/users/{id}`, `POST /api/users/{id}/password` |

Export download routes are unchanged and never redirect: `/experiments/{id}/export.json|.pdf`
and `/experiments/{id}/batches/{batch_id}/export.json|.pdf`.

### 2.2 Existing JSON API surface (permanent contract)

| Endpoint | Used by React routes |
| --- | --- |
| `GET /api/experiments`, `POST /api/experiments` | Experiments list, experiment builder |
| `GET /api/experiments/{id}/conditions`, `POST`, `PUT /api/conditions/{condition_id}`, `DELETE` | Experiment builder, plan detail |
| `PATCH /api/experiments/{id}/plan-status` | Plan status control |
| `POST /api/conditions/{condition_id}/substrate-exceptions`, `POST /api/substrate-exceptions/{exception_id}/decision` | Exception workflow |
| `GET/POST/PUT/DELETE /api/baselines`, `GET /api/baselines/{id}/versions` | Baselines page, builder template expansion |
| `GET/POST/PUT/DELETE /api/layer-presets` | Layer presets page, builder template expansion |
| `GET/POST /api/materials`, `PATCH /api/materials/{id}`, `POST /api/materials/{id}/products`, `PATCH /api/material-products/{product_id}` | Materials page |
| `GET/POST /api/campaigns`, `PATCH /api/campaigns/{code}` | Campaigns page |
| `GET /api/device-layouts` | Builder, detail, results |
| `POST /api/experiments/{id}/fabrication-batches`, `GET /api/experiments/{id}/fabrication-batches` | Batch creation, experiment detail |
| `GET /api/fabrication-batches/{id}/run-sheet` (aggregate read) and `.../status`, `.../conditions`, `.../substrates`, `.../devices` | Batch run sheet — `BatchDetailPage` loads the aggregate `run-sheet` contract; the per-entity reads remain for targeted mutations |
| `GET/POST /api/fabrication-batches/{id}/solution-preparations`, `.../uses`, `.../split`, `.../merge`, `PATCH .../{preparation_id}` | Batch run sheet (mutations) |
| `GET/POST /api/fabrication-batches/{id}/process-executions`, `.../members`, `.../split`, `.../merge`, `PATCH .../{execution_id}` | Batch run sheet (mutations) |
| `GET/POST /api/fabrication-batches/{id}/deviations` | Batch run sheet, provenance |
| `POST /api/experiments/{id}/results` (multipart) | Result upload |
| `GET /experiments/{id}/export.{json,pdf}`, `GET /experiments/{id}/batches/{batch_id}/export.{json,pdf}` | Export actions |

## 3. JSON API migration status

The following operations were identified as JSON API gaps. Completed endpoints
reuse repository methods and FastAPI security dependencies; domain authorization
remains server-side.

### Phase 1 (session and shell)

Status: complete.

1. `GET /api/session` — current user id, display name, role, and CSRF
   availability. 401 when unauthenticated. Backed by `resolve_auth_context`.
2. `GET /api/auth/login-csrf` — mints a login CSRF token, sets the
   `login_csrf` cookie (same mechanism as the legacy `GET /login`), returns the
   token as JSON. Required so `POST /api/auth/login` can use the existing login
   CSRF check (`has_valid_login_csrf`).
3. `POST /api/auth/login` — accepts JSON credentials, validates the login CSRF
   token, calls `authenticate_credentials` + `issue_session`, sets the same
   session/CSRF cookies as the legacy form login. 401 on failure, 403 on
   expired login CSRF.
4. `POST /api/auth/logout` — requires normal CSRF protection, deletes the
   session, clears the same cookies (mirrors the legacy `/logout`).

### Phase 2 (experiment planning and library)

Status: complete.

5. `GET /api/experiments/{experiment_id}` — returns the authorized experiment,
   conditions, substrate exceptions, fabrication-batch summaries, and result
   summaries as one detail response.
6. `GET /api/experiments/{experiment_id}/substrate-exceptions` — list active
   pending/approved exceptions per condition (currently only rendered in the
   HTML detail template).
7. `GET /api/layer-presets/{preset_id}/versions` — returns immutable revision
   history after applying personal ownership and shared-preset visibility.
8. `GET /api/users`, `POST /api/users`, `PATCH /api/users/{user_id}`,
   `POST /api/users/{user_id}/password` — administrator user management,
   returned as JSON instead of HTML form posts. These endpoints are
   administrator-only and never return password hashes or lockout internals.

### Phase 3 (execution, results, provenance)

Status: complete and accepted August 14, 2026. Five required API gaps plus one
additional run-sheet aggregate contract were delivered:

9. `GET /api/results/{file_id}` — one result record including `metrics`,
   `analysis`, `sha256`, `group_assignment`, `created_by_id`, and timestamps.
10. `GET /api/results/{file_id}/assignments` — device assignment rows
    (`result_device_assignments` joined with fabrication device/substrate codes).
11. `POST /api/results/{file_id}/assignments` — save group assignments as JSON;
    the server runs `assign_substrates_to_groups` +
    `update_result_analysis_and_complete` and returns the complete
    `ResultDetailResponse` with recomputed statistics.
12. `GET /api/fabrication-batches` and `GET /api/results` — global, role-scoped
    lists (server-side filtering; bare arrays, no pagination; students see only
    their own experiments, instructors/administrators see all).
- Additional contract: `GET /api/fabrication-batches/{batch_id}/run-sheet` — the
  aggregated run-sheet read model (batch, frozen conditions, substrates, devices,
  preparations with uses, executions with members, deviations, and editor config).

React routes delivered: `/app/fabrication-batches`, `/app/results`,
`/app/experiments/:experimentId/batches/:batchId` (run sheet with preparation,
execution, split, merge, deviation, and status workflows),
`/app/experiments/:experimentId/upload`, and `/app/results/:resultId` (analysis,
assignment, JV curves, box plots, and export links). Statistics are
server-computed; the browser renders the returned `analysis.statistics` without
client-side quartile, mean, SD, p-value, or comparison computation. Chart
rendering uses hand-written SVG only (no chart library), preserving the
production CSP `script-src 'self'`.

### Explicitly not added

- Audit log read API. `audit_events` is write-only today (no repository list
  method). Per the project decision, the "Audit log" navigation item is not
  created because no backed API exists. Provenance uses record-level
  timestamps, actors, hashes, and deviations already exposed by the APIs above.
- No CSV import, no Bayesian optimization UI, no generic ELN notes, no
  material-lot tracking, no electronic signatures.

## 4. Role access matrix

Role rank: student < instructor < administrator. Server-side checks are the
security boundary; the React navigation hides items the role cannot use.

| Page / action | Student | Instructor | Administrator |
| --- | --- | --- | --- |
| Overview | own experiments, own batches, active materials | all experiments | all experiments |
| Experiments list/detail | own only (`created_by_id`) | all | all |
| Experiment builder | create from active saved baseline; own conditions | create, approve plans | create, approve plans |
| Plan status | own: draft → pending_approval / released / cancelled | + approve, release | + approve, release |
| Substrate exceptions | request on own draft plans | decide | decide |
| Fabrication batches | create for own released plans; record prep/execution/deviation; cannot cancel | create for any; cancel | create for any; cancel |
| Result upload / assignments | own experiments, in-progress or completed batch | all | all |
| Materials | view active + own pending; propose materials/products (pending) | publish, revise status, review | same |
| Layer presets | view active shared; create/revise/deactivate own personal presets | same personal controls; create/revise/deactivate shared presets | same as instructor |
| Baselines | view active only | create, see archived | create, revise (append), archive, see archived |
| Device layouts | view active | view | view |
| Campaigns | view active only | create/update/close/archive | same |
| Review queue | — | substrate exceptions + material review | same |
| Users | — | — | create, disable, role change, reset password |

Enforcement points already in the backend: `require_role`, `_student_owner_id`
in `routes.py`, `_batch_for_actor`, `_validate_plan_transition`, and
`create_fabrication_batch` ownership checks in `repository.py`. The React app
must not filter data client-side as a security mechanism; it only hides
navigation and disables actions.

## 5. Frontend build and deployment method

- New `frontend/` directory: Vite + React + TypeScript (strict), built with the
  existing `pnpm` toolchain. No external CDNs; production CSP is `script-src
  'self'; style-src 'self'` (both the `cdn.jsdelivr.net` allowance and
  `'unsafe-inline'` were removed in Phase 4C after the React app and browser
  suites proved no inline scripts or styles are needed).
- Development: `pnpm dev` runs the Vite dev server; the browser talks
  same-origin to the Vite origin and the Vite proxy forwards `/api`, `/healthz`,
  and the export download URLs to FastAPI so the CSP `connect-src 'self'`
  holds. The obsolete `/login`, `/logout`, and `/static` proxy entries were
  removed in Phase 4B.
- Production build: `vite build` writes directly to `src/web/static-app/`
  through the committed `frontend/vite.config.ts` `outDir`. Release method A
  (chosen): the built `src/web/static-app/` is committed to Git as reviewed
  release content and packaged with the Python wheel; the production server
  serves it from the installed package and needs no Node/pnpm toolchain. The
  existing deployment runs a Python environment from reviewed source on the
  server with no Node/pnpm installed, so the production artifact must travel
  inside the wheel. Method B (a dedicated build server with pinned Node/pnpm
  that runs the frontend build before `uv build`) is the fallback if committing
  built assets is later rejected.
- Wheel packaging: `pyproject.toml` includes the SPA entry file and every
  recursive asset so the wheel is self-contained —
  `[tool.setuptools.package-data] web = ["static-app/*.html",
  "static-app/**/*", "services/*.json"]`. The legacy `templates/*.html` and
  `static/*.js` package-data entries were removed in Phase 4C, and the
  installed wheel contains only React static-app assets.
- FastAPI serving (all new code in `app.py`):
  - The legacy GET routes return 303 redirects to their React equivalents and
    never render HTML (`_register_legacy_redirects`).
  - `/app/` and `/app/{path:path}` return the React entry point for safe SPA
    routes; `/app/assets/*` serves the hashed bundle with immutable cache
    headers.
  - `/api`, `/healthz`, and export routes keep their behavior and are never
    shadowed by the SPA fallback.
- Release flow (extends `DEPLOYMENT.md` section 1): on a machine with pnpm,
  run `pnpm install --frozen-lockfile` and `pnpm build` from `frontend/`; the
  build updates `src/web/static-app/` directly. Commit and review that output,
  then run `uv sync --locked --extra test --no-dev --no-editable` →
  `uv run --no-sync python -m unittest discover -s tests -v` → `uv build`.
  `LOCAL_DEVELOPMENT_WINDOWS.md` gains the pnpm prerequisite and the
  two-command local start (FastAPI + Vite dev).
- Phase 1 acceptance for the build path: build the wheel, install it into a
  clean temporary venv, and confirm `/app/` loads the SPA entry point and its
  hashed assets with no dependence on a source checkout or a Vite dev server.
  Phase 4 extended this to `tests/test_installed_wheel_smoke.py`, which
  exercises the installed wheel from outside the source checkout (React entry
  + immutable assets, 303 legacy GET redirects, `/api/session` 401, `/healthz`
  200, removed POST 404/405, no legacy assets installed, and JSON/PDF exports
  as attachments).
- The React application is the single active frontend: post-login root
  navigation points to `/app/` (Phase 4).

## 6. Removal criteria for legacy Jinja pages — completed

Phase 4 exercised the cutover gate below; all four criteria now hold and every
legacy template and static JavaScript file has been deleted.

1. A tested React route exists for it (list in section 2.1 is complete).
2. No test still asserts its legacy markup or template filename, and no test
   depends on an HTML-form 303 redirect that the React app no longer uses.
3. The JSON API it exercised is covered by SPA tests (per-role isolation,
   template expansion, batch execution, result upload, exports).
4. Exports and the JSON login flow still pass (the legacy form login no
   longer exists).

Final per-template disposition at Phase 4 cutover (all removed):

| Template | React equivalent | Remove when |
| --- | --- | --- |
| Template | React equivalent | Disposition (Phase 4 cutover) |
| --- | --- | --- |
| `login.html` | `/app/login` | Removed |
| `index.html` | `/app/`, `/app/experiments` | Removed |
| `experiment.html` | `/app/experiments/new`, `/app/experiments/:id` | Removed |
| `campaigns.html` | `/app/campaigns` | Removed |
| `materials.html` | `/app/materials` | Removed |
| `users.html` | `/app/users` | Removed |
| `upload.html` | `/app/experiments/:id/upload` | Removed |
| `result_analysis.html` | `/app/results/:resultId` | Removed |
| `batch.html` | `/app/experiments/:id/batches/:batchId` | Removed |
| `_navbar.html` | React app shell navigation | Removed |

No active Jinja UI remains. The old `static/` JavaScript files
(`experiment-builder.js`, `baseline-manager.js`, `batch-dashboard.js`,
`layer-reorder.js`, `result-analysis.js`) were removed together with their
templates in Phase 4C.

The tests that once asserted legacy markup (`test_web_app.py`, the retired
inline-harness classes in `test_browser_builder.py`, `test_material_context.py`
form-parser cases, and the HTML-text assertions across the suite) were migrated
to JSON API/React assertions in Phase 4C; no test depends on Jinja HTML,
form-POST, or `/static`.

## 7. Non-goals and constraints reaffirmed

- PostgreSQL, Alembic, FastAPI, export formats, and server-side validation are
  preserved.
- No reusable laboratory data is hardcoded in React: materials, products,
  baselines, layer presets, and device layouts always come from the catalog
  APIs. The server-side `LAYER_PRESETS`/`BUILTIN_BASELINE_SEEDS` structures in
  `perovskite_bo.device_recipe` remain the definition of the seeded templates
  (the preset catalog values now load from `perovskite_bo/data/layer_presets.json`,
  not from Python literals); they are not frontend data.
- Experiments/conditions/batches/exports always store expanded snapshots.
- CSRF (`X-CSRF-Token` from the `perovskite_csrf` cookie or `__Host-` variant),
  cookie security, same-origin checks, audit events, and backend validation are
  never weakened.
- All repository file content is US English.
