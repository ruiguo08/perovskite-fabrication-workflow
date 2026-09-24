# React Phase 4 Implementation Plan — Complete Frontend Cutover

**Status:** Completed and accepted 2026-08-16. Phases 4B, 4C, and 4D each
stopped for external review; the cutover is fully verified. Date: 2026-08-14.
Companion document: `docs/react-phase-4-readiness-review.md`.

Readiness classification: **READY.** Phase 3 delivered every React route; no API gaps
exist. This plan executes the cutover in three implementation phases (4B/4C/4D), each
using TDD and stopping for external review.

Ground rules: TDD for every route/auth change (write the failing test first); vitest for
React; unittest for Python; genuine CDP driver for browser tests (`tests/cdp_driver.py`);
no schema/migration changes; no CSP weakening; no feature flag or second active frontend;
every state-changing React request through `apiFetch` (CSRF automatic); English (United States)
for all project-file content.

## Phase 4B — Canonical routing, auth destinations, compatibility redirects, export/Vite-proxy protection

**Goal:** `/app/` becomes the canonical application; legacy GET URLs redirect to React;
`LoginPage` handles `next` query; export routes are protected; Vite proxy updated.
Legacy files are NOT deleted yet.

### 4B.1 — Legacy GET → React 303 redirects

- [x] **Add redirect routes** (`src/web/routes.py`, `src/web/auth_routes.py`)
  - Files modified: `src/web/routes.py`, `src/web/auth_routes.py`.
  - Interfaces consumed: `RedirectResponse`, `safe_next_path` ([auth.py:243-246](src/web/auth.py#L243)).
  - Interfaces produced: 303 redirects for every legacy GET in the readiness-review §3 table.
  - Replace each legacy GET handler (e.g. `GET /` at routes.py:242, `GET /experiments` at routes.py:249, `GET /experiments/{id}` at routes.py:343, etc.) with a `RedirectResponse(url=react_path, status_code=303)`. Preserve `?` query params where applicable.
  - `GET /login` at auth_routes.py:42 → 303 `/app/login` preserving `?next=...` (sanitized via `safe_next_path`).
  - `GET /experiments/{id}/results/{file_id}/analysis` → 303 `/app/results/{file_id}`.
  - Do NOT redirect export routes (`/experiments/{id}/export.json|.pdf`, `.../batches/{bid}/export.json|.pdf`).
  - Tests to add (`tests/test_phase4_redirects.py`, created here): each legacy GET returns 303 to the expected `/app/...` path; `?next=` on `/login` is sanitized (rejects `//evil.com`, accepts `/experiments/42`); export routes return 200/attachment (not 303); authenticated and unauthenticated cases.
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_phase4_redirects -v`.
  - Acceptance: all redirect tests pass; no Jinja template is rendered by any GET route.

### 4B.2 — LoginPage `next` query handling and 401 redirect correction

- [x] **Add `next` query-string fallback to LoginPage + fix 401 redirect** (`frontend/src/pages/LoginPage.tsx`, `frontend/src/lib/api.ts`)
  - Files modified: `frontend/src/pages/LoginPage.tsx`, `frontend/src/lib/api.ts`.
  - Interfaces consumed: `useSearchParams` (react-router-dom), existing `useSession().login`, `useSession()` for authenticated-redirect check.
  - Interfaces produced:
    - `LoginPage` reads `next` query param when `location.state.from` is absent. The `next` value is an app-internal path WITHOUT the `/app` basename (e.g. `/experiments/42?tab=plan`), passed directly to `navigate()` — `BrowserRouter` with `basename="/app"` prepends `/app` automatically. Do NOT manually prefix with `/app` or it will produce `/app/app/...`. If the incoming value starts with `/app/`, normalize by removing exactly one `/app` prefix before navigation. Preserve safe query strings and fragments.
    - Reject protocol-relative paths (`//`), absolute URLs (`http://`/`https://`), `/api/*`, `/healthz`, export URLs, `/login`, and `/app/login`. Invalid or missing destinations fall back to `/` (→ `/app/`).
    - `location.state.from` takes precedence over the `next` query parameter.
    - An already-authenticated user visiting `/app/login` is redirected to the safe destination (from `next` or `from` state) or `/app/` instead of seeing the login form.
    - `redirectToLogin()` in `api.ts` is updated to encode the current app route as a sanitized `next` query value: `window.location.assign("/app/login?next=" + encodeURIComponent(sanitizedCurrentPath))` where `sanitizedCurrentPath` is the app-internal path (without `/app` basename, with leading `/app/` stripped if present). This fixes the current defect where `window.location.assign("/app/login")` does not preserve React Router state on a 401.
  - Tests to add (`frontend/src/pages/LoginPage.test.tsx`):
    - Direct navigation to `/app/login?next=/experiments/42` → after login, navigates to `/experiments/42` (not `/app/app/experiments/42`).
    - `next=//evil.example` → rejects (falls back to `/` → `/app/`).
    - `from` state takes precedence over `next` query.
    - Session expiry on `/app/results/42?tab=curves` → `redirectToLogin()` encodes `next=/results/42?tab=curves` → login returns to `/app/results/42?tab=curves`.
    - No `/app/app/...` path is ever produced.
    - An already-authenticated user visiting `/app/login` is redirected to `/app/` (or the safe destination).
  - Commands: `corepack pnpm --dir frontend test`; `corepack pnpm --dir frontend typecheck`; `corepack pnpm --dir frontend lint`.
  - Acceptance: `next` query handling tests pass; 401-redirect tests pass; existing login tests still pass; no `/app/app/...` path produced.

### 4B.3 — Vite proxy update

- [x] **Update Vite dev proxy** (`frontend/vite.config.ts`)
  - Files modified: `frontend/vite.config.ts`.
  - Interfaces consumed: existing `apiProxy` config.
  - Interfaces produced: `PROXY_ROUTES` keeps `/api`, `/healthz`; removes `/login`, `/logout`, `/static`. Adds two narrow regular-expression proxy rules (using Vite's `proxy` config with `RegExp` keys):
    - `^/experiments/\\d+/export\\.(json|pdf)$` — proxies experiment JSON/PDF exports.
    - `^/experiments/\\d+/batches/\\d+/export\\.(json|pdf)$` — proxies fabrication-batch JSON/PDF exports.
    Each with `changeOrigin: true` and the same `proxyReq` Origin-rewrite hook as the existing `/api` proxy. Do NOT proxy every `/experiments/*` request.
  - Tests to add: extend `tests/test_vite_proxy_smoke.py` with one test that an export download URL (e.g. `/experiments/1/export.json`) reaches the backend through the Vite proxy (200 + `Content-Disposition: attachment`), AND one test that `/app/experiments/1` is NOT proxied (remains handled by Vite/React — assert the SPA HTML or a Vite-served response, not a backend attachment).
  - Commands: `$env:PEROVSKITE_VITE_SMOKE='1'; .venv\Scripts\python.exe -m unittest tests.test_vite_proxy_smoke -v`.
  - Acceptance: Vite smoke passes (4 + 2 new tests); dev export download links work; React routes not shadowed.

### 4B.4 — Browser redirect/role navigation tests

- [x] **Add genuine CDP browser tests for redirects and canonical login** (`tests/test_browser_cutover.py`, new)
  - Files created: `tests/test_browser_cutover.py`.
  - Interfaces consumed: `tests/cdp_driver.py` (launch_chrome_with_viewport, evaluate, wait_for_expression, click_center, get_cookies).
  - Tests to add: (a) legacy `/experiments` → 303 → React `/app/experiments` renders; (b) legacy `/login?next=/experiments/{id}` → 303 → `/app/login` → JSON login → navigates to `/app/experiments/{id}` (no `/app/app/...`); (c) `/` → 303 → `/app/`; (d) export download link works at 320px; (e) `/healthz` not shadowed; (f) session expiry on `/app/results/42?tab=curves` → `redirectToLogin()` encodes `next=/results/42?tab=curves` → login returns to `/app/results/42?tab=curves`; (g) an already-authenticated user visiting `/app/login` is redirected to `/app/` (or the safe `next` destination).
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_browser_cutover -v`.
  - Acceptance: cutover browser tests pass at 320px.

**Checkpoint 4B — passed (external review accepted).** Review: redirect correctness, `next` sanitization (no `/app/app/...`), 401-redirect encoding, authenticated-user redirect, export protection, Vite proxy. GLM runs `tests.test_phase4_redirects`, `tests.test_vite_proxy_smoke`, `tests.test_browser_cutover`, `corepack pnpm --dir frontend test`, `corepack pnpm --dir frontend typecheck`, `corepack pnpm --dir frontend lint`. (Legacy files were still in place at this checkpoint.)

## Phase 4C — Remove legacy routes, files, dependencies; tighten CSP; rebuild bundle

**Goal:** delete legacy form-POST routes, Jinja templates, static JS, dead code; rewrite/retire legacy-dependent tests; tighten CSP; rebuild the React bundle.

### 4C.1 — Remove legacy form-POST routes and dead code

- [x] **Delete form-POST routes** (`src/web/routes.py`, `src/web/auth_routes.py`, `src/web/forms.py`)
  - Files modified: `src/web/routes.py`, `src/web/auth_routes.py`.
  - Files deleted: `src/web/forms.py`.
  - Remove every form-POST in the readiness-review §3 table (POST `/login`, `/logout`, `/experiments`, `/experiments/{id}/substrate-exceptions`, `.../decision`, `.../plan-status`, `.../results`, `.../assignments`, `.../fabrication-batches`, `/campaigns`, `/campaigns/update`, `/materials`, `/materials/{id}/products`, `/materials/{id}/update`, `/material-products/{id}/update`, `/admin/users`, `/admin/users/{id}/access`, `/admin/users/{id}/password`).
  - Remove `Jinja2Templates` construction (routes.py:135), `_template_response` (routes.py:3202-3229), `_login_response` (auth_routes.py:436-466), `TEMPLATE_DIR` (routes.py:123), and the `from .forms import ...` (routes.py:34-39).
  - **`forms.py` has direct test consumers** ([tests/test_material_context.py:35,370+](tests/test_material_context.py#L35), [tests/test_device_recipe.py:22,700+](tests/test_device_recipe.py#L22)). Phase 4C.3 must migrate or retire those form-parser tests before `forms.py` can be deleted. If any form-parser test cases remain after 4C.3, `forms.py` deletion is deferred until they are resolved.
  - Tests to add: `tests/test_phase4_no_legacy_mutations.py` — assert each removed path returns 404/405; assert no `Jinja2Templates` import remains; assert `forms.py` is absent.
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_phase4_no_legacy_mutations -v`.
  - Acceptance: removed routes 404/405; no Jinja/forms imports.

### 4C.2 — Delete legacy templates and static JS

- [x] **Delete all files under `src/web/templates/` and `src/web/static/`**
  - Files deleted: `src/web/templates/*.html` (10 files), `src/web/static/*.js` (5 files).
  - Remove the `/static` mount (`app.py:125`).
  - Remove the `/static` auth-bypass branch in `middleware.py:36-41` (keep `/app/assets` bypass).
  - Remove the `/static` cache-exception branch in `middleware.py:77-80`.
  - Tests to add: `tests/test_phase4_legacy_absent.py` — assert `src/web/templates/` is empty/gone; assert `src/web/static/` is empty/gone; assert `GET /static/anything.js` returns 404; assert `/app/` serves the React entry and referenced hashed assets load (200 + immutable cache) — do NOT assert `GET /app/assets/` directory itself succeeds as it may 404.
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_phase4_legacy_absent -v`.
  - Acceptance: no legacy files; `/static` 404s; `/app/assets` works.

### 4C.3 — Rewrite/retire legacy-dependent tests

- [x] **Migrate tests** (`tests/test_auth_security.py`, `tests/test_web_app.py`, `tests/test_postgresql_integration.py`, `tests/test_session_api.py`, `tests/test_browser_builder.py`, `tests/test_browser_results.py`, `tests/test_browser_run_sheet.py`, `tests/test_material_context.py`, `tests/test_device_recipe.py`)
  - Files modified: the above test files.
  - DELETE: `LoginBrowserTests`, `ReactShellBrowserTests`, `ReactBuilderBrowserTests`, `BatchDashboardBrowserTests` (all four classes in test_browser_builder.py — all are CSP false positives using inline-`<script>` harnesses blocked by `script-src 'self'`); `test_registry_pages_and_builder_assets_are_served` (test_web_app.py); `/static/` probe (test_session_api.py:169-181).
  - REWRITE: every `login()`/`logout()`/`create_user()` helper → JSON `/api/auth/login` + `/api/auth/logout` + `/api/users`; every Jinja-HTML-text assertion → `/api` JSON or React DOM marker; every form-POST `/experiments` → `POST /api/experiments`; every form-POST mutation → its JSON equivalent. See readiness-review §5 for the full list.
  - **`tests/test_material_context.py` and `tests/test_device_recipe.py`**: these import and test the `forms.py` parsers directly (`recipe_from_form`, `condition_plans_from_form`, `_legacy_recipe_from_form`). Migrate or retire the form-parser test cases: preserve non-form domain coverage (recipe validation, condition-plan logic, material-context behavior that does not depend on the form adapter); remove only tests that exclusively verify the retired HTML-form adapter, or replace them with API/domain tests where the behavior is still relevant.
  - Tests to add: none new (the rewrites themselves are the regression).
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_auth_security tests.test_web_app tests.test_session_api tests.test_material_context tests.test_device_recipe -v`.
  - Acceptance: rewritten tests pass; no test depends on Jinja HTML, form-POST, or `/static`.

### 4C.4 — Remove dead dependencies and package-data; tighten CSP

- [x] **Update pyproject.toml, middleware.py, uv.lock** (`pyproject.toml`, `src/web/middleware.py`, `uv.lock`)
  - Files modified: `pyproject.toml`, `src/web/middleware.py`, `uv.lock`.
  - Remove `jinja2` from dependencies (pyproject.toml:21) — only if no remaining import. **Do NOT remove `python-multipart`** (pyproject.toml:24).
  - Run `uv lock` to update `uv.lock` after removing `jinja2` from `pyproject.toml`. Run `uv lock --check` to verify the lockfile is consistent. Distinguish direct dependency removal from transitive installation: if another dependency legitimately requires Jinja2 transitively, it may still appear in `uv.lock` — that is acceptable and must be documented. The final wheel/environment must not retain Jinja2 merely because of a stale lock entry.
  - Remove `templates/*.html` and `static/*.js` from package-data (pyproject.toml:41-42).
  - Remove `https://cdn.jsdelivr.net` from CSP `style-src` (middleware.py:75).
  - Audit `style-src 'unsafe-inline'`: if the React app + browser tests prove no inline styles, remove it; otherwise retain with a comment.
  - Tests to add: extend `tests/test_phase4_legacy_absent.py` — assert `jinja2` is not in `pyproject.toml` direct dependencies; assert CSP header no longer contains `cdn.jsdelivr.net`.
  - Commands: `uv lock`; `uv lock --check`; `.venv\Scripts\python.exe -m unittest tests.test_phase4_legacy_absent -v`.
  - Acceptance: no `jinja2` dep; no CDN in CSP; no legacy package-data.

### 4C.5 — Rebuild the React bundle

- [x] **Rebuild** (`frontend/`)
  - Commands: `corepack pnpm --dir frontend build`.
  - Acceptance: build succeeds; `src/web/static-app/index.html` + hashed assets updated.

### 4C.6 — Genuine CDP experiment-builder browser suite

- [x] **Create a genuine CDP experiment-builder browser suite** (`tests/test_browser_builder_cdp.py`, new)
  - Files created: `tests/test_browser_builder_cdp.py`.
  - Interfaces consumed: `tests/cdp_driver.py` (launch_chrome_with_viewport, evaluate, wait_for_expression, click_center, get_cookies, set_file_input).
  - Interfaces produced: a genuine CDP top-document browser suite that replaces the retired `ReactBuilderBrowserTests` false positive. The suite:
    - loads the production React bundle in the top document (no iframe, no inline harness);
    - logs in through the JSON authentication flow (`/api/auth/login`);
    - opens `/app/experiments/new`;
    - selects a baseline through the real React UI;
    - expands and edits the planned configuration (layer stack, conditions);
    - creates an experiment through the real React UI (submits to `/api/experiments`);
    - verifies navigation to the React experiment detail (`/app/experiments/{id}`);
    - verifies the saved record through the real backend API (`GET /api/experiments/{id}`);
    - checks 320px horizontal overflow at the builder and detail views;
    - fails on page exceptions, console errors, and failed mutating API requests.
  - Tests to add: one end-to-end test covering the full builder flow at 320px.
  - Commands: `.venv\Scripts\python.exe -m unittest tests.test_browser_builder_cdp -v`.
  - Acceptance: genuine CDP builder suite passes; no inline-harness dependency; 320px verified.

**Checkpoint 4C — passed (external review accepted).** Review: legacy routes/files/deps removed; tests rewritten; all four inline-harness classes retired; genuine CDP builder suite added; CSP tightened; bundle rebuilt. GLM runs `corepack pnpm --dir frontend test`, `corepack pnpm --dir frontend typecheck`, `corepack pnpm --dir frontend lint`, `corepack pnpm --dir frontend build`, `.venv\Scripts\python.exe -m unittest tests.test_phase4_no_legacy_mutations tests.test_phase4_legacy_absent tests.test_auth_security tests.test_web_app tests.test_session_api tests.test_material_context tests.test_device_recipe -v` (affected suites, not full discovery).

## Phase 4D — Complete acceptance matrix, installed-wheel verification, documentation, final audit

### 4D.1 — Full acceptance matrix

- [x] Run the complete matrix (all exit 0):
  - `corepack pnpm --dir frontend test`
  - `corepack pnpm --dir frontend typecheck`
  - `corepack pnpm --dir frontend lint`
  - `corepack pnpm --dir frontend build`
  - `.venv\Scripts\python.exe -m unittest discover -s tests -v`
  - `.venv\Scripts\python.exe -m unittest tests.test_browser_results tests.test_browser_run_sheet tests.test_browser_cutover tests.test_browser_builder_cdp -v`
  - `$env:PEROVSKITE_VITE_SMOKE='1'; .venv\Scripts\python.exe -m unittest tests.test_vite_proxy_smoke -v`
  - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Test-LocalPostgreSQL.ps1 -PostgreSQLOnly`
  - `uv build`

### 4D.2 — Wheel-content inspection

- [x] Inspect the newest wheel:
  - `.venv\Scripts\python.exe -m zipfile -l dist/*.whl` — assert `web/static-app/index.html`, hashed JS/CSS, `web/services/material_catalog_seed.json` present.
  - Assert NO `web/templates/*.html` and NO `web/static/*.js` entries.

### 4D.3 — Fresh-installed-wheel route/API/export smoke

- [x] Install the wheel into a temp venv and verify from outside the source
      checkout via `tests/test_installed_wheel_smoke.py`:
  - Load `/app/`; parse the hashed JS/CSS references from the entry document; request each referenced asset; assert 200 + immutable cache headers (do NOT assert `GET /app/assets/` directory itself succeeds).
  - Legacy GETs (`/`, `/experiments`, `/login?next=...`) return 303 to `/app/...` (not HTML).
  - `/api/session` 401; `/healthz` 200.
  - Removed form-POST routes (`POST /login`, `POST /experiments`) return 404/405.
  - `web/templates/` and `web/static/` are absent from the installed package.
  - **Export smoke:** create an isolated test database and authenticated user, create a valid experiment through the JSON API (or repository), request its JSON/PDF export, and assert the attachment response is not redirected or shadowed. Do NOT assume `/experiments/1/export.json` can return 200 in an empty unauthenticated installation.

### 4D.4 — Legacy-absence search

- [x] Search proving no runtime/template/static references remain:
  - `rg -n "Jinja2Templates|TemplateResponse|_template_response|_login_response|from .forms|templates/" src/web/` → no matches.
  - `rg -n "cdn.jsdelivr.net" src/web/` → no matches.
  - `rg -n "/static/" src/web/middleware.py` → no `/static` branch.

### 4D.5 — Documentation updates

- [x] Update documentation:
  - `docs/react-migration.md` — mark Phase 4 complete; update route table; remove "fallback" wording; update removal-criteria table.
  - `docs/react-phase-4-readiness-review.md` — mark accepted.
  - `docs/superpowers/plans/2026-08-14-react-phase-4.md` — mark checkpoints complete.
  - `DEPLOYMENT.md` — update route list; remove "legacy fallback" wording; extend wheel smoke.
  - `LOCAL_DEVELOPMENT_WINDOWS.md` — update Vite proxy; remove legacy-entry wording.
  - `README.md` — remove "legacy pages available" wording; update route list.
  - `ARCHITECTURE.md` — update if it references legacy templates.

### 4D.6 — git diff --check and consistency review

- [x] `git diff --check` exit 0.
- [x] Review the three Phase 4 documents for contradictory current-state wording.

**Checkpoint 4D — COMPLETE and accepted 2026-08-16.** One review gate occurred
during 4D: the PostgreSQL run failed because `test_postgresql_integration.py`
still asserted the legacy `GET /experiments/{id}` returned 404 for a non-owner,
while Phase 4B had made it a public 303 redirect. The stale three-line probe
was removed (the equivalent JSON-API 404 assertion already stood below it);
focused suites and the exact previously-failing command then passed. Phase 4D
also added `tests/test_installed_wheel_smoke.py` (fresh-installed-wheel smoke
from outside the source checkout), which passes. No Phase 5 or post-cutover
work is started.
