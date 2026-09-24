# React Phase 4 Readiness Review — Complete Frontend Cutover

**Status: ACCEPTED.** Phase 4 was executed and accepted on August 16, 2026; see
`docs/superpowers/plans/2026-08-14-react-phase-4.md` for the completion log and
`docs/react-migration.md` §5–§6 for the resulting architecture. The cutover is
complete: legacy GET URLs redirect (303) to their React equivalents, legacy
form-POST routes return 404/405, the Jinja templates and static JavaScript are
deleted, and the production wheel ships only React static-app assets (verified
by `tests/test_installed_wheel_smoke.py` from outside the source checkout).

> **Historical note.** Sections 1–10 below are the *pre-implementation readiness
> assessment* written on 2026-08-14, before Phase 4 was executed. They describe
> what Phase 4B–4D needed to do at the time and must be read as the original
> planning/inventory material, not as a statement of the current state. Where
> the assessment says work "remains", "is required", "must be added", or "is
> not yet done", that work was subsequently completed and accepted (see the
> plan completion log). The CSP, in particular, was finalized as
> `script-src 'self'; style-src 'self'` with no CDN allowance and no
> `'unsafe-inline'`; the shipped policy is authoritative over any § below.

## 1. Executive assessment (historical, 2026-08-14)

**Classification:** READY at review time.

Phase 3 delivered every React route that the legacy Jinja UI served: experiment
list/detail/builder, campaigns, materials, layer presets, baselines, device
layouts, users, fabrication-batch run sheet, result upload, and result
analysis/assignment. All five legacy static JavaScript files are fully replaced
by React components. Every legacy form-POST mutation has an existing JSON
`/api` equivalent — no API gaps were found. The production CSP planned for
`script-src 'self'`; no chart library is used.

The review conclusion was that the cutover was safe to proceed, with required
work: redirecting legacy GET URLs to their React equivalents, removing legacy
form-POST routes, deleting the 10 Jinja templates and 5 legacy JS files,
retiring legacy-dependent tests, tightening the CSP (removing the Bootstrap CDN
allowance and evaluating `style-src 'unsafe-inline'`), and extending the
installed-wheel smoke to prove legacy assets are absent. All of that work was
subsequently completed in Phases 4B–4D and accepted.

## 2. Findings (historical)

### Critical

**None.** No blocking contract gaps, no unresolvable redirect loops, no
security weakening required.

### Important

**I1. `LoginPage` does not read a `next` query string — legacy bookmarks break.**
- Reference: [frontend/src/pages/LoginPage.tsx:21-29](frontend/src/pages/LoginPage.tsx#L21) reads only `location.state.from` (React Router state); there is no `useSearchParams` / `next` query handling.
- Existing behavior: after React login, the user navigates to `from.pathname` (captured by `RequireAuth`) or defaults to `/` (→ `/app/`). A legacy bookmark `/login?next=/experiments/42` hits the legacy `templates/login.html` form, which the cutover removes.
- Why it matters: the fixed cutover decision requires `/login?next=...` to be sanitized, translated to an `/app/...` destination, and consumed by `LoginPage`. Without query-string `next` handling, a legacy bookmark loses its destination.
- Correction: Phase 4B adds a server-side redirect `/login?next=...` → 303 `/app/login?next=...` (sanitized via `safe_next_path`). `LoginPage` reads `next` as a fallback when `from` state is absent. The `next` value is an app-internal path WITHOUT the `/app` basename (e.g. `/experiments/42?tab=plan`), passed directly to `navigate()` (React Router's `BrowserRouter` already has `basename="/app"`, so it prepends `/app` automatically — the plan must NOT manually prefix with `/app` or it will produce `/app/app/...`). If the incoming value starts with `/app/`, normalize it by removing exactly one `/app` prefix before navigation. Reject protocol-relative paths (`//`), absolute URLs (`http://`/`https://`), `/api/*`, `/healthz`, export URLs, `/login`, and `/app/login`. Invalid or missing destinations fall back to `/` (→ `/app/`). External/protocol-relative targets are already rejected by `safe_next_path` ([src/web/auth.py:243-246](src/web/auth.py#L243)).
- Blocks: no (a UX gap, not a security gap).

**I2. Vite dev proxy does not forward non-API export download URLs.**
- Reference: [frontend/vite.config.ts:16](frontend/vite.config.ts#L16) — `PROXY_ROUTES = ["/api", "/login", "/logout", "/static", "/healthz"]`. The export routes (`/experiments/{id}/export.json|.pdf`, `/experiments/{id}/batches/{bid}/export.json|.pdf`) are NOT proxied.
- Existing behavior: in production, export URLs are FastAPI routes (same-origin GET, `Content-Disposition: attachment`). In dev (Vite origin `:5173`), these paths fall through to the Vite server (404/SPA) — export download links break in dev.
- Why it matters: the React app links to exports as plain `<a href>` / `window.location`; in dev these must reach the backend.
- Correction: Phase 4B adds a narrow regular-expression proxy rule covering exactly the four export download paths (`/experiments/{id}/export.json|.pdf`, `/experiments/{id}/batches/{bid}/export.json|.pdf`), and removes the obsolete `/login`, `/logout`, `/static` proxy entries.
- Blocks: no (dev-only).

**I3. `test_vite_proxy_smoke.py` does not exercise `/login`, `/logout`, or `/static` proxy routes.**
- Reference: [tests/test_vite_proxy_smoke.py](tests/test_vite_proxy_smoke.py) — all four tests hit `/api/...` and `/healthz` only.
- Why it matters: removing the obsolete proxy entries is safe for this test, but Phase 4B should add a smoke assertion that the export download proxy works if the proxy is extended.
- Correction: Phase 4B may extend the smoke; Phase 4D acceptance reruns it unchanged.
- Blocks: no.

**I4. `python-multipart` must NOT be removed.**
- Reference: [pyproject.toml:24](pyproject.toml#L24) — `python-multipart>=0.0.9,<1`.
- Why it matters: the React result-upload route (`POST /api/experiments/{id}/results`, multipart `FormData`) depends on it. Removing it would break result upload.
- Correction: retain `python-multipart`; only `jinja2` ([pyproject.toml:21](pyproject.toml#L21)) becomes removable after templates + `Jinja2Templates` are gone.
- Blocks: no.

**I5. `style-src 'unsafe-inline'` may still be required by React inline styles.**
- Reference: [src/web/middleware.py:75](src/web/middleware.py#L75) — `style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net`.
- Why it matters: React and the hand-written SVG charts may set inline styles (e.g. `style={{ fillOpacity: 0.18 }}`). Removing `'unsafe-inline'` could break chart rendering unless all inline styles are moved to CSS classes or the CSP uses a nonce/hash.
- Correction: Phase 4C removes the `https://cdn.jsdelivr.net` allowance (Bootstrap is gone). `'unsafe-inline'` removal is conditional: audit the React app + browser tests; remove only if proven unnecessary; otherwise retain with a documented justification.
- Blocks: no.

### Minor

**M1. `forms.py` becomes dead code — but has direct test consumers.** [src/web/forms.py](src/web/forms.py) is imported at runtime only by `routes.py:34-39` for the legacy `POST /experiments` form builder. Once that form route is removed, `forms.py` is dead at runtime. However, `tests/test_material_context.py:35,370+` and `tests/test_device_recipe.py:22,700+` import and test the form parsers directly. Phase 4C must explicitly migrate or retire those form-parser test cases before deleting `forms.py`. Preserve the non-form domain coverage in those test files; remove only tests that exclusively verify the retired HTML-form adapter, or replace them with API/domain tests where the behavior is still relevant.

**M2. `__Host-` cookie prefix differs between dev and prod.** In dev (`secure_cookies=False`) the CSRF cookie is `perovskite_csrf`; in prod it is `__Host-perovskite_csrf`. The React `csrfToken()` helper ([frontend/src/lib/api.ts:32-53](frontend/src/lib/api.ts#L32)) already reads both names. No change needed, but the cutover must not assume a single cookie name.

**M3. `test_session_api.py` has a `/static/` probe.** [tests/test_session_api.py:169-181](tests/test_session_api.py#L169) probes `/static/{file}` to confirm the legacy static dir serves. After `/static` is dropped, this probe must be deleted or rewritten to check `/app/assets` only.

## 3. Complete legacy route disposition table (historical planning map)

### Legacy GET routes (become 303 redirects to React; do not render Jinja)

| Legacy GET | Redirects to (303) | Line | Notes |
|---|---|---|---|
| `/` | `/app/` | routes.py:242 | Preserve `?` query if any |
| `/login` | `/app/login` (preserve `?next=...`) | auth_routes.py:42 | Sanitize `next` via `safe_next_path` |
| `/experiments` | `/app/experiments` | routes.py:249 | |
| `/experiments/new` | `/app/experiments/new` | routes.py:256 | |
| `/experiments/{id}` | `/app/experiments/{id}` | routes.py:343 | |
| `/experiments/{id}/upload` | `/app/experiments/{id}/upload` | routes.py:507 | |
| `/experiments/{id}/results/{file_id}/analysis` | `/app/results/{file_id}` | routes.py:580 | Note the path-structure change |
| `/experiments/{id}/batches/{batch_id}` | `/app/experiments/{id}/batches/{batch_id}` | routes.py:2667 | |
| `/campaigns` | `/app/campaigns` | routes.py:1592 | |
| `/materials` | `/app/materials` | routes.py:1680 | |
| `/admin/users` | `/app/users` | auth_routes.py:330 | |

### Legacy form-POST mutation routes (removed; JSON `/api` equivalent exists)

| Legacy POST | Removed; JSON equivalent | Line | Notes |
|---|---|---|---|
| `POST /login` | `POST /api/auth/login` | auth_routes.py:48 | |
| `POST /logout` | `POST /api/auth/logout` | auth_routes.py:92 | |
| `POST /experiments` | `POST /api/experiments` | routes.py:280 | `forms.py` becomes dead |
| `POST /experiments/{id}/substrate-exceptions` | `POST /api/conditions/{cid}/substrate-exceptions` | routes.py:396 | |
| `POST /experiments/{id}/substrate-exceptions/{eid}/decision` | `POST /api/substrate-exceptions/{eid}/decision` | routes.py:433 | |
| `POST /experiments/{id}/plan-status` | `PATCH /api/experiments/{id}/plan-status` | routes.py:475 | |
| `POST /experiments/{id}/results` | `POST /api/experiments/{id}/results` (multipart) | routes.py:527 | `python-multipart` retained |
| `POST /experiments/{id}/results/{file_id}/assignments` | `POST /api/results/{file_id}/assignments` | routes.py:608 | |
| `POST /experiments/{id}/fabrication-batches` | `POST /api/experiments/{id}/fabrication-batches` | routes.py:1933 | |
| `POST /campaigns` | `POST /api/campaigns` | routes.py:1599 | |
| `POST /campaigns/update` | `PATCH /api/campaigns/{code}` | routes.py:1632 | |
| `POST /materials` | `POST /api/materials` | routes.py:1687 | |
| `POST /materials/{id}/products` | `POST /api/materials/{id}/products` | routes.py:1720 | |
| `POST /materials/{id}/update` | `PATCH /api/materials/{id}` | routes.py:1751 | |
| `POST /material-products/{id}/update` | `PATCH /api/material-products/{id}` | routes.py:1789 | |
| `POST /admin/users` | `POST /api/users` | auth_routes.py:341 | |
| `POST /admin/users/{id}/access` | `PATCH /api/users/{id}` | auth_routes.py:384 | |
| `POST /admin/users/{id}/password` | `POST /api/users/{id}/password` | auth_routes.py:409 | |

**Gaps: none.** Every legacy form-POST has a JSON `/api` equivalent.

### Routes that must remain unchanged

| Route | Line | Status |
|---|---|---|
| `GET /api/*` (all) | routes.py / auth_routes.py | Unchanged — the permanent contract |
| `POST /api/*` (all mutations) | routes.py / auth_routes.py | Unchanged |
| `GET /healthz` | app.py:102 | Unchanged |
| `GET /app/assets/*` | app.py:148-154 | Unchanged (immutable cache) |
| `GET /app/` and `/app/{path}` (SPA fallback) | app.py:156-159 | Unchanged |
| `GET /experiments/{id}/export.json` | routes.py:353 | Unchanged (not redirected; active download) |
| `GET /experiments/{id}/export.pdf` | routes.py:374 | Unchanged |
| `GET /experiments/{id}/batches/{bid}/export.json` | routes.py:2728 | Unchanged |
| `GET /experiments/{id}/batches/{bid}/export.pdf` | routes.py:2761 | Unchanged |

## 4. Template and static-file dependency inventory (historical)

### Templates (10 files under `src/web/templates/`)

| File | React route | Covered? | Disposition |
|---|---|---|---|
| `login.html` | `/app/login` | Yes | DELETE (4C) |
| `index.html` | `/app/`, `/app/experiments` | Yes | DELETE (4C) |
| `experiment.html` | `/app/experiments/new`, `/app/experiments/{id}` | Yes | DELETE (4C) |
| `campaigns.html` | `/app/campaigns` | Yes | DELETE (4C) |
| `materials.html` | `/app/materials` | Yes | DELETE (4C) |
| `users.html` | `/app/users` | Yes | DELETE (4C) |
| `upload.html` | `/app/experiments/{id}/upload` | Yes | DELETE (4C) |
| `result_analysis.html` | `/app/results/{resultId}` | Yes | DELETE (4C) |
| `batch.html` | `/app/experiments/{id}/batches/{batchId}` | Yes | DELETE (4C) |
| `_navbar.html` | React `AppShell` | Yes | DELETE (4C) |

**No template behavior is uncovered by React.**

### Legacy static JS (5 files under `src/web/static/`)

| File | React replacement | Disposition |
|---|---|---|
| `experiment-builder.js` | `features/experiment-builder/` + `ExperimentBuilderPage` | DELETE (4C) |
| `batch-dashboard.js` | `SnapshotEditor` + `BatchDetailPage` | DELETE (4C) |
| `result-analysis.js` | `JvChart` + `BoxPlotChart` + `ResultDetailPage` | DELETE (4C) |
| `baseline-manager.js` | `BaselinesPage` + builder baseline loading | DELETE (4C) |
| `layer-reorder.js` | React state-based reorder in `LayerStackEditor` | DELETE (4C) |

### Dead code after removal

| Item | Line | Disposition |
|---|---|---|
| `Jinja2Templates` construction | routes.py:135 | DELETE (4C) |
| `_template_response` helper | routes.py:3202-3229 | DELETE (4C) |
| `_login_response` helper | auth_routes.py:436-466 | DELETE (4C) |
| `forms.py` (entire file) | src/web/forms.py | DELETE (4C) |
| `templates = Jinja2Templates(...)` + `TEMPLATE_DIR` | routes.py:123,135 | DELETE (4C) |
| `/static` mount | app.py:125 | DELETE (4C) |
| `/static` + `/app/assets` auth-bypass branch | middleware.py:36-41 | Modify: keep `/app/assets` bypass, remove `/static` |
| `templates/*.html` + `static/*.js` package-data | pyproject.toml:41-42 | DELETE (4C) |
| `jinja2` dependency | pyproject.toml:21 | DELETE (4C) — only if no remaining import |

## 5. Test dependency inventory (historical)

### Tests to DELETE (legacy-only, no replacement)

| Test | File:line | Reason |
|---|---|---|
| `LoginBrowserTests` (class) | test_browser_builder.py:39 | CSP false positive; legacy `/login` + dump-DOM |
| `ReactShellBrowserTests` (class) | test_browser_builder.py:315 | CSP false positive; inline-script harness blocked by `script-src 'self'`; `REACT_SHELL_OK` marker found in source, not executed |
| `ReactBuilderBrowserTests` (class) | test_browser_builder.py:444 | CSP false positive; inline-script harness blocked by `script-src 'self'`; `REACT_BUILDER_OK` marker found in source, not executed |
| `BatchDashboardBrowserTests` (class) | test_browser_builder.py:661 | CSP false positive; legacy batch.html + batch-dashboard.js |
| `test_registry_pages_and_builder_assets_are_served` | test_web_app.py:1062 | Asserts on legacy template/JS source text |
| `/static/` probe in `test_missing_spa_asset_is_not_cached_as_immutable` | test_session_api.py:169-181 | `/static` is removed |

### Tests to REWRITE (switch from form-POST/Jinja to JSON/React)

| Test / helper | File:line | Change |
|---|---|---|
| `login()` helper (form-POST `/login`) | test_auth_security.py:44, test_web_app.py:167, test_postgresql_integration.py:184,396 | → `/api/auth/login` JSON |
| `logout()` helper (form-POST `/logout`) | test_postgresql_integration.py:203,417 | → `POST /api/auth/logout` |
| `create_user()` helper (form-POST `/admin/users`) | test_auth_security.py:65 | → `POST /api/users` |
| `setUpClass` form-POSTs in browser tests | test_browser_results.py:160, test_browser_run_sheet.py:151 | → JSON API |
| `test_unauthenticated_html_redirects_and_api_rejects` | test_auth_security.py:102 | → assert `/app/login` redirect (not `/login`) |
| `test_student_campaign_directory_is_read_only` | test_auth_security.py:215 | → assert on `/api/campaigns` (not Jinja HTML) |
| `test_students_can_only_access_experiments_they_created` | test_auth_security.py:260 | → assert on `/api/experiments/{id}` (not HTML 200) |
| `test_material_directory_proposals_require_staff_review` | test_auth_security.py:417 | → assert on `/api/materials` (not HTML) |
| `test_guided_form_persists_*` (3 tests) | test_web_app.py:438,500,529 | → `POST /api/experiments` JSON |
| `test_standalone_plan_and_exports_use_exact_condition_snapshot` | test_web_app.py:570 | → `POST /api/experiments`; keep export GETs |
| `test_html_substrate_exception_and_plan_approval_workflow` | test_web_app.py:639 | → POST exception/decision/plan-status to API |
| `test_baseline_revision_is_linked_to_every_materialized_condition` | test_web_app.py:711 | → `POST /api/experiments` |
| `test_archived_baseline_revision_cannot_seed_a_new_plan` | test_web_app.py:778 | → `POST /api/experiments` + JSON `detail` |
| `test_campaign_dropdown_lists_only_instructor_created_campaigns` | test_web_app.py:846 | → assert on `/api/campaigns` |
| `test_builder_expands_database_layer_presets_into_a_keyed_map` | test_web_app.py:859 | → assert on `/api/layer-presets` JSON |
| `test_html_result_workflow_assigns_substrates_then_shows_statistics_and_curves` | test_web_app.py:982 | → POST results/assignments to `/api/...` |
| `test_role_scoped_http_workflow_uses_postgresql` | test_postgresql_integration.py:141 | → JSON login; assert on `/api/experiments/{id}` |
| `test_phase3_contracts_use_postgresql_schema` | test_postgresql_integration.py:332 | → JSON login/logout |
| `test_instructor_sees_baseline_save_control` + `can_manage_baselines` | test_web_app.py:1311 | → assert on React/API behavior |

### Tests to RETAIN (genuine, no legacy dependency)

- `test_session_api.py` (all, minus the `/static` probe)
- `test_vite_proxy_smoke.py` (all)
- `test_release_config.py` (all)
- `cdp_driver.py` (all — test infrastructure)
- `test_browser_results.py` (both tests — genuine CDP/React)
- `test_browser_run_sheet.py` (all 3 tests — genuine CDP/React)
- All DB-only `test_postgresql_integration.py` tests
- All API-only assertions in `test_auth_security.py` and `test_web_app.py` (the bulk of both files)

**Note:** `ReactShellBrowserTests` and `ReactBuilderBrowserTests` (test_browser_builder.py:315, 444) were previously listed here as real coverage. They are NOT — they use the same inline-`<script>` harness + `--dump-dom` marker pattern blocked by the production CSP. Their meaningful coverage (shell/role navigation, builder end-to-end, 320px overflow) must be replaced by real CDP suites in Phase 4C: shell/role navigation belongs in `tests/test_browser_cutover.py` (Phase 4B), and a new real CDP experiment-builder suite replaces `ReactBuilderBrowserTests`.

## 6. Authentication and redirect-loop analysis (historical)

**Login destination safety:**
- React `LoginPage` reads `location.state.from` (captured by `RequireAuth` on SPA-internal navigation) and navigates there after JSON login. If absent (direct navigation), defaults to `/` → `/app/`.
- After Phase 4B, `/login?next=...` redirects 303 to `/app/login?next=...` (sanitized). `LoginPage` reads `next` as a fallback when `from` state is absent. The `next` value is an app-internal path WITHOUT the `/app` basename (e.g. `/experiments/42`), passed directly to `navigate()` — `BrowserRouter` with `basename="/app"` prepends `/app` automatically. If the incoming value starts with `/app/`, one `/app` prefix is stripped before navigation. Reject protocol-relative paths, absolute URLs, `/api/*`, `/healthz`, export URLs, `/login`, and `/app/login`. Invalid or missing → `/` (→ `/app/`).

**Redirect-loop analysis (no loops possible):**
1. Unauthenticated `/` → 303 `/app/` → SPA `RequireAuth` → Navigate `/app/login` → `LoginPage` renders. **No loop.**
2. Unauthenticated `/login?next=...` → 303 `/app/login?next=...` → `LoginPage` renders. **No loop.**
3. Authenticated `/` → 303 `/app/` → `OverviewPage`. **No loop.**
4. Authenticated `/login` → 303 `/app/login` → `RequireAuth` passes → redirect to safe destination or `/app/` instead of showing the login form. **No loop.**
5. The SPA fallback `/app/{path}` only matches `/app/...`; it cannot redirect to `/login` or `/`. **No loop.**

**Session expiry (401) — current defect and Phase 4B correction:**
`apiFetch` calls `redirectToLogin()` ([frontend/src/lib/api.ts:74-78](frontend/src/lib/api.ts#L74)) which performs `window.location.assign("/app/login")`. This is a hard browser navigation that does NOT preserve React Router state, so `RequireAuth`'s `from` capture does NOT fire on a 401 from an API call. The current claim that `RequireAuth` preserves the attempted location after an API 401 is **false**.

Phase 4B must update `redirectToLogin()` to encode the current app route as a sanitized `next` query value: `window.location.assign("/app/login?next=" + encodeURIComponent(sanitizedCurrentPath))`. The `next` value is the app-internal path (without `/app` basename, with leading `/app/` stripped if present). `LoginPage` then reads `next` after login and navigates to the sanitized destination. This preserves the return-to-page behavior for session expiry.

**An already-authenticated user visiting `/app/login`:** Phase 4B must redirect an authenticated user away from `/app/login` to the safe destination (from `next` or `from` state) or `/app/`, instead of rendering the login form.

## 7. Export and Vite-proxy analysis (historical)

**Export routes (4):** `GET /experiments/{id}/export.json|.pdf` and `GET /experiments/{id}/batches/{bid}/export.json|.pdf`. These are NOT under `/api` and NOT under `/app`. They are active download contracts used by the React app as `<a href>` / `window.location` navigations. They must NOT be redirected, removed, or shadowed by the SPA fallback. The `/app/{path}` catch-all only matches `/app/...`, so it cannot shadow them. **No risk.**

**Vite dev proxy:** Currently proxies `/api`, `/login`, `/logout`, `/static`, `/healthz`. After cutover:
- **Keep:** `/api`, `/healthz`.
- **Remove:** `/login`, `/logout`, `/static` (obsolete).
- **Add:** a narrow regular-expression proxy rule covering exactly the four export download paths:
  - `/experiments/{integer_id}/export.json`
  - `/experiments/{integer_id}/export.pdf`
  - `/experiments/{integer_id}/batches/{integer_batch_id}/export.json`
  - `/experiments/{integer_id}/batches/{integer_batch_id}/export.pdf`

  The exact Vite configuration shape: add a `proxy` entry keyed by the regex
  `^/experiments/\\d+/export\\.(json|pdf)$` and
  `^/experiments/\\d+/batches/\\d+/export\\.(json|pdf)$` (two rules, or one combined
  regex), each with `changeOrigin: true` and the same `proxyReq` Origin-rewrite hook
  as the existing `/api` proxy. Do NOT proxy every `/experiments/*` request — React
  routes like `/app/experiments/...` must remain handled by Vite/React.

**Do NOT** route all `/experiments/*` to the SPA or shadow React routes — the export paths are specific and must be added narrowly.

## 8. Dependency, package-data, and CSP removal analysis (historical)

### Dependencies
| Dependency | pyproject.toml line | Removable? |
|---|---|---|
| `jinja2` | 21 | **Yes** (after templates + `Jinja2Templates` removed; no other consumer). Requires `uv lock` update to remove from `uv.lock` — distinguish direct dependency removal from transitive installation. |
| `python-multipart` | 24 | **No** (React result upload uses multipart `FormData`) |

**`uv.lock`:** Removing the direct `jinja2` dependency from `pyproject.toml` requires running `uv lock` and verifying `uv lock --check` so the lockfile no longer pulls Jinja2 as a direct entry. If another dependency legitimately requires it transitively, it may still appear in `uv.lock` — that is acceptable and must be documented.

### Package-data
| Entry | pyproject.toml line | Removable? |
|---|---|---|
| `templates/*.html` | 41 | **Yes** (4C) |
| `static/*.js` | 42 | **Yes** (4C) |
| `static-app/*.html` | 43 | **Keep** |
| `static-app/**/*` | 44 | **Keep** |
| `services/*.json` | 45 | **Keep** |

### CSP
| Directive | middleware.py line | Ship state |
|---|---|---|
| `script-src 'self'` | 74 | **Shipped unchanged** |
| `style-src 'self'` | 74 | **Shipped as `style-src 'self'`** — the `https://cdn.jsdelivr.net` allowance and `'unsafe-inline'` were both removed in Phase 4C after the React app and CDP browser suites proved no inline styles are needed |
| `frame-ancestors 'none'` | 73 | **Shipped unchanged** |
| `/static` auth-bypass branch | middleware.py:36-41 | **Removed in 4C**; only the `/app/assets` bypass remains |
| `/static` cache exception | middleware.py:77-80 | **Removed in 4C** |

The full shipped policy is `default-src 'self'; base-uri 'self'; connect-src
'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'; img-src
'self' data:; object-src 'none'; script-src 'self'; style-src 'self'` — no CDN
allowance, no `'unsafe-inline'`.

## 9. Risks and rollback considerations (historical)

**Risk: test rewrites are extensive.** ~20 tests across 4 files switch from form-POST/Jinja to JSON. A rewrite error could mask a regression. **Mitigation (implemented):** Phase 4B added the new redirect/auth tests first (TDD); Phase 4C rewrote tests incrementally with focused runs; Phase 4D ran the complete matrix.

**Risk: `style-src 'unsafe-inline'` removal breaks chart rendering.** The hand-written SVG charts use inline `style` attributes (`fillOpacity`, `strokeDasharray` via JSX). **Mitigation (implemented / outcome):** Phase 4C audited the React app and the CDP browser suites before removing `'unsafe-inline'`; the shipped policy is `style-src 'self'`, and all CDP suites subsequently passed against that policy, demonstrating no regression in chart or UI rendering.

**Risk: legacy bookmark with `?next=` loses destination.** **Mitigation:** Phase 4B adds `next` query handling to `LoginPage` + server-side `/login?next=...` → `/app/login?next=...` redirect.

**Rollback:** Phase 4B is reversible (revert redirect routes + `LoginPage` changes). Phase 4C deletions are irreversible per-file but the git working tree preserves the pre-deletion state; a `git checkout` of the deleted files restores them. No schema/migration changes mean no database rollback is needed.

## 10. Answers to the required review questions (historical)

1. **Exact legacy routes and their disposition:** see §3 (GET → 303 redirect; POST → removed; no gaps).
2. **Tests dependent on legacy:** see §5 (4 DELETE, ~20 REWRITE, bulk RETAIN).
3. **Old tests — rewrite/retain/delete:** see §5 classifications.
4. **React login preserves destinations safely:** yes, via `from` state + `next` query fallback (§6, I1).
5. **Redirect loops:** none possible (§6 analysis).
6. **Shadowing APIs/assets/health/exports:** no — the `/app/{path}` catch-all only matches `/app/...` (§7).
7. **Dead imports/helpers/deps after removal:** see §4 (Jinja2Templates, _template_response, forms.py, /static mount, jinja2 dep, package-data entries).
8. **Templates/JS still providing uncovered behavior:** none — all 10 templates and 5 JS files are fully replaced by React (§4).
9. **Real CDP browser tests prove post-cutover behavior:** `test_browser_run_sheet.py` + `test_browser_results.py` + the new `test_browser_builder_cdp.py` (Phase 4C) + `test_browser_cutover.py` (Phase 4B) all drive the production React bundle via `cdp_driver.py`. The retired `ReactShellBrowserTests` + `ReactBuilderBrowserTests` (CSP false positives) are replaced by real CDP suites. Phase 4D runs all four CDP suites in the acceptance matrix.
10. **Installed-wheel smoke proves canonical + retained behavior:** Phase 4D installs the wheel outside the source checkout, loads `/app/`, parses the hashed JS/CSS references from the entry document, requests each referenced asset (assert 200 + immutable cache headers — do NOT assert `GET /app/assets/` directory itself succeeds as it may 404), verifies legacy GETs redirect (303), `/api/session` 401, `/healthz` 200. For the export smoke: create an isolated test database and authenticated user, create a valid experiment through the JSON API, request its JSON/PDF export, and assert the attachment response is not redirected or shadowed (do NOT assume `/experiments/1/export.json` can return 200 in an empty unauthenticated installation). Assert `templates/` + `static/` are absent from the installed package.
