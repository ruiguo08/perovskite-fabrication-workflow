# Perovskite Solar Cell Fabrication Workflow

A laboratory-facing FastAPI application for planning, executing, and recording perovskite solar-cell fabrication experiments and their characterization results.

## Project Goal

Build a deployable laboratory workflow and system of record for perovskite solar-cell fabrication.

The system enables a research team to:

- define campaigns, baselines, device layouts, substrates, layers, solutions, and processing conditions;
- plan comparative or standalone experiments;
- freeze approved plans into reproducible fabrication batches;
- record planned and actual parameters, deviations, and characterization results; and
- export auditable JSON and PDF records with enough provenance to reproduce an experiment.

Baselines and Layer Presets are input templates only. Selecting one expands it into editable process values. Saved experiments, conditions, fabrication batches, and exports must persist every actual process parameter and its versioned snapshot; they must never depend solely on a Baseline or Layer Preset reference. This keeps the data complete, traceable, reconstructible, and suitable for future Bayesian Optimization and machine-learning workflows.

Bayesian Optimization remains a future layer. The immediate priority is reliable, structured, and auditable experiment capture, not automatic experiment suggestion.

## Language Policy

Discussions may use English, Chinese, or both. All repository files must use en-US, including user-facing text, documentation, source comments and docstrings, configuration, scripts and help text, migrations, tests, fixtures, examples, error messages, validation messages, and audit descriptions. Standard scientific terminology, names, units, chemical formulas, and identifiers retain their conventional forms.

## Laboratory Workflow

1. An instructor or administrator creates an active Campaign; students select it rather than inventing a series name.
2. Select a saved Baseline revision. A Baseline contains the device stack plus the material, solution, layer, and process recipe used as the starting point.
3. Create either a comparative plan (exactly one control plus one or more targets) or a standalone plan for a single best-condition run.
4. Choose one versioned layout: 15 × 15 mm / 2 devices / 0.05 cm² each; 20 × 20 mm / 1 × 1 cm² device; 25 × 25 mm / 6 devices / 0.10 cm² each; or 25 × 25 mm / 1 device / 1.017 cm².
5. Plan at least three substrates per condition. Counts of one or two require a reason and instructor approval tied to that exact condition snapshot.
6. Build or adjust each condition layer by layer and record all solution and deposition values.
7. Save a complete independent snapshot for every condition. Released plans cannot be edited.
8. Select the frozen fabrication batch and upload its JV result file. The parser keeps Forward/Reverse scans paired, reads instrument-local measurement timestamps, and requires the student to assign every parsed substrate to exactly one control, target, or standalone condition.

A Campaign groups related plans and assigns their `series_version`/experiment code. It does not make recipes mutable or force all plans in the Campaign to share one setup.

## Device-Stack Builder

The builder supports both device architectures, selected per experiment:

- **p-i-n (inverted)**: ITO or FTO → HTL → perovskite → ETL → metal electrode
- **n-i-p (regular)**: ITO or FTO → ETL → perovskite → HTL → metal electrode

Switching the architecture re-sorts the layer stack to the matching
functional-role order; the buried interface sits below the perovskite and
the top passivation above it in both architectures.

For a p-i-n device the functional-role order is:

~~~
ITO or FTO
→ HTL: NiOx and/or SAM
→ Buried Interface Modifier: SiO2 nanoparticle
→ perovskite (spin coating + Vacuum Chamber Drying)
→ Top Passivation: PEAI or PEAI + EDADI
→ ETL: optional PCBM, required C60, and exactly one of BCP or SnO2
→ Top electrode: Ag
~~~

An n-i-p device places the ETL first and the HTL last (after top passivation),
keeping the same perovskite core between them.

The Material directory is database-backed. It stores reusable substrates, chemicals, solvents, gases, other materials, and supplier products (vendor and catalog number). The experiment builder reads active records from that directory; it does not use a hard-coded material catalog. Students can submit material or supplier-product proposals, which remain pending and visible only to their submitter until an instructor or administrator activates them. Supplier lot and inventory tracking are deliberately out of scope for this phase. Substrate dimensions, device count, and active area remain constrained by the four approved device layouts. Baselines and Layer Presets are input-time templates only: loading one copies its values into the editable plan, and saving an experiment persists every expanded device, solution, and process parameter. Each user can create, revise, and deactivate private Layer Presets from the layer editor; immutable preset revisions preserve provenance, and another user cannot list, update, deactivate, or select them. Baseline/Preset IDs remain provenance metadata and are never substitutes for the complete stored snapshot. Missing formulation quantities and equipment settings remain blank until recorded by the operator.

Each spin-coated solution stores up to 20 solid chemicals and 10 solvents with individual weights and volumes. Non-perovskite spin-coated layers support up to three spin stages; the perovskite process supports up to four. A perovskite VCD program can interleave up to five evacuation stages and five MFC gas-backfill stages in any order; every backfill records its gas, flow, fill target pressure, and hold time (seconds at target). VCD pressures and MFC flows are integer setpoints (Pa and sccm), evacuation and hold durations are whole seconds (0 s = reach the pressure without holding), and a pump-down without pressure control is recorded as 0 Pa with the total pump time (see `docs/vcd-program-entry-guide.md` for the standard entry patterns, also available as an in-app hint beside the program heading). Layers can be reordered with drag-and-drop or keyboard-accessible up/down buttons. Every target-owned stack requires its own complete perovskite spin/VCD/annealing process.

Sputtering requires gas 1 and its flow. Gas 2 is optional, but when used its name and flow must be supplied together; this supports both Ar-only processes and mixed-gas processes such as Ar/O2 NiOx sputtering.

## Stored Data

The persisted plan domain contains:

- one parent experiment/plan with Campaign identity and lifecycle state;
- independent control, target, or standalone condition snapshots;
- canonical spin-coating, VCD, annealing, and layer processing parameters;
- the immutable Baseline revision used to seed each condition;
- a versioned device-layout snapshot and derived expected device count;
- planned substrate count plus any approval decision for a count below three;
- substrate identity and dimensions;
- ordered layers and Layer Preset provenance;
- functional layer roles, a complete control baseline, complete target-owned stack snapshots, and derived target/control differences;
- quantified solution ingredients;
- non-perovskite processing parameters;
- Campaign metadata and a Campaign-local `series_version`;
- lifecycle status and timestamps;
- parsed characterization metrics;
- metadata for the associated raw result file.

Fabrication batches store independently versioned and hashed planned and actual solution/process snapshots. When an operator records that execution matched the plan, the server copies the complete planned parameters into the actual snapshot; it never stores only a “same as planned” flag.

VCD pressure is stored canonically as integer Pa. Deprecated mbar input remains readable when it converts exactly to integer Pa.

Nested floating-point laboratory values reject NaN and infinity.

## Result Upload Safety

JV uploads are read in bounded chunks and are limited to 10 MB. Both simple row-based JV CSVs and multi-device instrument exports are supported. Instrument traces are grouped by normalized physical-device labels, so reordered Forward/Reverse traces remain associated with the right device. Substrate laser marks are factory-etched facts, not system-generated values: batch creation leaves `substrate_mark` blank, and the physical mark read from the instrument labels (for example `A001`) is written back to the matching substrate when a result CSV is assigned. Marks are unique within one batch, so short marks may safely repeat in another batch. Instrument-local timestamps are stored per trace without inventing a timezone. A rejected upload does not leave a result BLOB behind or complete the experiment.

Multi-device exports also preserve each trace block's info rows and capture the instrument software's own summary metrics (Voc, Jsc, FF, PCE/Eff) as reported. The result analysis page shows these instrument-reported values beside the computed metrics, highlights differences beyond tolerance, and provides the J-V comparison overlay, per-metric box plots (optionally split into forward/reverse scan boxes), and SVG/PNG/TIFF chart export for reports. Dead or shorted devices can be excluded from statistics and charts with a recorded reason; exclusion is stored in the analysis, reported in the audit trail, and never deletes the underlying data. The analytic summary is exclusion-aware, while the parse-time acquisition summary over all devices is retained and labeled so the page never shows one number under two meanings.

## Installation

Python 3.14 and PostgreSQL 18 are required for the networked application. On a
Windows development computer, follow
[LOCAL_DEVELOPMENT_WINDOWS.md](LOCAL_DEVELOPMENT_WINDOWS.md). After installing
the project, start it with:

~~~powershell
conda activate PSC314
python -m pip install uv==0.12.1
uv sync --locked --extra test --no-dev
.\scripts\Start-LocalDevelopment.ps1
~~~

The startup script prompts securely for the local application-database password
when needed, applies pending migrations, verifies the schema, and then starts the
server. It refuses non-loopback databases and permits HTTP only on loopback. For
first-user setup and access from other computers, see
[LOCAL_DEVELOPMENT_WINDOWS.md](LOCAL_DEVELOPMENT_WINDOWS.md) and
[DEPLOYMENT.md](DEPLOYMENT.md).

Production does not create a default Campaign. `PEROVSKITE_CAMPAIGN_ID` is an optional preselected Campaign code, but that Campaign must already exist and be active.

Run the tests:

~~~powershell
.\scripts\Configure-LocalTestDatabase.ps1  # once
.\scripts\Test-LocalPostgreSQL.ps1
~~~

This command temporarily points the application at the loopback
`perovskite_test` database. It refuses any other role or database name, so the
application/production database remains untouched.

Run the full unittest suite (the same entry point CI uses):

~~~powershell
uv sync --locked --extra test --no-dev
uv run --no-sync python -m unittest discover -s tests -v
~~~

The browser-driven tests run against an installed Google Chrome browser and are
skipped by default; enable them with `PEROVSKITE_SKIP_BROWSER=0`. To run a
single real-browser smoke test:

~~~powershell
uv sync --locked --extra test --no-dev
uv run --no-sync python -m unittest tests.test_browser_builder -v
~~~

## Web and REST Operations

The React single-page application served at `/app/` is the canonical interface. It supports instructor/admin Campaign management, Baseline-first comparative or standalone plan creation, explicit per-condition layout/substrate planning, experiment history and details, substrate-count approval, plan lifecycle actions, JSON/PDF plan export, fabrication-batch run sheets, JV upload, and parsed-result display and assignment. Legacy server-rendered routes and Jinja templates are removed; the old GET URLs return 303 redirects to their React equivalents.

Access is role-scoped: students can list, open, change, and upload results only for experiments they created. Instructors and administrators have lab-wide experiment access. Instructors and administrators manage Campaigns, create Baselines, and decide substrate-count exceptions; only administrators create new Baseline revisions or archive Baselines. Students see only active Campaigns and active Baselines. Students can submit pending material and supplier-product records, while instructors and administrators review, activate, edit, or inactivate the shared Material directory. Layer Presets have two scopes, personal and shared: students author and manage personal presets, instructors and administrators can additionally create and manage shared presets and promote an active personal preset to shared (ownership predicates still prevent one user from mutating another user's personal presets).

REST endpoints:

- `POST /api/experiments` records a setup in a required active `campaign_id`; `source_baseline_version_id` records its immutable Baseline revision.
- `GET /api/experiments` lists experiment records.
- `GET|POST /api/experiments/{experiment_id}/conditions` reads or adds complete condition snapshots.
- `PUT|DELETE /api/conditions/{condition_id}` changes draft conditions.
- `POST /api/conditions/{condition_id}/substrate-exceptions` requests permission for one or two substrates.
- `POST /api/substrate-exceptions/{exception_id}/decision` records an instructor decision.
- `PATCH /api/experiments/{experiment_id}/plan-status` advances the validated plan lifecycle.
- `GET /experiments/{experiment_id}/export.json` downloads the authoritative versioned plan payload, including exact condition snapshots, hashes, layout snapshots, Baseline lineage, and exception history.
- `GET /experiments/{experiment_id}/export.pdf` downloads a human-readable fabrication plan with a complete configuration appendix.
- `POST /api/experiments/{experiment_id}/results` uploads and parses a JV CSV for a required frozen fabrication batch; the browser then requires one condition assignment per parsed substrate.
- `POST /api/baselines` creates a named Baseline.
- `PUT /api/baselines/{baseline_id}` creates a new immutable Baseline revision.
- `GET /api/baselines`, `GET /api/baselines/{baseline_id}`, and `GET /api/baselines/{baseline_id}/versions` read Baselines and revisions.
- `DELETE /api/baselines/{baseline_id}` archives a Baseline; it does not remove provenance.
- `GET|POST /api/layer-presets`, `PUT|DELETE /api/layer-presets/{preset_id}`, and `GET /api/layer-presets/{preset_id}/versions` manage complete versioned preset snapshots with personal-owner isolation.
- `GET|POST /api/materials` reads the visible Material directory or submits a material; `PATCH /api/materials/{material_id}` is instructor/administrator maintenance.
- `POST /api/materials/{material_id}/products` submits a supplier product; `PATCH /api/material-products/{product_id}` is instructor/administrator maintenance.
- `GET|POST /api/campaigns` and `PATCH /api/campaigns/{code}` read or manage Campaigns.
- `GET /api/device-layouts` returns current versioned layout definitions.
- `GET /api/experiments/{experiment_id}` returns one authorized experiment with conditions, exceptions, batches, and result summaries.
- `GET|POST /api/users`, `PATCH /api/users/{user_id}`, and `POST /api/users/{user_id}/password` provide administrator-only account management.
- **Fabrication Batches**:
  - `POST /api/experiments/{experiment_id}/fabrication-batches` creates a batch.
  - `GET /api/experiments/{experiment_id}/fabrication-batches` lists batches.
  - `GET /api/fabrication-batches/{batch_id}` gets a single batch.
  - `PATCH /api/fabrication-batches/{batch_id}/status` transitions batch status.
  - `GET /api/fabrication-batches/{batch_id}/conditions` frozen condition snapshots.
  - `GET /api/fabrication-batches/{batch_id}/substrates` substrates.
  - `GET /api/fabrication-batches/{batch_id}/devices` devices.
  - `GET|POST /api/fabrication-batches/{batch_id}/solution-preparations` preparations.
  - `PATCH /api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}` update preparation.
  - `GET .../{preparation_id}/uses`, `POST .../{preparation_id}/split`, and `POST .../{preparation_id}/merge` manage draft preparation memberships.
  - `GET|POST /api/fabrication-batches/{batch_id}/process-executions` executions.
  - `PATCH /api/fabrication-batches/{batch_id}/process-executions/{execution_id}` update execution.
  - `GET .../{execution_id}/members`, `POST .../{execution_id}/split`, and `POST .../{execution_id}/merge` manage draft execution memberships.
  - `GET|POST /api/fabrication-batches/{batch_id}/deviations` deviations.
  - `GET /experiments/{experiment_id}/batches/{batch_id}` 303 redirect to the React run sheet.
  - `GET /experiments/{experiment_id}/batches/{batch_id}/export.json` batch JSON export.
  - `GET /experiments/{experiment_id}/batches/{batch_id}/export.pdf` human-readable Batch traveler.

Session and React application endpoints:

- `GET /api/session` returns the current user, role, and CSRF availability for
  the React application (401 when unauthenticated).
- `GET /api/auth/login-csrf` mints the login CSRF token used by a JSON login.
- `POST /api/auth/login` creates the same secure session cookies from JSON
  credentials.
- `POST /api/auth/logout` clears the session with normal CSRF protection.
- `/app/` serves the React application; `/app/{path}` falls back to its entry
  point for client-side routes. The compiled bundle ships inside the Python
  wheel from `src/web/static-app/` (see `docs/react-migration.md`).
- Phase 2 React routes include experiments, experiment detail and planning,
  Campaigns, device layouts, materials, layer presets, Baselines, and
  administrator user management. Phase 3 React routes add the fabrication-batch
  run sheet (`/app/experiments/:id/batches/:batchId`), result upload
  (`/app/experiments/:id/upload`), and result analysis and assignment
  (`/app/results/:resultId`), plus the global `/app/fabrication-batches` and
  `/app/results` lists. Phase 4 made `/app/` the canonical entry: legacy GET
  URLs return 303 redirects to their React equivalents, legacy form-POST
  routes and Jinja templates are removed, and the production wheel ships only
  the React static assets.

`series_version` counts plans within a Campaign. `recipe_schema_version` (and the condition `schema_version`) identifies the JSON document shape so future code can migrate it safely. A Baseline revision number identifies a change in experimental content. These numbers serve different purposes and do not substitute for one another.

Legacy rows using `fabrication_context`, device-stack strings, PVK aliases, or mbar VCD fields remain readable.

## Package Layout

~~~
src/
├── perovskite_bo/
│   ├── device_recipe.py  # validated device, layer, and process models
│   ├── fabrication.py    # legacy fabrication-context compatibility
│   ├── recipe.py         # canonical deposition setup
│   ├── records.py        # experiment record types shared with BO consumers
│   └── ...               # optional future optimization modules
├── web/
│   ├── app.py
│   ├── auth.py           # local accounts, sessions, roles, and CSRF
│   ├── database.py       # async SQLAlchemy PostgreSQL schema
│   ├── repository/       # transactional web persistence and auditing,
│   │                     # split into per-domain mixins (experiment, batch, …)
│   ├── middleware.py
│   ├── models.py
│   ├── plan_export.py    # canonical JSON and human-readable PDF plan export
│   ├── routes.py
│   ├── static-app/           # committed React build output, packaged in the wheel
│   └── services/             # catalog seeding and material catalog data
└── migrations/           # Alembic PostgreSQL schema history
~~~

`frontend/` holds the Vite + React + TypeScript source for the application
served under `/app/`; rebuild it with pnpm (see
`LOCAL_DEVELOPMENT_WINDOWS.md`).

See [ARCHITECTURE.md](ARCHITECTURE.md) for data ownership and flow details.

## Administration CLI

The `perovskite-workflow-admin` console script manages the PostgreSQL database
without exposing an account-creation API. It reads the URL from
`PEROVSKITE_DATABASE_URL` (or `--database-url`):

- `create-user` / `list-users` create and inspect local accounts;
- `cleanup-sessions` deletes expired sessions (run on a schedule);
- `export-audit` writes audit events as JSON lines or CSV, with `--since`,
  `--until`, `--actor`, `--action`, and `--limit` filters;
- `export-training-data` writes `(X, y)` Bayesian-optimization training rows for
  completed batches as JSON lines or CSV (`--experiment-id`, `--batch-id`);
- `check-database` verifies connectivity and that the Alembic head matches;
- `status` prints maintenance counters for monitoring.

## Deployment Safety

The command-line entry point binds to `127.0.0.1`. Local Argon2 accounts provide Student, Instructor, and Administrator roles. Opaque database-backed sessions use secure host-only cookies, absolute and idle expiration, CSRF tokens, login throttling, and revocation after account disabling or password reset. State-changing browser requests also reject cross-site origins. Uploads are bounded to CSV-like text, stored with uploader attribution and SHA-256 integrity metadata, and included in the audit trail.

Follow [DEPLOYMENT.md](DEPLOYMENT.md) before allowing access from other machines. It covers PostgreSQL migrations, initial administrator creation, private-network HTTPS, backups, and file permissions.

See [docs/dependency-supply-chain-httpx2.md](docs/dependency-supply-chain-httpx2.md) for the recorded decision on the `httpx`/`httpx2` test-dependency question and the `starlette` test-client migration.

## Next Steps

- support additional instrument-specific result formats;
- extend automated browser coverage from the current authentication, builder-state, and Batch execution checks to full experiment creation and result assignment;
- advance Bayesian optimization: the training-data pipeline is already in place (the `export-training-data` CLI emits the 19-dimensional deposition features plus aggregated J-V metrics as JSON lines or CSV), and a lightweight strategy layer (`perovskite_bo.strategies`) exists as scaffolding; automatic experiment suggestion remains a future layer once the experiment registry is stable.
