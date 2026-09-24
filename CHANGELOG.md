# Changelog

All notable changes to this project are documented in this file. The format
follows Keep a Changelog; release versions follow the single source of truth
in `src/web/version.py`.

## Unreleased

### Added

- Layer presets can now be created from scratch: the layer presets page gains
  a "Create from scratch" form (layer type with its fixed device role,
  preset and layer names, scope for instructors) next to the snapshot-copy
  form, so the first reusable preset no longer depends on another preset
  already existing. Perovskite presets must record a complete deposition
  process before saving (the same gate as preset revisions); other layer
  types may leave the solution and process empty, exactly as the backend
  contract allows.
- Students' own still-pending chemical and solvent proposals are now offered
  by the solution editor's ingredient datalists, and pending gases by the
  sputtering and gas-backfill pickers, matching the substrate panel: pending
  records in a student's materials list are always their own proposals
  (scoped by `/api/materials`), so they are usable in a draft instead of
  invisible until activation.
- The overview page shows a first-use setup checklist while prerequisites
  for a first experiment are missing: staff get direct links to create the
  first device layout (administrator) and the first active campaign
  (instructor); students are told who to ask. The panel disappears once both
  exist.
- `perovskite-workflow-admin export-catalog` snapshots the catalog tables
  (device layouts, materials with supplier products, active layer presets,
  active baselines) as one versioned JSON document, and
  `perovskite-workflow-admin import-catalog <file> --actor <username>`
  re-creates them in another database through the same creation code paths
  (full validation, audit events, actor recorded). Import is idempotent —
  records that already exist (same layout (code, version), material
  (category, name), preset/baseline name in scope) are skipped and counted.
  This is the operator-controlled path for lifting a reviewed test database's
  catalog into production.
- Students can add conditions to a from-scratch experiment plan through
  `POST /api/experiments/{id}/conditions`: the leftover rule that required a
  saved baseline revision (inconsistent with from-scratch planning) is
  removed. `source_baseline_version_id` stays pure provenance.
- Device-layout creation (API and catalog import) writes a
  `device_layout.create` audit event with the acting user, matching every
  other catalog creation path.

### Fixed

- Windows test runs no longer hit intermittent `PermissionError` when the
  temporary SQLite file is removed: test teardowns now dispose the database
  engine before `TemporaryDirectory.cleanup()`, releasing the file handle
  Windows keeps open while pooled connections exist.
- `import-catalog` now goes through the same recipe validation as the
  baseline API (`validate_device_recipe` + `validate_deposition_process`
  + control-only stripping), so a hand-edited export document cannot inject
  an unvalidated snapshot into production.
- Catalog transfer semantics hardened after review: the export only includes
  active, shared-scope records (student-pending materials and personal
  presets/baselines stay in their database of origin — import would have
  silently activated or re-scoped them), and idempotency is pre-check based
  (SELECT before INSERT) instead of per-item constraint-violation recovery,
  which does not survive PostgreSQL's failed-transaction semantics.
  Re-importing into a database that already has a material but is missing
  its products now backfills them.
- The fixture scrub now covers the baseline-seed deposition processes too:
  24 seeds still carried the original VCD program (VV03/VV06 pressures) and
  3000-rpm spin cast; all are now the same synthetic placeholders as the
  reference process, completing the "no real laboratory setpoints in the
  repository" claim.
- Layer preset name inputs enforce the backend's 120-character limit (the
  forms previously allowed 160 and failed with a 422 on submit), the
  instructor promote-review section surfaces its load errors instead of
  silently disappearing, and the from-scratch perovskite preset path is now
  covered end-to-end by a happy-path test.

### Changed

- The factory shared layer-preset catalog no longer lives in Python code: its
  values moved to `perovskite_bo/data/layer_presets.json`. Bumping the file's
  `version` field makes the app roll changed presets out to deployed databases
  at next startup as new immutable revisions (created and validated through
  the same code path as user-created presets; within one catalog version,
  instructor edits from the UI are never overwritten).
- The factory catalogs are gone from runtime and shipped catalogs: the
  layer-preset JSON, the material seed JSON, the `LAYER_PRESETS` /
  `BUILTIN_BASELINE_SEEDS` Python constants, and all startup seeding are
  removed. Materials, layer presets, and baselines are user-authored records
  (students build them, instructors promote them to shared). The former
  factory values survive only as frozen test fixtures in
  `tests/recipe_fixtures.py` — no laboratory data ships in any installed
  package or served catalog. Every fabrication parameter in the fixtures has
  been replaced with obviously synthetic placeholders (round rpm numbers,
  the generic VV02 valve, 10 nm films, 5 mg solids, "Example solvent"), so
  the repository contains no real laboratory setpoints at all.

- Frozen conditions keep their exact layout version: condition edits,
  plan release, batch materialization, and extra substrates resolve the
  (code, version) recorded in each condition's frozen layout snapshot, so
  administrator catalog updates never retroactively change planned or
  released geometry. Brand-new conditions select the latest version.
  Layout creation returns the inserted (code, version) row, rejects decimals
  beyond the NUMERIC(10, 4) storage scale, and reports validation problems
  as 400 (duplicates stay 409). Promotion failures on promote-only preset
  cards are now visible.

- The device-layout catalog is now database-authoritative and
  administrator-managed: a new admin-only `POST /api/device-layouts` endpoint
  (plus a create form on the Device layouts page) replaces the factory JSON
  seed and the Python layout constants, which are removed. Experiment and
  condition creation resolve layout references against the database, so a
  fresh deployment starts with zero layouts and the administrator builds the
  catalog in place; students see an explicit empty state until then.

- Instructors can promote a student's personal layer preset to shared
  (one-way, audited, name-conflict checked) from a new "Student personal
  presets — promote to shared" review section on the layer presets page,
  mirroring the existing baseline promotion. Students planning an experiment
  can now also select their own still-pending material and supplier-product
  proposals, flagged "(pending review)", instead of waiting for activation.

- Students can plan an experiment entirely from scratch: a baseline
  reference is no longer mandatory (it was already provenance only — every
  experiment and condition stores its own complete, frozen recipe snapshot,
  and training-data export reads those snapshots, never the baseline). The
  starting-point panel now offers all roles the same three paths: expand a
  shared baseline, expand one of their own personal baselines, or plan from
  scratch; the baseline reference is an optional shortcut with an explicit
  empty state when no baseline exists yet.

- Layer stacks can now be authored entirely from scratch: the builder's
  Step 3 gains a "New blank layer" picker (layer type with its device role),
  next to the preset picker. Blank layers start with no solution and no
  process and are completed through "Edit complete layer values"; uniqueness
  and BCP/SnO2-exclusivity rules still apply. Presets remain an optional
  shortcut, so the first baseline no longer depends on any preset existing.

- The builders (baseline, experiment, preset editors) now fetch the
  authoritative VCD valve list from a new `GET /api/editor-config` endpoint
  instead of a hardcoded frontend copy, so a valve added on the backend is
  immediately selectable everywhere; the frontend list remains only as a
  loading fallback. Layer process editors show an inline "not complete yet"
  list for every layer type (not just perovskite), and incomplete layer cards
  carry a warning on their collapsed header pointing at "Edit complete layer
  values".
- The factory device-layout catalog also moved out of Python code into
  `web/services/device_layouts.json` (Decimal-exact values as strings). Startup
  now re-applies the layout file on every boot: appending an entry with an
  existing code and a bumped `version` rolls the new geometry out as a new
  immutable row, fixing the previous seed-once gate that prevented layout
  updates from ever reaching deployed databases.

### Fixed

- The factory shared Perovskite preset shipped with blank VCD valve names, so
  every baseline that copied it failed the "every VCD evacuation stage must be
  complete" review with no way to satisfy it. The seed data now carries real
  valves (VV03/VV06/VV06), deployments get an automatic correcting revision,
  and perovskite layer presets are rejected unless their deposition process is
  complete (backend API and preset editor alike). The perovskite process
  editor now lists exactly which stages are incomplete and shows blank valves
  as an explicit "- select a valve -" choice.

### Added

- Result analysis schema 5: each device now records the instrument-reported
  illumination (`irradiance_sun`, from the trace's "Int. (sun)" info row) and
  a PCE-based hysteresis index ((PCE_reverse - PCE_forward) / PCE_reverse,
  null when either direction is missing). Uploads whose reported illumination
  deviates from 1 sun by more than 0.05 produce analysis-level warnings,
  surfaced as an amber banner on the result detail page, because computed
  PCE assumes 1 sun (100 mW/cm2) and is never rescaled silently.
- Simple row-based JV CSVs may report total current instead of current
  density: such columns are converted with J = I / A using the batch's device
  layout area (resolved server-side from the frozen condition snapshots), and
  the conversion is recorded in the analysis as `unit_conversion` provenance.
  A total-current upload without a resolvable area is rejected with an
  explicit message. The previously conflated bare `current` and single-number
  `jsc` headers are no longer treated as current-density columns.
- Experiment records now derive `device_summary` (substrate material plus
  layer names) from the hash-verified control condition snapshot for list
  views.
- `perovskite-workflow-admin export-training-data` output is now
  self-describing: JSON exports lead with a header record declaring the
  export schema version, the feature/metric field lists, the unit of every
  feature and metric, and the measurement assumptions (1 sun / 100 mW/cm2
  AM1.5G, excluded-device filtering, None for absent recipe steps); CSV
  exports carry `export_schema_version` and `exported_at` columns. Aggregated
  condition metrics now include the median `hysteresis_index`.
- A transport-level request-body cap (`Content-Length` precheck, 12 MB)
  rejects oversized uploads from the header alone, before the multipart/JSON
  parsers buffer the body to temp disk. The reverse proxy
  (`request_body max_size`) remains the authoritative hard limit; this closes
  the direct-uvicorn exposure.


- Device exclusions on the result analysis page: dead or shorted devices can
  be flagged with a reason (a one-click preset applies the common Voc < 0.7 V,
  PCE < 10%, FF < 60% rule) and saving the assignments recomputes group
  statistics and comparisons without them. Exclusion never deletes data — the
  device keeps its traces, metrics, and assignment, the flag rides in the
  analysis JSON, and each save's audit event records the excluded count.
  Excluded devices are marked in the device tables and skipped by the box
  plots and the J-V overlay.
- Box plots can split every condition into forward/reverse scan boxes
  (computed from trace-level metrics), matching the F/R comparison the lab
  uses to judge hysteresis.
- Result analysis schema 4: the parser now preserves each instrument trace
  block's info rows verbatim and captures the instrument software's own
  summary metrics (Voc, Jsc, FF, PCE/Eff) alongside the computed metrics.
  Percentage FF values are normalized to the stored 0-1 fraction, and the
  result detail page shows an "Instrument vs computed metrics" table that
  highlights differences beyond tolerance (Voc 0.02 V, Jsc 1 mA cm⁻², FF
  2 points, PCE 0.3 points).
- J-V comparison overlay on the result detail page: all assigned devices'
  curves in one coordinate system, colored by condition group (forward solid,
  reverse dashed), with best-per-group selection, per-group visibility
  toggles, and a 24-curve cap.
- Chart export as SVG, PNG, and TIFF directly from the result page. PNG
  carries a pHYs chunk and TIFF carries inch resolution tags, both at the
  requested DPI (300 default), so exported figures meet common journal
  requirements without external tools.

- `perovskite-workflow-admin export-training-data`: read-only (X, y)
  extraction from the registry — one row per frozen condition of each
  completed batch, combining BO search-space recipe features, aggregated
  device metrics, and batch provenance (JSON lines or CSV). Backed by the
  new `WebRepository.build_training_dataset` wired onto
  `perovskite_bo.web_adapter`.

- Administration maintenance subcommands for `perovskite-workflow-admin`:
  `cleanup-sessions` (scheduled daily by a hardened systemd timer),
  read-only `export-audit` (JSON lines or CSV with `--since`, `--until`,
  `--actor`, `--action`, and `--limit` filters), and `status` monitoring
  counters. `DEPLOYMENT.md` documents the timer installation.
- Root React `ErrorBoundary`: a rendering crash now shows a recovery state
  with a reload action instead of unmounting to a blank page.

- Self-hosted IBM Plex Sans/Mono (woff2, SIL OFL 1.1) behind the existing
  `--font-ui`/`--font-mono` declarations: the console now renders in its
  intended brand typeface instead of the `system-ui` fallback. Data tables
  and stat tiles use tabular numerals.

- Data tables show a skeleton while their first load is in flight instead
  of flashing "No records." (pages wired to `useApiResource`). Error toasts
  stay on screen until dismissed (others still auto-hide after 5s), all
  toasts pause their timer on hover, and error toasts announce as
  `role="alert"`. The dashboard empty state carries a direct
  "Plan an experiment" call to action.

- Wide screens: main content is centered next to the sidebar instead of
  hugging the left edge. Bench guardrail: full-size run-sheet controls
  keep a ≥40px touch target.

### Changed

- Frontend styles are normalized onto the design-token system: a six-step
  type scale replaces 13 ad-hoc font sizes, spacing declarations use the
  8px-grid tokens, ~15 off-palette one-off colors are absorbed into palette
  tokens (including per-tone badge borders), and one-off shadows map to the
  elevation scale. The mobile step-rail `font-size: 0` label hack is
  replaced by a dedicated label span. Visual intent is unchanged apart from
  ±1–2px snapping to the grid. Audit and roadmap: `docs/ui-design-review.md`.

- `styles.css` is split into cascade-ordered modules under
  `frontend/src/styles/` (tokens / base / screens / run-sheet), and the
  run-sheet page is decomposed into `pages/batch-detail/` section
  components (preparations, executions, deviations, recording control,
  helpers). Both are pure moves: the compiled CSS is byte-identical and
  behavior is guarded by the existing page tests and browser suites.

### Fixed

- `create_condition` no longer resets the plan status to draft
  unconditionally: a plan already advanced to pending-approval or approved
  by a concurrent release keeps its status (the released-or-closed guard
  only blocks post-release statuses). The unconditional reset downgraded a
  pending-approval plan mid-release, failing the release's next transition
  — caught by the PostgreSQL race test on the post-merge main CI run.
  Updates and deletes still return the plan to draft: they change the
  approved content itself, so the approval no longer holds and the plan
  must pass the gate again (exactly one of edit/release commits).
- Training-data export no longer leaks excluded devices: `build_training_dataset`
  skips devices flagged `excluded` (with their recorded reason), matching the
  statistics/charts behavior, and every export row carries
  `excluded_device_count` so the filtered volume stays visible.
- Voc is now taken from the highest-voltage J = 0 crossing. The previous
  first-crossing rule understated Voc on S-kink or shunt-affected curves and
  truncated the power-quadrant search (corrupting FF and PCE).
- Scan direction is detected from the measured voltage sweep instead of trace
  block parity. Multiplexed instruments that sweep all channels forward then
  all reverse were mislabeled F/F/R/R, fabricating a hysteresis signal in the
  overlay chart and F/R box-plot split. Explicit Forward/Reverse labels still
  win.
- The legacy `experiments.recipe` JSON blob is removed (migration 0015). It
  was written only at experiment creation and never resynced on condition
  edits, so exports and legacy readers could see a recipe that no longer
  matched the hash-verified condition snapshots; `ExperimentRecord.recipe` is
  now derived from the control/standalone condition snapshot at read time.
  The downgrade re-adds the column as nullable (schema rollback only, no
  fabricated values), and list reads exclude pre-conditions legacy rows that
  have no condition snapshot to reconstruct from.
- `create_condition` now locks the parent experiment row (`FOR UPDATE`),
  closing a race where a condition creation racing a plan release could
  downgrade a released plan back to draft or violate a frozen batch hash.
- The result upload endpoint maps parser anomalies (`csv.Error`, `KeyError`,
  `IndexError`) from malformed files to a 400 response instead of a 500.
- Failed login attempts and account lockouts are now audited
  (`session.login_failed` / `session.lockout`) alongside the existing
  session events.
- `update_user` refuses to demote or deactivate the last active
  administrator (advisory-lock serialized), preventing a zero-administrator
  state.
- The experiment builder asks for confirmation before replacing a draft that
  holds recorded content (re-selecting a baseline or starting blank), which
  previously destroyed the draft silently and overwrote the auto-persisted
  copy.
- Gas-backfill stage count (max 5) is now validated client-side with
  per-kind add/switch guards in the VCD editor, instead of failing with a
  server 422 after save.
- Chart domain computations no longer use spread `Math.max(...)`/`Math.min(...)`
  over trace arrays, which could throw a RangeError on dense measurement
  files; a loop-based `extentOf` helper replaces them.
- Browser tests no longer write scratch SQLite databases into the repository
  root; they use a temporary directory.
- The result-detail browser suite no longer fails on a navigation race:
  `wait_for_expression` retries CDP calls that fail because the page is
  mid-navigation ("Inspected target navigated or closed", "Cannot find
  context") instead of failing the test; real page errors still propagate.
  Seen once on the Linux CI runner as a login-redirect test failure.
- The result-detail unit test could flake under parallel-worker load:
  `renderReadyDetail` now drains pending passive effects (`await act`) after
  the detail renders, so the assignment/exclusion prefill can never flush
  between the checkbox toggle and the reason input lookup and wipe the
  in-progress exclusion.
- CI workflow: all four actions upgraded to Node 24 runtimes
  (checkout v4 → v7, setup-python v5 → v7, cache v4 → v6, setup-node v4 →
  v7), clearing the Node.js 20 deprecation warnings on every job.
- Chart exports (SVG / PNG / TIFF) now embed the chart's webfont: IBM Plex
  Sans is inlined as data-URI `@font-face` rules (weights 400 and 600) plus a
  root `font-family`, so exported figures render with the app's typeface
  instead of the browser's default serif. SVG-as-image and external viewers
  cannot load page stylesheets or remote font files, but they do honor
  data-URI fonts; fetch failures degrade to the previous fallback behavior.
- Device-stack layer drag-and-drop: the ⠿ handle now appears only on layers
  that actually have a same-type neighbor (reordering is only legal within a
  same role + layer_type run, so on typical stacks every drop was previously
  a silent no-op), legal drop targets highlight with an insertion edge,
  illegal ones show the not-allowed cursor, the drag ghost is the whole
  card, and the drag populates `dataTransfer` so Firefox can start it at
  all.
- The completion dialog traps Tab focus like the confirm dialog (shared
  `trapModalFocus`), its fields use the shared `FormField` wrapper with
  `aria-invalid`/`aria-describedby` wiring, and the focus ring is drawn
  with `outline` so it is no longer clipped inside scrollable tables.
  Disabled navigation items are now real buttons that explain on
  activation why they are unavailable (touch-friendly).

- Run-sheet refresh races: a reload superseded by a newer in-flight request
  no longer reports success or drops the optimistic sheet. The
  `useApiResource.reload()` contract now reports `applied`, `superseded`, or
  `failed`, and `refetchSheet` stays silent while keeping the optimistic
  copy when superseded on the same route.
- Browser-test Chrome discovery is platform-portable: posix executable
  locations are checked before Windows paths, and launching without any
  installed browser raises a clear error instead of a Windows-path
  `FileNotFoundError` on Linux runners.
- CI: the PostgreSQL job sets `PEROVSKITE_ALEMBIC_CONFIG`, because the
  `--no-editable` install resolves the source-tree `alembic.ini` fallback
  to `site-packages`.
- CI: Actions minutes on the private-repo budget are cut roughly 5x per
  pull request. Duplicate runs on the same branch now cancel each other
  (`concurrency` with `cancel-in-progress`), docs-only changes skip the
  workflow (`paths-ignore`), the 2x-billed Windows leg moved from every PR
  to main merges and manual dispatches (a PR run bills ~14 minutes instead
  of ~70), and `workflow_dispatch` allows re-validating main on demand.

### Removed

- Dead legacy `BaselineStore` SQLite class whose update/get/delete methods
  referenced an undefined `reference_id`.
- The legacy closed-loop optimization stack: the SQLite `ExperimentStore`
  (`perovskite_bo/store.py`), `ClosedLoopOptimizer` (`workflow.py`), the
  web wiring (`web/optimizer.py`), their tests, the random-loop example,
  and the retired test-only notebook. `ExperimentRecord`/`ExperimentStatus`
  moved to `perovskite_bo/records.py`, and `default_search_space` moved to
  `perovskite_bo/web_adapter.py`; the pure strategy/search-space/adapter
  layer remains as the future BO consumer. SQLite is now used exclusively
  by the test suite (aiosqlite) — production remains PostgreSQL-only.

## 0.4.0 - 2026-08-23

Deployment-readiness remediation and the 0.4.0 controlled-trial gate. The
ten-task plan is `docs/superpowers/plans/2026-08-22-deployment-readiness-remediation.md`;
verification evidence is `docs/deployment-checklists/0.4.0-controlled-trial.md`.

### Added

- Physical laser-mark and channel identity: result analysis schema 3 with
  canonical `^[A-Z]\d{3,8}$` substrate marks, explicit device ordinals, and
  Forward/Reverse trace pairing per physical device.
- Typed execution deviations (`general`, `fabrication_shortfall`,
  `measurement_shortfall`) with an active-deviation superseding chain and
  condition/type index.
- Actual substrate counts: batch completion materializes
  `max(planned, actual)` substrate slots with full device sets and frozen
  execution-group memberships, validated by a full-condition pre-check that
  runs before any write.
- Migration `0014_deployment_integrity_repairs` with idempotent data repairs;
  `0013` downgrade now fails before any DDL, and `check-database` rejects
  pre-squash databases by column-width fingerprint.
- CI enforcement: deployable frontend artifact (`git diff --exit-code` on
  `src/web/static-app`), schema-head preflight, real-Chrome suites, and the
  installed-wheel smoke test against the freshly built wheel.

### Changed

- Condition create/update/delete and plan status transitions serialize on the
  parent experiment row; batch completion is one backend transaction.
- Frontend route-state generation guards, destructive plan-change preview,
  and hardened logout/next-path handling.

### Notes

- The first deployment is a controlled trial only. P0-1 environment capture
  and P0-2 material-lot provenance remain open
  (`docs/deferred-issues.md`) and gate authoritative data collection.

## Earlier versions

Pre-0.4.0 history — the initial closed-loop optimization package, the FastAPI
web interface, the guided experiment workflow, and the Jinja-to-React
migration phases — is recorded in the Git history and
`docs/superpowers/plans/`.
