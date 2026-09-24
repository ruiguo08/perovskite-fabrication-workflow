import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useSession } from "../auth/session";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { RequiredLegend } from "../components/RequiredLegend";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { VersionHistory } from "../components/VersionHistory";
import { createPresetDraftStore } from "../features/layer-presets/presetDraftStorage";
import { LayerProcessEditor, PerovskiteProcessEditor } from "../features/experiment-builder/ProcessEditor";
import { SolutionEditor } from "../features/experiment-builder/SolutionEditor";
import { completeDepositionProcess } from "../features/experiment-builder/validation";
import { LAYER_TYPE_DEFS } from "../features/experiment-builder/state";
import type { DraftIssue } from "../features/experiment-builder/types";
import { apiFetch } from "../lib/api";
import { useApiResource } from "../lib/useApiResource";
import { useEditorConfig } from "../lib/useEditorConfig";
import { VCD_VALVES } from "../lib/constraints";
import { formatDateTime, titleCase } from "../lib/format";
import type {
  DeviceLayer,
  LayerPreset,
  LayerPresetVersion,
  LayerProcess,
  LayerSolution,
  Material,
  PerovskiteDepositionProcess,
} from "../types/api";

function sortedPresets(rows: LayerPreset[]): LayerPreset[] {
  return [...rows].sort((left, right) => `${left.scope}:${left.name}`.localeCompare(`${right.scope}:${right.name}`));
}

export function LayerPresetsPage() {
  const { user } = useSession();
  const { show } = useToast();
  const canCreateShared = user?.role === "instructor" || user?.role === "administrator";
  const loadPresets = useCallback(() => apiFetch<LayerPreset[]>("/api/layer-presets?include_inactive=true"), []);
  const resource = useApiResource(loadPresets);
  const loadMaterials = useCallback(() => apiFetch<Material[]>("/api/materials"), []);
  const materialsResource = useApiResource(loadMaterials);
  const materials = materialsResource.data ?? [];
  const editorConfigResource = useEditorConfig();
  const vcdValves = editorConfigResource.data?.vcd_valves ?? VCD_VALVES;
  const loadPromotable = useCallback(
    () => (canCreateShared ? apiFetch<LayerPreset[]>("/api/layer-presets?promotable=true") : Promise.resolve([])),
    [canCreateShared],
  );
  const promotableResource = useApiResource(loadPromotable);
  const [promotedIds, setPromotedIds] = useState<number[]>([]);
  const promotableRows = (promotableResource.data ?? []).filter((row) => !promotedIds.includes(row.id));
  // The promotable list is a staff-only side panel: never block the page on
  // it, but its failure must be visible instead of silently dropping the
  // promote section.
  const promotableError = canCreateShared && promotableResource.status === "error"
    ? `Unable to load student presets for promotion: ${promotableResource.error ?? "unknown error"}`
    : null;
  const [presets, setPresets] = useState<LayerPreset[] | null>(null);
  const rows = useMemo(() => sortedPresets(presets ?? resource.data ?? []), [presets, resource.data]);
  const activeRows = rows.filter((preset) => preset.status === "active");
  const [sourceId, setSourceId] = useState("");
  const [name, setName] = useState("");
  const [scope, setScope] = useState<"personal" | "shared">(canCreateShared ? "shared" : "personal");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function replacePresetFromBlank(created: LayerPreset) {
    replacePreset(created);
  }

  const selectedSource = activeRows.find((preset) => String(preset.id) === sourceId) ?? activeRows[0];

  function replacePreset(replacement: LayerPreset) {
    setPresets((current) => sortedPresets((current ?? rows).some((row) => row.id === replacement.id)
      ? (current ?? rows).map((row) => row.id === replacement.id ? replacement : row)
      : [...(current ?? rows), replacement]));
  }

  async function createPreset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSource) {
      setError("Select an active source preset.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiFetch<LayerPreset>("/api/layer-presets", {
        method: "POST",
        body: {
          name: name.trim(),
          layer: selectedSource.layer,
          deposition_process: selectedSource.deposition_process,
          scope: canCreateShared ? scope : "personal",
        },
      });
      replacePreset(created);
      setName("");
      show("Layer preset created from a complete snapshot.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the layer preset.");
    } finally {
      setSubmitting(false);
    }
  }

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading layer presets…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load layer presets."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="Layer presets"
        description="Reusable input templates. Selecting a preset copies its complete values into an editable experiment configuration."
      />
      <section className="panel panel--accent" aria-labelledby="create-preset-title">
        <h2 className="panel__title" id="create-preset-title">Create from saved snapshot</h2>
        <form className="preset-create-grid" onSubmit={(event) => void createPreset(event)}>
          <FormField label="New preset name" htmlFor="new-preset-name" required>
            <input id="new-preset-name" className="text-input" required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
          </FormField>
          <FormField label="Source preset" htmlFor="source-preset" required>
            <select id="source-preset" className="text-input" required value={selectedSource ? String(selectedSource.id) : ""} onChange={(event) => setSourceId(event.target.value)}>
              {activeRows.map((preset) => <option key={preset.id} value={preset.id}>{preset.name} · {preset.layer.role.replace(/_/g, " ")} · {preset.scope}</option>)}
            </select>
          </FormField>
          {canCreateShared ? (
            <FormField label="Preset scope" htmlFor="new-preset-scope" required>
              <select id="new-preset-scope" className="text-input" value={scope} onChange={(event) => setScope(event.target.value as "personal" | "shared")}>
                <option value="shared">Shared directory</option>
                <option value="personal">Personal</option>
              </select>
            </FormField>
          ) : null}
          <div className="form-grid__action">
            <button className="button button--primary" type="submit" disabled={submitting || !selectedSource}>
              {submitting ? "Creating…" : canCreateShared && scope === "shared" ? "Create shared preset" : "Create personal preset"}
            </button>
          </div>
        </form>
        <InlineFormError message={error} />
      </section>

      <BlankPresetForm
        canCreateShared={canCreateShared}
        materials={materials}
        vcdValves={vcdValves}
        onCreated={replacePresetFromBlank}
      />

      {promotableError ? (
        <div className="inline-form-error" role="alert">{promotableError}</div>
      ) : null}

      <div className="catalog-columns">
        <PresetGroup
          title="Shared presets"
          rows={rows.filter((preset) => preset.scope === "shared")}
          canManageShared={canCreateShared}
          materials={materials}
          vcdValves={vcdValves}
          onChange={replacePreset}
        />
        <PresetGroup
          title="My presets"
          rows={rows.filter((preset) => preset.scope === "personal")}
          canManageShared={canCreateShared}
          materials={materials}
          vcdValves={vcdValves}
          onChange={replacePreset}
        />
        {canCreateShared && promotableRows.length > 0 ? (
          <PresetGroup
            title="Student personal presets — promote to shared"
            rows={promotableRows}
            canManageShared={canCreateShared}
            materials={materials}
            vcdValves={vcdValves}
            promoteOnly
            onChange={(updated) => {
              setPromotedIds((current) => [...current, updated.id]);
              replacePreset(updated);
            }}
          />
        ) : null}
      </div>
    </>
  );
}

/**
 * Author a preset from scratch — the from-zero path that also works when no
 * saved snapshot exists yet. Mirrors the backend's preset contract: a
 * perovskite preset must carry a complete deposition-process snapshot, every
 * other layer type may store an empty solution/process and leave the
 * experiment-specific setpoints to be filled in per experiment.
 */
function BlankPresetForm({
  canCreateShared,
  materials,
  vcdValves,
  onCreated,
}: {
  canCreateShared: boolean;
  materials: Material[];
  vcdValves: readonly string[];
  onCreated: (preset: LayerPreset) => void;
}) {
  const { show } = useToast();
  const [layerType, setLayerType] = useState("");
  const [presetName, setPresetName] = useState("");
  const [layerName, setLayerName] = useState("");
  const [scope, setScope] = useState<"personal" | "shared">(canCreateShared ? "shared" : "personal");
  const [solution, setSolution] = useState<LayerSolution | null>(null);
  const [layerProcess, setLayerProcess] = useState<LayerProcess | null>(null);
  const [depositionProcess, setDepositionProcess] = useState<PerovskiteDepositionProcess | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const definition = LAYER_TYPE_DEFS.find((item) => item.layerType === layerType);
  const isPerovskite = layerType === "perovskite";

  function selectLayerType(nextType: string) {
    setLayerType(nextType);
    const next = LAYER_TYPE_DEFS.find((item) => item.layerType === nextType);
    if (next && !layerName.trim()) setLayerName(next.label);
    setSolution(null);
    setLayerProcess(null);
    setDepositionProcess(nextType === "perovskite"
      ? { method: "spin_coating_vcd", spin_steps: [], vcd_stages: [], gas_backfill_stages: [], vcd_step_sequence: [], anneal_steps: [] }
      : null);
  }

  // Same gate as the revision editor: a perovskite preset is copied verbatim
  // into baselines and experiments, so every spin/VCD/anneal stage must be
  // complete before the preset can be saved.
  const issues = useMemo<DraftIssue[]>(() => {
    const found: DraftIssue[] = [];
    if (!presetName.trim()) found.push({ path: "name", message: "Enter a preset name." });
    if (!layerName.trim()) found.push({ path: "layer.name", message: "Enter a layer name." });
    if (depositionProcess) {
      completeDepositionProcess(depositionProcess, found, "deposition_process", "perovskite", vcdValves);
    }
    return found;
  }, [presetName, layerName, depositionProcess, vcdValves]);

  async function createFromBlank(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!definition || issues.length > 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const layer: DeviceLayer = {
        layer_type: definition.layerType,
        role: definition.role,
        name: layerName.trim(),
        preset_id: null,
        solution,
        process: layerProcess,
      };
      const created = await apiFetch<LayerPreset>("/api/layer-presets", {
        method: "POST",
        body: {
          name: presetName.trim(),
          layer,
          deposition_process: isPerovskite ? depositionProcess : null,
          scope: canCreateShared ? scope : "personal",
        },
      });
      onCreated(created);
      setPresetName("");
      setLayerName("");
      setLayerType("");
      setSolution(null);
      setLayerProcess(null);
      setDepositionProcess(null);
      show("Layer preset created from scratch.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create the layer preset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="create-blank-preset-title">
      <h2 className="panel__title" id="create-blank-preset-title">Create from scratch</h2>
      <p className="builder-help">Build the first reusable preset without any saved snapshot. Perovskite presets must record a complete deposition process; other layer types may leave the solution and process empty and fill them in per experiment.</p>
      <form onSubmit={(event) => void createFromBlank(event)}>
        <div className="builder-fields builder-fields--two">
          <FormField label="Layer type" htmlFor="blank-preset-type" required>
            <select
              id="blank-preset-type"
              className="text-input"
              required
              value={layerType}
              onChange={(event) => selectLayerType(event.target.value)}
            >
              <option value="">Choose a layer type…</option>
              {LAYER_TYPE_DEFS.map((item) => (
                <option key={item.layerType} value={item.layerType}>{item.label} · {item.role.replace(/_/g, " ")}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Preset name" htmlFor="blank-preset-name" required>
            <input
              id="blank-preset-name"
              className="text-input"
              required
              maxLength={120}
              value={presetName}
              onChange={(event) => setPresetName(event.target.value)}
            />
          </FormField>
        </div>
        {definition ? (
          <>
            <FormField label="Layer name" htmlFor="blank-preset-layer-name" required>
              <input
                id="blank-preset-layer-name"
                className="text-input"
                required
                maxLength={120}
                value={layerName}
                onChange={(event) => setLayerName(event.target.value)}
              />
            </FormField>
            <p className="builder-help">Role {titleCase(definition.role)} — derived from the layer type and fixed for this preset.</p>
            <RequiredLegend />
            <SolutionEditor idPrefix="blank-preset" solution={solution} materials={materials} onChange={setSolution} />
            {isPerovskite ? (
              depositionProcess ? (
                <PerovskiteProcessEditor process={depositionProcess} materials={materials} vcdValves={vcdValves} onChange={setDepositionProcess} />
              ) : null
            ) : (
              <LayerProcessEditor layerType={layerType} process={layerProcess} materials={materials} onChange={setLayerProcess} />
            )}
          </>
        ) : null}
        {canCreateShared ? (
          <FormField label="Preset scope" htmlFor="blank-preset-scope" required>
            <select
              id="blank-preset-scope"
              className="text-input"
              value={scope}
              onChange={(event) => setScope(event.target.value as "personal" | "shared")}
            >
              <option value="shared">Shared directory</option>
              <option value="personal">Personal</option>
            </select>
          </FormField>
        ) : null}
        <InlineFormError message={error} />
        {issues.length > 0 && layerType ? (
          <div className="builder-issue-summary" role="alert" aria-labelledby="blank-preset-issues-title">
            <h3 id="blank-preset-issues-title">Complete these values before saving</h3>
            <ul>{issues.map((issue, index) => <li key={`${issue.path}-${index}`}><code>{issue.path}</code> — {issue.message}</li>)}</ul>
          </div>
        ) : null}
        <div className="form-grid__action">
          <button
            className="button button--primary"
            type="submit"
            disabled={submitting || !definition || issues.length > 0}
          >
            {submitting ? "Creating…" : canCreateShared && scope === "shared" ? "Create shared preset" : "Create personal preset"}
          </button>
        </div>
      </form>
    </section>
  );
}

function PresetGroup({
  title,
  rows,
  canManageShared,
  materials,
  vcdValves,
  promoteOnly = false,
  onChange,
}: {
  title: string;
  rows: LayerPreset[];
  canManageShared: boolean;
  materials: Material[];
  vcdValves: readonly string[];
  promoteOnly?: boolean;
  onChange: (preset: LayerPreset) => void;
}) {  return (
    <section className="catalog-group" aria-labelledby={`preset-group-${title.replaceAll(" ", "-").toLowerCase()}`}>
      <div className="catalog-group__heading">
        <h2 id={`preset-group-${title.replaceAll(" ", "-").toLowerCase()}`}>{title}</h2>
        <span className="record-count">{rows.length} records</span>
      </div>
      <div className="preset-list">
        {rows.length === 0 ? <EmptyState title={`No ${title.toLowerCase()} are available.`} /> : rows.map((preset) => (
          <PresetCard
            key={preset.id}
            preset={preset}
            canManage={!promoteOnly && (preset.scope === "personal" || canManageShared)}
            materials={materials}
            vcdValves={vcdValves}
            promoteOnly={promoteOnly}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}

function PresetCard({ preset, canManage, materials, vcdValves, promoteOnly = false, onChange }: { preset: LayerPreset; canManage: boolean; materials: Material[]; vcdValves: readonly string[]; promoteOnly?: boolean; onChange: (preset: LayerPreset) => void }) {
  const { show } = useToast();
  const { user } = useSession();
  const presetDraftStore = useMemo(() => createPresetDraftStore(preset.id, {
    name: preset.name,
    layerName: preset.layer.name,
    solution: preset.layer.solution,
    layerProcess: preset.layer.process ?? null,
    depositionProcess: preset.deposition_process,
  }), [preset]);
  const [name, setName] = useState(preset.name);
  const [layerName, setLayerName] = useState(preset.layer.name);
  const [solution, setSolution] = useState<LayerSolution | null>(preset.layer.solution);
  const [layerProcess, setLayerProcess] = useState<LayerProcess | null>(preset.layer.process ?? null);
  const [depositionProcess, setDepositionProcess] = useState<PerovskiteDepositionProcess | null>(preset.deposition_process);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmingPromotion, setConfirmingPromotion] = useState(false);
  const [restoredDraft, setRestoredDraft] = useState(false);
  const restoreAttempted = useRef(false);

  // A perovskite preset's deposition snapshot is copied verbatim into baselines
  // and experiments, so — like the backend — block saving until every spin/VCD/
  // anneal stage is complete. Layer processes may stay incomplete on purpose
  // (experiment-specific setpoints are filled in per experiment).
  const presetIssues = useMemo<DraftIssue[]>(() => {
    const found: DraftIssue[] = [];
    if (depositionProcess) {
      completeDepositionProcess(depositionProcess, found, "deposition_process", "perovskite", vcdValves);
    }
    return found;
  }, [depositionProcess, vcdValves]);

  useEffect(() => {
    if (user === null || restoreAttempted.current) return;
    restoreAttempted.current = true;
    const stored = presetDraftStore.load(user.id);
    if (stored !== null) {
      setName(stored.name);
      setLayerName(stored.layerName);
      setSolution(stored.solution);
      setLayerProcess(stored.layerProcess);
      setDepositionProcess(stored.depositionProcess);
      setRestoredDraft(true);
    }
  }, [user, presetDraftStore]);

  useEffect(() => {
    if (user === null) return;
    presetDraftStore.save(user.id, { name, layerName, solution, layerProcess, depositionProcess });
  }, [user, presetDraftStore, name, layerName, solution, layerProcess, depositionProcess]);

  function discardRestoredDraft() {
    if (user !== null) presetDraftStore.clear(user.id);
    setName(preset.name);
    setLayerName(preset.layer.name);
    setSolution(preset.layer.solution);
    setLayerProcess(preset.layer.process ?? null);
    setDepositionProcess(preset.deposition_process);
    setRestoredDraft(false);
  }

  async function revise(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const layer = {
        ...preset.layer,
        name: layerName.trim(),
        solution,
        process: layerProcess,
      } as DeviceLayer;
      const updated = await apiFetch<LayerPreset>(`/api/layer-presets/${preset.id}`, {
        method: "PUT",
        body: { name: name.trim(), layer, deposition_process: depositionProcess, scope: preset.scope },
      });
      if (user !== null) presetDraftStore.clear(user.id);
      onChange(updated);
      setRestoredDraft(false);
      show("A new immutable preset revision was saved.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to revise the layer preset.");
    } finally {
      setSubmitting(false);
    }
  }

  const canPromote = preset.scope === "personal"
    && preset.status === "active"
    && (user?.role === "instructor" || user?.role === "administrator");

  async function promote() {
    setConfirmingPromotion(false);
    setError(null);
    try {
      const updated = await apiFetch<LayerPreset>(`/api/layer-presets/${preset.id}/promote`, { method: "POST" });
      onChange(updated);
      show(`${updated.name} is now shared with every student.`, "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to promote the layer preset.");
    }
  }

  async function deactivate() {
    setConfirming(false);
    setError(null);
    try {
      await apiFetch<void>(`/api/layer-presets/${preset.id}`, { method: "DELETE" });
      onChange({ ...preset, status: "inactive" });
      show("Layer preset deactivated.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to deactivate the layer preset.");
    }
  }

  const titleId = `preset-title-${preset.id}`;
  return (
    <article className="preset-card" aria-labelledby={titleId}>
      <header className="preset-card__header">
        <div>
          <div className="material-card__title-line">
            <h3 id={titleId}>{preset.name}</h3>
            <StatusBadge status={preset.status} />
            <span className="scope-chip">{preset.scope}</span>
          </div>
          <p className="preset-card__identity">{titleCase(preset.layer.role)} · {preset.layer.name} · {preset.layer.process?.method?.replace(/_/g, " ") ?? "process in deposition snapshot"}</p>
        </div>
        <span className="version-mark">r{preset.current_revision_number} · {formatDateTime(preset.updated_at)}</span>
      </header>
      <code className="catalog-hash">{preset.canonical_hash}</code>

      {!promoteOnly && canManage && preset.status === "active" ? (
        <details className="inline-editor">
          <summary>Edit preset</summary>
          <form className="inline-editor__body" onSubmit={(event) => void revise(event)}>
            {restoredDraft ? (
              <div className="draft-restored-note" role="status">
                <span>Unsaved edits to this preset were restored from your last session.</span>
                <button type="button" className="button button--secondary button--small" onClick={discardRestoredDraft}>Discard edits</button>
              </div>
            ) : null}
            <FormField label={`Preset name`} htmlFor={`preset-name-${preset.id}`} required>
              <input id={`preset-name-${preset.id}`} className="text-input" required value={name} onChange={(event) => setName(event.target.value)} />
            </FormField>
            <FormField label={`Layer name`} htmlFor={`preset-layer-name-${preset.id}`} required>
              <input id={`preset-layer-name-${preset.id}`} className="text-input" required value={layerName} onChange={(event) => setLayerName(event.target.value)} />
            </FormField>
            <p className="builder-help">Layer type <code>{preset.layer.layer_type}</code> · role {titleCase(preset.layer.role)}{preset.layer.preset_id ? ` · source key ${preset.layer.preset_id}` : ""}. These identity fields are fixed for this preset.</p>
            <RequiredLegend />

            <SolutionEditor idPrefix={`preset-${preset.id}`} solution={solution} materials={materials} onChange={setSolution} />
            <LayerProcessEditor layerType={preset.layer.layer_type} process={layerProcess} materials={materials} onChange={setLayerProcess} />

            {depositionProcess ? (
              <PerovskiteProcessEditor process={depositionProcess} materials={materials} vcdValves={vcdValves} onChange={setDepositionProcess} />
            ) : (
              <p className="builder-empty-editor">No perovskite deposition process — this layer type records its process above.</p>
            )}

            <InlineFormError message={error} />
            {presetIssues.length > 0 ? (
              <div className="builder-issue-summary" role="alert" aria-labelledby={`preset-issues-title-${preset.id}`}>
                <h3 id={`preset-issues-title-${preset.id}`}>Complete these values before saving</h3>
                <ul>{presetIssues.map((issue, index) => <li key={`${issue.path}-${index}`}><code>{issue.path}</code> — {issue.message}</li>)}</ul>
              </div>
            ) : null}
            <button className="button button--secondary" type="submit" disabled={submitting || presetIssues.length > 0}>Save new revision</button>
          </form>
        </details>
      ) : null}

      {!promoteOnly ? (
        <VersionHistory<LayerPresetVersion>
          endpoint={`/api/layer-presets/${preset.id}/versions`}
          renderSnapshot={(version) => <pre className="snapshot-json">{JSON.stringify({ layer: version.layer, deposition_process: version.deposition_process }, null, 2)}</pre>}
        />
      ) : null}
      {canPromote ? (
        <>
          {/* Promotion failures must be visible on promote-only cards, whose
              edit form (and its InlineFormError) is not rendered. */}
          <InlineFormError message={promoteOnly ? error : null} />
          <button className="button button--secondary button--small" type="button" onClick={() => setConfirmingPromotion(true)}>Promote {preset.name} to shared</button>
        </>
      ) : null}
      {!promoteOnly && canManage && preset.status === "active" ? (
        <button className="button button--danger button--small catalog-danger-action" type="button" onClick={() => setConfirming(true)}>Deactivate {preset.name}</button>
      ) : null}
      <ConfirmDialog
        open={confirmingPromotion}
        title="Promote layer preset to shared"
        message={`Every student will be able to select ${preset.name} as a starting point. Promotion is one-way: the preset cannot be made personal again.`}
        confirmLabel="Promote to shared"
        onConfirm={() => void promote()}
        onCancel={() => setConfirmingPromotion(false)}
      />
      <ConfirmDialog
        open={confirming}
        title="Deactivate layer preset"
        message="Existing experiment snapshots remain unchanged. This preset will no longer be available for new selections."
        confirmLabel="Deactivate preset"
        destructive
        onConfirm={() => void deactivate()}
        onCancel={() => setConfirming(false)}
      />
    </article>
  );
}
