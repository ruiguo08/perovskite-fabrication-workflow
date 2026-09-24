# React Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the experiment-planning and reusable-library Jinja pages with complete, role-aware React routes while preserving expanded, independently reconstructible experiment snapshots.

**Architecture:** FastAPI remains the security and validation boundary and exposes the few missing JSON read/write contracts. React consumes those contracts through focused page modules and a pure experiment-builder state layer; selecting a baseline or layer preset deep-copies its complete snapshot into editable state before any save. Legacy Jinja routes remain available until every Phase 2 React route passes unit, API, and browser acceptance tests.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, SQLAlchemy 2 async, PostgreSQL/Alembic, React 19, TypeScript strict, React Router 7, Vite 6, Vitest, Testing Library, vanilla CSS.

**Status:** Complete and accepted on August 12, 2026. All checklist steps below
were implemented; legacy Jinja routes remain intentionally available until the
Phase 4 cutover.

## Global Constraints

- All project-file content must use English (United States).
- Baselines and layer presets are input templates only; saved experiments and conditions contain complete expanded parameters and immutable version snapshots.
- Students can create, revise, and deactivate only their own personal layer presets; personal presets are isolated by owner.
- Shared presets and reusable materials are PostgreSQL catalog records, not frontend constants.
- Students see only their own experiments, active Campaigns, active shared presets, and active materials plus their own pending material proposals.
- FastAPI authorization and validation remain authoritative; React role checks are presentational.
- State-changing requests retain same-origin and CSRF enforcement.
- No audit-log page, CSV import, Bayesian optimization UI, material-lot tracking, or Phase 3 execution/result pages.
- Do not remove a legacy Jinja route until its React replacement satisfies the removal criteria in `docs/react-migration.md`.
- Do not create commits unless the user explicitly requests them.

---

### Task 1: Complete Phase 2 JSON API contracts

**Files:**
- Modify: `src/web/models.py`
- Modify: `src/web/repository.py`
- Modify: `src/web/routes.py`
- Modify: `src/web/auth_routes.py`
- Create: `tests/test_phase2_api.py`

**Interfaces:**
- Produces: `GET /api/experiments/{experiment_id}` returning `ExperimentDetailResponse`.
- Produces: `GET /api/experiments/{experiment_id}/substrate-exceptions` returning `list[SubstrateExceptionResponse]`.
- Produces: `GET /api/layer-presets/{preset_id}/versions` returning immutable revisions visible to the actor.
- Produces: administrator-only `GET/POST /api/users`, `PATCH /api/users/{user_id}`, and `POST /api/users/{user_id}/password`.

- [x] **Step 1: Write API authorization and response tests**

  Cover administrator success, instructor/student 403 for `/api/users`, student ownership 404 for another student's experiment, experiment detail composition, exception listing, personal-preset history isolation, and active/inactive shared-preset history visibility.

  ```python
  def test_student_cannot_read_another_students_experiment_detail(self) -> None:
      response = self.student_client.get(f"/api/experiments/{other_experiment_id}")
      self.assertEqual(response.status_code, 404)

  def test_layer_preset_versions_are_immutable_and_owner_scoped(self) -> None:
      response = self.owner_client.get(f"/api/layer-presets/{preset_id}/versions")
      self.assertEqual([row["revision_number"] for row in response.json()], [1, 2])
      self.assertEqual(self.other_client.get(url).status_code, 404)
  ```

- [x] **Step 2: Run the new API tests and confirm missing routes/models fail**

  Run: `.venv\Scripts\python.exe -m unittest tests.test_phase2_api -v`

- [x] **Step 3: Add strict Pydantic contracts**

  ```python
  class UserCreatePayload(ApiModel):
      username: str = Field(..., min_length=1, max_length=64)
      display_name: str = Field(..., min_length=1, max_length=160)
      password: str = Field(..., min_length=1, max_length=128)
      role: Literal["student", "instructor", "administrator"]

  class UserUpdatePayload(ApiModel):
      role: Literal["student", "instructor", "administrator"]
      is_active: bool

  class UserPasswordResetPayload(ApiModel):
      password: str = Field(..., min_length=1, max_length=128)
  ```

  `ExperimentDetailResponse` contains `experiment`, `conditions`, `substrate_exceptions`, `fabrication_batches`, and `results`; nested records reuse existing response models.

- [x] **Step 4: Add repository preset-version listing with actor visibility**

  Implement `list_layer_preset_versions(preset_id: int, *, actor_user_id: int) -> list[dict[str, Any]]`. First resolve the preset through actor-scoped visibility, then return revisions ordered by `revision_number`; never expose another user's personal preset.

- [x] **Step 5: Implement JSON routes by reusing existing repository and auth helpers**

  Use `_get_record_or_404`, `_student_owner_id`, `_condition_response`, `_substrate_exception_response`, `_fabrication_batch_response`, `normalize_username`, `hash_password`, `require_csrf`, and `require_role`. Preserve existing status semantics: 201 create, 200 reads/updates, 204 password reset, 400 invalid state, 403 wrong role, 404 inaccessible resource, and 409 duplicate username.

- [x] **Step 6: Run targeted and OpenAPI tests**

  Run: `.venv\Scripts\python.exe -m unittest tests.test_phase2_api tests.test_session_api -v`

---

### Task 2: Establish shared TypeScript domain contracts and page state

**Files:**
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/lib/useApiResource.ts`
- Create: `frontend/src/lib/useApiResource.test.tsx`
- Create: `frontend/src/components/InlineFormError.tsx`
- Modify: `frontend/src/components/DataTable.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: strict API types used by every Phase 2 page.
- Produces: `useApiResource<T>(loader: () => Promise<T>)` with explicit loading, error, data, and reload states.

- [x] **Step 1: Write hook tests for loading, success, retry, and stale-result suppression**

  ```tsx
  const { result } = renderHook(() => useApiResource(load));
  expect(result.current.status).toBe("loading");
  await waitFor(() => expect(result.current.status).toBe("success"));
  expect(result.current.data).toEqual(rows);
  ```

- [x] **Step 2: Run Vitest and confirm the missing hook fails**

  Run: `corepack pnpm test -- src/lib/useApiResource.test.tsx`

- [x] **Step 3: Define API contracts without `any`**

  Include `Experiment`, `ExperimentDetail`, `Condition`, `SubstrateException`, `Baseline`, `BaselineVersion`, `LayerPreset`, `LayerPresetVersion`, `Material`, `MaterialProduct`, `Campaign`, `DeviceLayout`, and `UserAccount`. Preserve snake_case field names to match FastAPI exactly.

- [x] **Step 4: Implement reusable async and inline-error components**

  The hook ignores late responses after unmount/reload. `InlineFormError` uses `role="alert"`; table actions remain keyboard reachable and do not put buttons inside links.

- [x] **Step 5: Run typecheck, lint, and focused tests**

  Run: `corepack pnpm typecheck`, `corepack pnpm lint`, and `corepack pnpm test -- src/lib/useApiResource.test.tsx`.

---

### Task 3: Migrate Campaigns and device-layout directories

**Files:**
- Create: `frontend/src/pages/CampaignsPage.tsx`
- Create: `frontend/src/pages/CampaignsPage.test.tsx`
- Create: `frontend/src/pages/DeviceLayoutsPage.tsx`
- Create: `frontend/src/pages/DeviceLayoutsPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `Campaign`, `DeviceLayout`, `apiFetch`, `useSession`, `useApiResource`.
- Produces: `/app/campaigns` and `/app/device-layouts`.

- [x] **Step 1: Write role-aware page tests**

  Assert students get a read-only active Campaign table, instructors can create/update status, API errors remain inline, and device dimensions/areas render with units and tabular numbers.

- [x] **Step 2: Run focused tests and confirm placeholder routes fail**

  Run: `corepack pnpm test -- src/pages/CampaignsPage.test.tsx src/pages/DeviceLayoutsPage.test.tsx`

- [x] **Step 3: Implement Campaign directory**

  Use one compact management panel for instructor/administrator actions and a semantic table for all users. Do not duplicate server status-transition logic; submit the selected status and render the returned record.

- [x] **Step 4: Implement device-layout reference page**

  Present substrate footprint, devices per substrate, active area per device, and total active area. The page is read-only because layouts are versioned catalog data with no write API.

- [x] **Step 5: Switch navigation to React routes and verify**

  Replace legacy/disabled entries with `path` entries and run the two page tests, typecheck, and lint.

---

### Task 4: Migrate the shared material directory

**Files:**
- Create: `frontend/src/pages/MaterialsPage.tsx`
- Create: `frontend/src/pages/MaterialsPage.test.tsx`
- Create: `frontend/src/components/JsonObjectField.tsx`
- Create: `frontend/src/components/JsonObjectField.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: material create/update/product endpoints and role from `useSession`.
- Produces: `/app/materials` with proposal and review workflows.

- [x] **Step 1: Test all three role surfaces**

  Students can view active rows, submit pending materials/products, and see only their own pending proposals. Instructors/administrators can publish, edit, or deactivate records. Tests assert no manager controls appear for students.

- [x] **Step 2: Test JSON specification editing**

  `JsonObjectField` accepts a JSON object, rejects arrays/scalars with an inline message, and emits the parsed object only when valid.

- [x] **Step 3: Implement grouped material/product rows**

  Group by category, show formula/CAS/specification as secondary metadata, and nest supplier products under their material. Use inline expandable editing rather than a modal for every row.

- [x] **Step 4: Wire create, add-product, and manager update mutations**

  On success, replace the returned material in local state and announce through `Toast`. On failure, keep entered values and show the normalized FastAPI message next to the form.

- [x] **Step 5: Run page tests, typecheck, and lint**

---

### Task 5: Migrate layer-preset and baseline libraries

**Files:**
- Create: `frontend/src/pages/LayerPresetsPage.tsx`
- Create: `frontend/src/pages/LayerPresetsPage.test.tsx`
- Create: `frontend/src/pages/BaselinesPage.tsx`
- Create: `frontend/src/pages/BaselinesPage.test.tsx`
- Create: `frontend/src/components/RecipeSnapshotSummary.tsx`
- Create: `frontend/src/components/VersionHistory.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: baseline and layer-preset APIs including immutable histories.
- Produces: `/app/layer-presets` and `/app/baselines`.

- [x] **Step 1: Write ownership/version tests**

  Students can create/revise/deactivate personal presets and cannot mutate shared presets. Instructor/administrator shared-preset controls reflect backend permissions. Students see active baselines only; instructors can create; administrators can append revisions/archive. History renders revision, hash, actor, and timestamp.

- [x] **Step 2: Implement concise snapshot summaries**

  Show layer role/type/name, process method, solution ingredient count, substrate, full stack, and perovskite process stages without dumping raw JSON as the primary presentation. Provide a disclosure for canonical JSON when needed for audit.

- [x] **Step 3: Implement personal preset editing as full snapshot replacement**

  Forms always submit `name`, complete `layer`, optional complete `deposition_process`, and `scope`. Editing a revision never patches individual database fields.

- [x] **Step 4: Implement baseline management and immutable history**

  Every create/update submits a complete `device_recipe` and complete `deposition_process`. Archive uses DELETE and removes the item from a student's active view without changing previous experiment snapshots.

- [x] **Step 5: Run tests, typecheck, and lint**

---

### Task 6: Migrate administrator user management

**Files:**
- Create: `frontend/src/pages/UsersPage.tsx`
- Create: `frontend/src/pages/UsersPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 1 administrator user JSON endpoints.
- Produces: `/app/users`, protected by both `RequireRole` and FastAPI.

- [x] **Step 1: Test list/create/access/password behaviors**

  Assert password inputs are never rendered back, self-deactivation errors remain inline, disabled accounts are labeled in text, and non-admin API responses are 403 even if the React route is requested directly.

- [x] **Step 2: Implement account table and create form**

  Use explicit role and status controls. Password reset is a focused confirmation dialog with a new password field; clear the value immediately after the request finishes.

- [x] **Step 3: Wire route and navigation**

  Replace the legacy Users URL with `/app/users`; retain the administrator route guard.

- [x] **Step 4: Run frontend and API tests**

---

### Task 7: Migrate experiment list and detail

**Files:**
- Create: `frontend/src/pages/ExperimentsPage.tsx`
- Create: `frontend/src/pages/ExperimentsPage.test.tsx`
- Create: `frontend/src/pages/ExperimentDetailPage.tsx`
- Create: `frontend/src/pages/ExperimentDetailPage.test.tsx`
- Create: `frontend/src/components/ConditionCard.tsx`
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: experiment list/detail, plan-status, condition, exception, batch-summary, and export endpoints.
- Produces: `/app/experiments` and `/app/experiments/:experimentId`.

- [x] **Step 1: Test role-scoped list and deep-link detail**

  List rows link to React detail routes. Student fixtures contain only owned experiments. Detail renders condition hashes, layouts, counts, source baseline revisions, active exceptions, and full device/process snapshots.

- [x] **Step 2: Implement filters and status presentation**

  Filter locally only within already authorized API results. Support Campaign, plan status, and text search; default sort is most recently updated.

- [x] **Step 3: Implement plan actions and exception workflow**

  Present only role/state-appropriate actions, submit to the existing APIs, then reload the detail. Keep direct JSON/PDF export anchors as normal downloads.

- [x] **Step 4: Replace Overview's legacy link and route navigation**

  Use React `Link` for experiments and direct each recent row to its detail.

- [x] **Step 5: Run page/API tests, typecheck, and lint**

---

### Task 8: Extract and test the React experiment-builder domain state

**Files:**
- Create: `frontend/src/features/experiment-builder/types.ts`
- Create: `frontend/src/features/experiment-builder/state.ts`
- Create: `frontend/src/features/experiment-builder/state.test.ts`
- Create: `frontend/src/features/experiment-builder/validation.ts`
- Create: `frontend/src/features/experiment-builder/validation.test.ts`

**Interfaces:**
- Produces: `createBlankDraft`, `expandBaseline`, `expandLayerPreset`, `addLayer`, `replaceLayer`, `moveLayerWithinRole`, `removeLayer`, `setPlanType`, `materializeConditionPlans`, and `toExperimentPayload`.

- [x] **Step 1: Port behavior tests before implementation**

  Cover role order, duplicate restrictions, NiOx process variants, optional layers, perovskite process ownership, standalone/comparative conversion, target-copy independence, layout matching, and explicit condition plans.

- [x] **Step 2: Prove template expansion is a deep copy**

  ```ts
  const draft = expandBaseline(baseline);
  draft.device_recipe.layers[0].name = "Edited";
  expect(baseline.device_recipe.layers[0].name).not.toBe("Edited");
  expect(toExperimentPayload(draft).recipe.device_recipe.layers[0].name).toBe("Edited");
  ```

- [x] **Step 3: Implement pure immutable transitions**

  No function reads global catalog variables. Catalog records enter as explicit arguments. A selected preset's `preset_id` may remain provenance metadata inside the expanded layer, but all solution/process values are present in the payload.

- [x] **Step 4: Implement client guidance validation**

  Return structured field issues for missing required values but do not attempt to replace Pydantic validation. Server errors map back to the page-level summary when a field cannot be identified.

- [x] **Step 5: Run focused tests and typecheck**

---

### Task 9: Build the React experiment-planning workspace

**Files:**
- Create: `frontend/src/pages/ExperimentBuilderPage.tsx`
- Create: `frontend/src/pages/ExperimentBuilderPage.test.tsx`
- Create: `frontend/src/features/experiment-builder/StartingPointPanel.tsx`
- Create: `frontend/src/features/experiment-builder/SubstratePanel.tsx`
- Create: `frontend/src/features/experiment-builder/LayerStackEditor.tsx`
- Create: `frontend/src/features/experiment-builder/SolutionEditor.tsx`
- Create: `frontend/src/features/experiment-builder/ProcessEditor.tsx`
- Create: `frontend/src/features/experiment-builder/ConditionPlanner.tsx`
- Create: `frontend/src/features/experiment-builder/ReviewPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 8 state functions and catalog APIs.
- Produces: `/app/experiments/new` and a complete `POST /api/experiments` payload.

- [x] **Step 1: Test baseline requirement and catalog loading**

  Students cannot submit until they expand an active saved baseline. Instructor/administrator may start blank. All roles load Campaigns, baselines, layer presets, materials, and device layouts through APIs.

- [x] **Step 2: Build the left-to-right planning flow**

  Use a compact step rail: starting point, substrate/layout, layer stack, conditions, review. Keep the active editor beside a persistent device-stack rail on wide screens and stack it vertically at 720 px and below.

- [x] **Step 3: Implement complete layer editors**

  Support weighed solids/diluted dispersions; 1–4 spin stages; 1–5 VCD and gas-backfill stages with explicit sequence; 1–2 anneal stages; sputtering; thermal evaporation; and ALD. Material and vendor suggestions come only from the material API.

- [x] **Step 4: Implement comparative and standalone condition planning**

  Targets start as deep copies of control, remain independently editable, and submit explicit layout/substrate counts. Never submit adjustment text in place of a complete target snapshot.

- [x] **Step 5: Implement review and save**

  Review shows Campaign, baseline revision, substrate, ordered layers, complete process stages, condition counts/layouts, and validation issues. On 201, navigate to `/experiments/{id}`; on failure, preserve the draft.

- [x] **Step 6: Run builder tests, typecheck, lint, and production build**

---

### Task 10: Phase 2 browser, PostgreSQL, packaging, and documentation acceptance

**Files:**
- Modify: `tests/test_browser_builder.py`
- Modify: `tests/test_postgresql_integration.py`
- Modify: `docs/react-migration.md`
- Modify: `README.md`
- Modify: `DEPLOYMENT.md`
- Modify: `LOCAL_DEVELOPMENT_WINDOWS.md`
- Regenerate: `src/web/static-app/index.html`
- Regenerate: `src/web/static-app/assets/*`

**Interfaces:**
- Produces: reviewed Phase 2 production bundle while legacy Jinja remains available as fallback.

- [x] **Step 1: Add a real-browser React planning workflow**

  Authenticate, deep-link to `/app/experiments/new`, expand a baseline, edit at least one solution/process value, review, save, and land on React detail. Assert no page errors and no horizontal overflow at 320 px.

- [x] **Step 2: Add PostgreSQL role/isolation coverage for new APIs**

  Verify personal preset history isolation, user endpoint administrator-only access, and experiment detail ownership against migrated PostgreSQL.

- [x] **Step 3: Update migration status and operator documentation**

  Mark completed Phase 2 routes/API gaps accurately. Do not state that legacy pages are removed until the cutover phase.

- [x] **Step 4: Run final verification**

  ```powershell
  corepack pnpm test
  corepack pnpm lint
  corepack pnpm build
  .venv\Scripts\python.exe -m unittest discover -s tests -v
  $env:PEROVSKITE_VITE_SMOKE = "1"
  .venv\Scripts\python.exe -m unittest tests.test_vite_proxy_smoke -v
  .\scripts\Test-LocalPostgreSQL.ps1 -PostgreSQLOnly
  uv build
  git diff --check
  ```

- [x] **Step 5: Inspect the wheel resource list**

  Confirm the wheel contains `web/static-app/index.html`, every referenced hashed JS/CSS asset, and `web/services/material_catalog_seed.json`.

## Self-review

- Spec coverage: all Phase 2 API gaps and all Phase 2 planning/library routes in `docs/react-migration.md` map to a task.
- Template expansion: Tasks 8 and 9 explicitly deep-copy and persist complete snapshots.
- Role matrix: Tasks 1 and 3–7 cover server authorization and presentational controls for all three roles.
- Accessibility/responsiveness: Tasks 2–9 require semantic controls, inline errors, keyboard access, and the existing 320 px acceptance test.
- Deferred scope: Phase 3 batches/results and Phase 4 Jinja removal remain excluded.
- Placeholder scan: implementation steps specify concrete interfaces and acceptance behavior; no deferred implementation placeholders remain.
