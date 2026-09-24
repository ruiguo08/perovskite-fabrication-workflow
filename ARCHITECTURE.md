# Architecture

The active web application is an experiment registry. It records the exact setup used for each perovskite experiment and associates that snapshot with its characterization results.

Optimization code remains available as an optional future consumer of the stored data, but it does not validate, constrain, or generate records in the current web workflow.

## Dependency Direction

~~~
Browser
  ↓
FastAPI routes and guided builder (src/web)
  ↓
Canonical recipe validation (src/perovskite_bo)
  ↓
Async SQLAlchemy repository
  ↓
PostgreSQL registry, sessions, uploads, and audit log
~~~

The core package must not import the web package.

## Module Responsibilities (application-operations layering)

The web package is layered so that authorization, validation, transactions,
and audit cannot be forgotten when a workflow changes:

~~~
HTTP routes (web/routes/<domain>.py)
  HTTP parsing, auth dependencies, response building only
  maps typed OperationError failures onto status codes
  ↓
Application operations (web/operations/)
  one function per state-changing use case; owns authorization, input and
  domain validation, the transaction boundary, and the audit record
  ↓
Connection-level data functions (web/repository/*.py, web/audit_trail.py)
  queries, row locks, and writes; every function receives the operation's
  connection and never opens its own transaction
  ↓
web.database (schema) / PostgreSQL
~~~

Rules enforced by ``tests/test_layering.py``:

- ``web.repository`` never imports ``web.operations`` at module level. The two
  deprecated repository methods (``update_result_analysis_and_complete``,
  ``update_fabrication_batch_status``) are documented delegates that call the
  operations lazily inside their bodies for backwards compatibility.
- ``web.services`` never imports ``web.repository``; shared low-level
  functionality (audit-event persistence) lives in ``web.audit_trail``, which
  depends only on the database metadata.
- Application operations never raise HTTP exceptions and never import the
  routes; they raise the typed errors from ``web.operations.errors``
  (``RecordNotFound``, ``AccessDenied``, ``InvalidInput``, ``StateConflict``).
  ``InvalidInput`` subclasses ``ValueError`` and ``AccessDenied`` subclasses
  ``PermissionError`` so historical exception contracts keep working.
- ``perovskite_bo`` never imports ``web``.

### Transaction and error boundaries

Each application operation opens exactly one transaction and passes that
connection to every data function, so authorization, state checks, locks,
writes, and the audit record commit or roll back together. Multi-row locks
follow the documented order (experiment -> batch -> result file). The routes
map typed errors as: ``RecordNotFound`` -> 404, ``AccessDenied`` -> 403,
``InvalidInput`` -> 400, ``StateConflict`` -> 409; message texts pass through
unchanged, and unexpected exceptions keep normal 500 handling. Ownership
isolation preserves the fixed 404 bodies that do not reveal whether another
user's record exists.

## Data Ownership

### DepositionRecipe

`DepositionRecipe` is the canonical perovskite process snapshot:

- one to three spin stages;
- an explicitly ordered VCD program containing one to five evacuation stages
  and zero to five MFC gas-backfill stages in any sequence;
- a recorded hold time (seconds) for every gas-backfill stage;
- one or two annealing stages;
- optional versioned device context.

VCD pressure is emitted in integer Pa. Exact legacy mbar values are migrated on read.

### DeviceRecipe

`device_recipe.py` contains Pydantic v2 models for:

- substrate material, vendor, SKU, and dimensions;
- single-junction/normal-bandgap device classification;
- either exactly one control and one or more target groups, or exactly one standalone condition;
- complete target-owned layer/process snapshots when a target diverges from the control;
- ordered functional roles containing one or more material layers;
- Layer Preset provenance;
- quantified solid and solvent ingredients;
- deposition-method-specific process data.

The shared `materials` and `material_products` tables provide the reusable directory for substrates, chemicals, solvents, gases, other materials, vendors, and catalog numbers. The builder fetches active entries from the database rather than a code-defined catalog. Students create pending proposals; instructors and administrators review, activate, edit, or inactivate them. No material-lot or inventory-consumption table exists in this phase. Geometry is not free text: selecting one of the four immutable device layouts sets the approved substrate dimensions and records device count and active area through the layout snapshot. The layout catalog is database-authoritative with no factory seed: administrators create layout rows through `POST /api/device-layouts` (see the Device layouts page), and experiment creation resolves every layout reference against the database — a deployment with no layouts is unusable until the administrator creates the first one. Rows are immutable; a changed geometry is a new `(code, version)` row while old rows keep serving historical conditions.

Layer Presets are owner-isolated database records with no factory catalog: every preset is authored by a user (blank layers can be created from scratch in the builder, so the first preset does not depend on any existing record), and instructors promote student personal presets to shared.  Each authenticated user can create, revise, and deactivate personal presets. Updates append immutable revisions, inactive presets disappear from new selections, and ownership predicates prevent one user from discovering or mutating another user's presets. Selecting any preset copies its complete layer, solution, and process values into the editable experiment configuration.

Baselines and Layer Presets are input-time templates, not database indirection. The browser deep-copies template values into the editable DeviceRecipe. The persisted Experiment, each independent Condition, every frozen Batch condition, and both export formats contain the expanded parameters; a Baseline/Preset identifier is provenance only.

Material directory records are also input-time catalog data. Recipes persist the selected material names and, for substrates, vendor and catalog number as ordinary recipe values. A future lot-tracking feature may add optional immutable catalog references, but no current persisted experiment relies on a material-directory foreign key.

The perovskite process is flattened into `DepositionRecipe`, preventing two writable sources for spin, VCD, and annealing data.

### Plan, Condition, and BaselineVersion

The historical `experiments` row is the parent plan and Campaign member. It owns identity, creator, Campaign-local sequence number, and plan status. `experiment_conditions` owns the actual immutable-at-release fabrication configurations:

- comparative plans require exactly one control and at least one target;
- standalone plans contain exactly one condition;
- each condition stores a complete recipe snapshot, canonical hash, layout snapshot, planned substrate count, and expected device count;
- each condition may point to the exact immutable `baseline_versions` row from which it was created;
- editing a draft condition recomputes derived fields, returns the plan to draft, and invalidates pending or approved substrate exceptions.

Baseline updates append revisions. Archiving hides a Baseline from new student work while preserving all revisions and condition provenance.

There are three deliberately separate version concepts: `series_version` numbers plans within a Campaign; `recipe_schema_version`/condition `schema_version` describes JSON structure; `baseline_versions.revision_number` describes experimental-content history.

### WebRepository

`WebRepository` is the transactional boundary for the network application. It owns:

- immutable-at-release condition recipe JSON and hashes;
- Campaign ID and Campaign-local sequence;
- Baseline revision and device-layout provenance;
- substrate-count exception requests and approvals;
- series-based experiment code and version;
- lifecycle status;
- parsed metrics;
- failure reason;
- creation and update timestamps.
- local users and hashed opaque sessions;
- uploaded result bytes, SHA-256 digests, and uploader attribution;
- append-only audit events for security-relevant mutations.

A Campaign groups related plans but does not impose shared setup values.

The `result_files` table contains:

- experiment ID;
- frozen fabrication batch ID;
- filename and content type;
- byte size;
- raw content;
- required per-substrate control/target condition assignments and optional exact device links;
- per-file parsed metrics;
- per-trace instrument-local measurement timestamps and the server upload timestamp;
- SHA-256 integrity digest and creating user.

Uploads are bounded before persistence. If experiment completion is rejected, the newly inserted file is removed.

## Setup Capture Flow

~~~
Instructor-created active Campaign
  ↓
Saved immutable Baseline revision
  ↓
Comparative plan (control + targets) or standalone plan
  ↓
Versioned layout and at least three substrates per condition
  ↓
Complete independent condition snapshots
  ├── source Baseline version ID
  ├── canonical recipe hash
  └── layout snapshot and expected device count
  ↓
device_recipe_json + deposition_process_json + condition_plans_json
  ↓
web.forms.recipe_from_form
  ├── validate complete DeviceRecipe
  └── flatten perovskite process fields
  ↓
DepositionRecipe.from_mapping
  ↓
WebRepository.add_experiment → validated experiment_conditions
~~~

The browser's `condition_plans_json` supplies the explicit layout and planned substrate count for every group. UI-only layout metadata is removed from `device_recipe_json` before canonical DeviceRecipe validation. The production experiment API requires a complete `device_recipe`; repository persistence rejects flat process-only recipes and requires at least one materialized condition. Ambiguous free-text-only target adjustments remain blocked behind manual review.

## Fabrication Batch Execution

A released Experiment Plan can be executed one or more times through Fabrication Batches. Each batch freezes the plan's condition snapshots, generates labeled substrates and devices, and creates solution-preparation and process-execution groupings.

~~~
Released Experiment Plan
  ↓
Fabrication Batch (draft)
  ├── frozen condition snapshots (copied from experiment_conditions)
  ├── substrates (internal code plus short mark such as A12)
  ├── devices (internal code plus glass mark such as A123)
  ├── solution preparations (grouped by canonical solution hash)
  │   └── solution_preparation_uses (links to batch_condition + layer)
  ├── process executions (grouped by canonical process hash)
  │   └── process_execution_members (links to specific substrates)
  └── execution deviations (append-only, superseding chain)
  ↓
ready → in_progress → completed
  ↓
JSON export (authoritative execution traceability artifact)
~~~

### Batch Lifecycle

- `draft`: Initial state after creation. Substrates, devices, preparations, and executions are generated.
- `ready`: Batch is ready for execution. Every preparation and execution has at least one membership.
- `in_progress`: Execution is active. Frozen snapshots and membership cannot be modified.
- `completed`: All preparations and processes are in terminal states. A consumed preparation and a completed process retain their actual snapshots.
- `cancelled`: Batch was cancelled by an instructor or administrator before completion.

Planning records and memberships can be created or split only while a batch is in `draft`. Execution values and deviations can be recorded before a terminal Batch state, but terminal preparations, executions, and Batches are immutable. Students may execute only Batches belonging to plans they created.

### Pre-creation Validation

Before creating a batch, the system validates:

1. The experiment plan status is `released`.
2. No condition requires manual review.
3. Every condition with fewer than 3 planned substrates has a valid, current approval tied to the exact condition hash.
4. The actor has permission (students can only create batches for their own plans).

### Substrate and Device Generation

Substrates and devices are generated in a single transaction with deterministic internal codes:

- Substrate code: `{batch_code}-{condition_code}-S{NN}` (e.g., `fab-v1-B01-control-v1-C-S01`)
- Device code: `{substrate_code}-D{NN}` (e.g., `fab-v1-B01-control-v1-C-S01-D01`)

Substrate laser marks are a factory-etched physical fact, not a generated value: batch creation leaves `substrate_mark` blank, and the mark parsed from instrument labels (for example `A001`) is written back to exactly one substrate when a result CSV is assigned, serialized on the parent batch row. Marks are unique within the selected batch, while the longer internal code remains globally unique. A batch is limited to 99 substrates and each marked substrate to 9 devices.

The device active area is copied from the immutable device layout catalog, stored as PostgreSQL `NUMERIC` to avoid binary float rounding.

### Solution Preparation Grouping

During batch creation, all layers with solutions across all conditions are scanned and grouped by the SHA-256 hash of the solution JSON. Layers with identical solution content are automatically grouped into a shared preparation. Draft memberships can be split, and only preparations with the same planned hash can be merged.

Planned and actual solution snapshots use an explicit schema version and independent canonical hashes. “Matched plan” is a recording action that copies the full planned recipe into the actual snapshot. Adjusted actual recipes are validated for complete solids, solvents, stock dispersion, weights, and volumes before persistence.

### Process Execution Grouping

Every planned process becomes an execution record. This includes layer spin coating and annealing, perovskite spin coating/VCD/annealing, thermal evaporation, ALD, and sputtering. Sharing requires an exact canonical match of the method, material/layer identity, and process parameters. Draft memberships can be split, and only executions with the same planned hash, snapshot schema, and layer context can be merged. Planned and actual process snapshots carry independent hashes; adjusted actual parameters are validated against the execution method, including the ordered VCD evacuation/backfill program.

### Deviation Recording

Deviations are append-only. Each deviation records a category, severity, description, and optional planned/actual values. A deviation can supersede a previous one via `supersedes_deviation_id`, preserving the full history. Deviations can optionally target a specific solution preparation, process execution, substrate, or device.

### Batch Export

The JSON export is the authoritative execution traceability artifact. It contains:

- Batch identity, status, and condition set hash
- Frozen condition snapshots and hashes
- All substrates and devices with internal codes, short laser marks, and statuses
- Planned and actual solution preparations with snapshot schema versions, hashes, and recording modes
- Planned and actual process executions with snapshot schema versions, hashes, recording modes, and memberships
- Characterization result metadata, hashes, complete parsed analysis, per-trace measurement times, and substrate-confirmed condition assignments
- Complete deviation history with superseding links

The Batch PDF traveler is generated from the same versioned payload and includes a complete configuration appendix. The JSON remains authoritative.

## Plan Export

The JSON download is the authoritative reproducibility artifact. Its versioned payload contains parent plan metadata, the stored recipe, every independent condition snapshot and canonical hash, immutable Baseline-version IDs, device-layout snapshots, expected device counts, and the complete substrate-exception history.

The PDF download is a human-readable execution plan generated from the same payload. It includes condition and layer summaries plus a complete configuration appendix; it does not replace the JSON source of truth.

The historical experiment execution status (`suggested/running/completed/failed`) remains for result compatibility. The plan lifecycle is separate (`draft/pending_approval/approved/released/in_progress/completed/cancelled`).

Instructors and administrators manage Campaigns through the authenticated `/campaigns` page. Creation is active by default; closing or archiving a Campaign immediately removes it from the student builder while preserving its existing plans and audit history.

Every structurally valid draft must pass through pending approval to approved before release; instructor or administrator approval is required at the approved step. A condition planning fewer than three substrates requires an approved substrate exception before the plan can be released. The approval stores the condition hash, so any later edit invalidates it automatically.

## Result Flow

~~~
Bounded single-curve or multi-device JV CSV upload
  ↓
Group traces by physical-device label; parse Voc, Jsc, FF, and PCE; summarize batches
  ↓
Validate extension, media type, filename, NUL bytes, and bounded size
  ↓
Persist raw bytes and digest atomically in result_files
  ↓
Complete the experiment in the same transaction
~~~

## Design Constraints

- Validate every structured setup through canonical models.
- Store a complete setup snapshot on every condition.
- Require a valid active Campaign for every new plan; only instructors/admins create Campaigns.
- Do not require plans in one Campaign to share a fixed setup.
- Treat released condition configurations as immutable.
- Require one control plus one or more targets, or exactly one standalone condition.
- Require three substrates per condition unless an instructor approves one or two against the current condition hash.
- Do not duplicate VCD values in nested device data.
- Require a complete perovskite deposition process for every target-owned stack.
- Treat optional sputtering gas 2 and its flow as an all-or-none pair.
- Do not bypass experiment lifecycle methods.
- Reject non-finite laboratory measurements.
- Bound uploaded result files before storing them.
- Preserve legacy database readability.
- Keep the web interface independent of optimization logic.
- Use asynchronous PostgreSQL I/O and keep JV parsing off the event loop.
- Preserve Baselines as immutable revisions and archive instead of deleting them.
- Require authenticated local users and enforce role and experiment-ownership checks at route boundaries. Students are limited to experiments they created; instructors and administrators retain lab-wide visibility.
- Require same-origin and CSRF validation for every state-changing browser operation.
- Store only hashes of session secrets and revoke sessions after security-sensitive account changes.

## Future Extension Points

- structured result export;
- instrument-specific parsers;
- optional analytical and Bayesian-optimization consumers;
- browser-level end-to-end tests.
