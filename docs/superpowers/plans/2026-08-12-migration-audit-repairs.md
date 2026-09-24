# Migration Audit Repairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct all data-integrity, authorization, React, accessibility, proxy-test, packaging, and documentation findings from the Phase 0 and Phase 1 audit.

**Architecture:** PostgreSQL becomes the runtime source for shared and personal reusable layer presets, with one-time bootstrap seeds and composite version integrity. Backend and React behavior changes are protected by focused regression tests before implementation, while the legacy workflow remains available until cutover.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, PostgreSQL, SQLite, React 19, TypeScript, Vite, Vitest, Testing Library.

## Global Constraints

- All project-file content is written in English (United States).
- Templates are expanded into complete editable values and saved records never depend only on template references.
- Existing migrations `0007` through `0009` are immutable; schema corrections use migration `0010`.
- Student-owned presets remain isolated; shared presets are read-only to students.
- Existing dirty-worktree changes are preserved and no commit is created without explicit user direction.

---

### Task 1: Catalog schema and migration

**Files:**
- Create: `migrations/versions/0010_catalog_integrity.py`
- Modify: `src/web/database.py`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Produces `catalog_seed_versions`, `layer_presets.scope`, a composite current-version foreign key, and supporting indexes.

- [ ] Write migration graph and metadata tests for the new constraints.
- [ ] Run the tests and confirm they fail against the current `0009` head.
- [ ] Add migration `0010` and matching SQLAlchemy metadata.
- [ ] Run migration and schema-drift tests until they pass.

### Task 2: One-time seeds and shared layer presets

**Files:**
- Modify: `src/web/services/catalog_service.py`
- Modify: `src/web/app.py`
- Modify: `src/web/repository.py`
- Modify: `src/web/routes.py`
- Modify: `src/web/models.py`
- Test: `tests/test_auth_security.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- `seed_catalogs(connection)` applies each bootstrap version once.
- `GET /api/layer-presets` returns active shared presets plus the actor's personal presets.
- Layer-preset mutations authorize by scope and role.

- [ ] Add failing tests proving seeds do not recreate renamed/deleted rows and shared presets are visible but student read-only.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement seed markers, shared preset bootstrap, and scoped repository authorization.
- [ ] Run focused tests until they pass.

### Task 3: Material and substrate correctness

**Files:**
- Modify: `src/perovskite_bo/device_recipe.py`
- Modify: `src/web/repository.py`
- Modify: `src/web/routes.py`
- Modify: `src/web/templates/experiment.html`
- Modify: `src/web/static/experiment-builder.js`
- Test: `tests/test_auth_security.py`
- Test: `tests/test_device_recipe.py`
- Test: `tests/test_material_context.py`

**Interfaces:**
- Substrate names are bounded strings populated from active `substrate` materials and their active products.

- [ ] Add failing tests for inactive-parent write rejection and a database-defined substrate name.
- [ ] Run the focused tests and confirm failures without committed hidden products.
- [ ] Tighten product permissions and replace hard-coded substrate choices with API/catalog data.
- [ ] Run focused repository and builder tests until they pass.

### Task 4: React session, routing, and overview behavior

**Files:**
- Modify: `frontend/src/auth/session.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Create or modify focused tests under `frontend/src/`.

**Interfaces:**
- Logout returns before navigation.
- Session bootstrap exposes an error state for non-401 failures.
- Authentication redirects preserve the requested location.
- Role guards protect management routes.

- [ ] Add failing component tests for logout ordering, server errors, deep-link restoration, route roles, loading state, and recent ordering.
- [ ] Run Vitest and confirm each regression test fails for the intended behavior.
- [ ] Implement the minimal session, routing, and overview changes.
- [ ] Run Vitest, typecheck, and lint until they pass.

### Task 5: React accessibility and responsive shell

**Files:**
- Modify: `frontend/src/components/ConfirmDialog.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/index.html`
- Modify focused component tests.

**Interfaces:**
- Dialogs trap focus, restore focus, close on Escape, and use unique accessible IDs.
- The shell remains usable at 320 CSS pixels and exposes a skip link.

- [ ] Add failing accessibility and responsive contract tests.
- [ ] Implement dialog focus management, skip navigation, contrast, narrow layout, `spellCheck`, and `theme-color`.
- [ ] Run frontend tests and static checks until they pass.

### Task 6: Proxy, cache, package, and documentation verification

**Files:**
- Modify: `tests/test_vite_proxy_smoke.py`
- Modify: `tests/test_session_api.py`
- Modify: `src/web/middleware.py`
- Modify: `docs/react-migration.md`
- Modify: `DEPLOYMENT.md`

**Interfaces:**
- Opt-in live proxy tests initialize their database and close all resources.
- Only successful hashed asset responses are immutable.
- Release instructions match Vite's direct output directory and include an installed-wheel check.

- [ ] Add a failing cache-control test for missing assets and repair the live proxy fixture.
- [ ] Run all four opt-in Vite proxy tests.
- [ ] Update release documentation and installed-wheel verification naming/coverage.
- [ ] Run the full frontend, Python, PostgreSQL, build, and isolated-wheel verification matrix.
