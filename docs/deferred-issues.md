# Deferred Issues

Issues raised in review but **not yet implemented**. This file is the
canonical backlog for accepted, un-actioned findings. When an issue is
implemented, move it to the appropriate section in README.md or
ARCHITECTURE.md and remove it here. Do not delete entries without resolving
them first.

Status of each item: **open** (discussed, agreed, not started) or **in
progress** (a branch exists / partial work landed).

---

## P0 — Reproducibility gaps (the largest real-world variables in perovskite fabrication)

### P0-1. Environment condition recording (humidity / temperature / O2 / glovebox)

- **Status:** open
- **First-principles basis:** perovskite fabrication (NiOx preparation, PVK
  crystallization, DMF/DMSO precursor handling) is highly sensitive to
  humidity, O2, and temperature. Reconstructing a recipe without the ambient
  conditions cannot fully reconstruct the experiment.
- **Current state (verified 2026-08-20):** no environment fields anywhere in
  the schema (`humidity`, `glovebox`, `dew_point` have zero hits in
  `src/web/database.py`).
- **Proposed shape** (keeping the snapshot philosophy):
  - optional `environment_snapshot` JSON on Fabrication Batch (frozen with the
    batch): `humidity_pct`, `temperature_c`, `glovebox_model`, `o2_ppm`,
    `dew_point_c`, ...
  - optional finer-grained per process-execution environment, if needed later.
  - **Design rule:** blank is allowed (never forced), but once filled the value
    enters the snapshot and its canonical hash.
- **Migration impact:** requires a forward migration (next free revision —
  `0013` was taken by the H-1 substrate laser-mark contract). **Schema should
  land before real data collection starts** — retrofitting is expensive.

### P0-2. Material lot / opened-on provenance

- **Status:** open
- **Current state (verified 2026-08-20):** `materials` / `material_products`
  have no lot / inventory / expiry columns (zero hits). README explicitly
  declares lot tracking out of scope.
- **First-principles basis:** water content of DMF/DMSO and batch-to-batch
  purity of PbI2/PEAI are the second-largest reproducibility variable. Today a
  recipe stores only the material name, so which bottle was used cannot be
  reconstructed.
- **Proposed shape** (traceability only, NOT inventory management):
  - optional `lot_number` / `opened_at` / `expiry` on `materials` or
    `material_products`;
  - solution recipe stores the selected `material_product_id` (optional FK) or
    the lot string directly as provenance — consistent with the existing rule:
    values must be expanded into the snapshot, IDs are provenance only.
- **Migration impact:** requires a forward migration (next free revision). Same
  "before real data" timing concern as P0-1.

---

## P1 — Bayesian-optimization data pipeline

### P1-1. Unified (X, y) data extraction layer

- **Status:** extraction wired — `perovskite-workflow-admin
  export-training-data` emits one row per frozen condition of completed
  batches (recipe features, aggregated device metrics, batch provenance)
  through `WebRepository.build_training_dataset` and
  `src/perovskite_bo/web_adapter.py`. Feeding these rows into a live
  optimizer suggestion loop is still not wired.
- **Current state (verified 2026-08-24):** `experiments.recipe` holds flat
  deposition fields; `metrics` is free JSON; the BO `search_space` covers
  spin/VCD parameters; the legacy SQLite closed-loop store
  (`perovskite_bo/store.py`) was removed with the retired optimizer wiring.
  There is no code path from stored web experiments into a training dataset.
- **First-principles basis:** BO fuel is historical experiments as
  (parameter vector, metric vector). Without an extractor, the data never
  becomes consumable.
- **Proposed shape:** a pure, side-effect-free module
  (`src/perovskite_bo/web_adapter.py`, implemented with M-1) that maps one
  condition snapshot + its device metrics into
  `{X: {...search-space params}, y: {pce, voc, jsc, ff}, meta: {...}}`.
  - semantics mirror `search_space` exactly; missing values -> `None`/drop row
    (never fabricate);
  - read-only, safe by construction;
  - shares direction with the Phase 3/4 NOMAD export bridge (same "data
    consumer" family) — can be planned together.

### P1-2. Server-normalized metrics view

- **Status:** open
- **Current state:** `metrics` is free JSON; FF scaling (x100) lives in
  frontend `lib/format.ts scaleMetric`; no single backend-normalized metric
  view.
- **Proposed shape:** a read-only normalized metrics view on the server
  (`{voc_v, jsc_ma_cm2, ff_pct, pce_pct}`) as the unified y vector for BO and
  future EQE/stability extension channels. Consolidates scaling rules in one
  place instead of scattered frontend copies.

---

## Substrate laser-mark model (H-1) — finalized design contract (2026-08-21)

Decisions locked with the user; **implementation in progress**:

1. **Laser mark is physical truth, entered at CSV upload.** The glass laser
   mark (`A001`) is factory-etched per procurement batch (e.g. 3000 pieces =
   A000–A999, B000–B999, C000–C999). It is NOT system-generated and NOT tied
   to a per-student letter or batch sequence. All students are required to
   save J-V data using the unified substrate laser-mark format.
2. **Batch creation leaves `substrate_mark` blank** (currently generated as
   `A12` — will be relaxed to nullable). The laser mark is written back into
   `fabrication_substrates.substrate_mark` when the CSV is uploaded and the
   substrate is associated with a condition.
3. **Device granularity = substrate granularity.** Each device on a substrate
   shares identical process params; CSV parses per-trace (label = substrate
   mark + channel, e.g. `A001 Channel 1`), aggregated to one substrate with
   multiple devices. Assignment is at substrate level only.
4. **`actual_substrate_count`** on `fabrication_batch_conditions` (new,
   nullable, default = planned): recorded at `in_progress -> completed`
   transition. Deviation rules:
   - actual > planned: deviation optional (not required);
   - actual < planned: deviation required;
   - whole group abandoned (actual = 0): deviation required with a reason;
   - CSV substrate count per condition must be <= actual_substrate_count;
     shortfall (made but not measured) requires a deviation.
5. **CSV upload validation**: every parsed substrate must be assigned to a
   condition (existing); new check enforces `CSV count <= actual_count` and
   requires deviation declarations for shortfall.

## P2 — Product / workflow level

### P2-1. Per-substrate actual status on shared executions

- **Status:** open
- **Current state:** `process_execution_members` is per-substrate, but the
  actual result is recorded per shared execution group; a failed substrate
  inside a group is only describable via a deviation.
- **Proposed shape:** optional `actual_status` / `notes` per member
  (`planned -> ok/failed/skipped`), surfaced in the batch JSON export.

### P2-2. Forced confirmation at execution completion

- **Status:** open
- **Current state:** executions already record `executed_by_id`,
  `started_at`, `completed_at`, `equipment_identifier` (good). The
  `completed` transition itself has no forced confirmation step.
- **Proposed shape:** require a confirmation checkbox ("verified against
  actuals") plus optional note when marking an execution `completed`.
  Thin constraint, meaningful trust gain.

---

## Deferred during deployment-readiness review (2026-08-16)

- **BatchDetailPage localSheet-wipe race** — frontend-only; split/merge do not
  write their POST result into localSheet, so a generation-guard "keep" would
  shadow the split topology. Correct fix needs optimistic-edit reconciliation.
  Too risky for a hasty fix on the audit run-sheet. (See commit 1ebb9a5.)
- **D2 / D3 (answered inline, not code changes):** VCD `seconds` = hold time,
  ge=0 correct; students may self-release (no instructor gate on RELEASED).
  *Update 2026-08-27: MFC flows became integer sccm and VCD pressures are
  integer Pa. A 1 s duration floor was tried and reverted the same day: a 0 s
  hold ("reach the pressure and move on") is a real pattern — VV03 pumps fast
  and overshoots setpoints, so VV03 rows with 0 s hand over to a VV06 row
  that stabilizes on target. Durations are whole seconds, 0 or greater; see
  `docs/vcd-program-entry-guide.md`.*

*The batch-code letter rollover note is obsolete: H-2 stopped deriving
substrate marks from the batch number (`substrate_mark` is null until a result
CSV writes back the physical laser mark), so no letter sequence can roll over.*

---

## Deferred during student-feedback triage (2026-08-27)

- **In-app user guide / FAQ page** — deferred until the workflow stabilizes.
  Until then, add contextual `HelpHint` popovers at points where students are
  repeatedly confused (the VCD program heading is the first one); static pages
  rot while the workflow still changes. Build the FAQ page later from the
  accumulated hints and real student questions.
- **Experiment-builder draft persistence** — *completed 2026-08-28, no longer
  deferred.* All three form families now persist drafts to localStorage keyed
  by user id (`perovskite-bo:{scope}-draft:{userId}`) through the shared
  `lib/draftPersistence.ts` factory: Baseline authoring
  (`features/baseline-builder/draftStorage.ts`), the experiment builder
  (`features/experiment-builder/draftStorage.ts`, cleared on successful
  save), and the Layer Preset edit forms
  (`features/layer-presets/presetDraftStorage.ts`, per-preset diff storage,
  cleared on successful revise).

## Deferred during UI overhaul (2026-08-29)

Roadmap and findings: `docs/ui-design-review.md`. PR1-PR3 shipped the token
system, self-hosted IBM Plex, the layer drag-and-drop fix, layout/touch
guardrails, and component-state consistency. The following were deliberately
deferred:

- **Dark mode** — revisit after the design-token system has settled in
  (`frontend/src/styles/tokens.css`); surface/status tokens now make a
  systematic dark palette cheap to add. The lab context is a bright-room,
  light-theme console today.
- **Full tablet/touch adaptation** — the guardrail layer (≥40px run-sheet
  touch targets, ≥8px action gaps, no hover-only information) is in. What
  remains deferred: long-press drag gestures for layer reordering
  (HTML5 drag-and-drop does not fire on touch; the ↑/↓ buttons remain the
  touch fallback), a 1024px intermediate breakpoint, and touch-friendly
  selection models for split/merge.
- **In-app user guide / FAQ page** — still deferred per the 2026-08-27
  triage; continue the contextual `HelpHint` strategy.
