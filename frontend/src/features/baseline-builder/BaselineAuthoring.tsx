import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "../../auth/session";
import { ErrorState } from "../../components/ErrorState";
import { FormField } from "../../components/FormField";
import { InlineFormError } from "../../components/InlineFormError";
import { RequiredLegend } from "../../components/RequiredLegend";
import { LayerStackEditor } from "../experiment-builder/LayerStackEditor";
import { SubstratePanel } from "../experiment-builder/SubstratePanel";
import {
  applyDeviceLayout,
  createBlankDraft,
} from "../experiment-builder/state";
import type { ExperimentDraft } from "../experiment-builder/types";
import { validateBaselineDraft } from "../experiment-builder/validation";
import {
  baselineDraftHasContent,
  clearBaselineDraft,
  loadBaselineDraft,
  saveBaselineDraft,
} from "./draftStorage";
import { apiFetch } from "../../lib/api";
import { useApiResource } from "../../lib/useApiResource";
import { useEditorConfig } from "../../lib/useEditorConfig";
import { VCD_VALVES } from "../../lib/constraints";
import type { DeviceLayout, DeviceRecipe, LayerPreset, Material, PerovskiteDepositionProcess } from "../../types/api";

export interface BaselineAuthoringValues {
  name: string;
  device_recipe: DeviceRecipe;
  deposition_process: PerovskiteDepositionProcess;
}

interface BaselineAuthoringProps {
  /** Server-fixed scope: student creation is Personal, instructor/admin is Shared. */
  scope: "personal" | "shared";
  onSubmit: (values: BaselineAuthoringValues) => Promise<void>;
  /** Optional starting values for revising an existing baseline. When present,
   * the editor pre-fills the name and expands the recipe's layer stack,
   * substrate, architecture, and perovskite process into the draft. */
  initialValues?: BaselineAuthoringValues;
}

function draftFromInitial(initial: BaselineAuthoringValues): ExperimentDraft {
  const draft = createBlankDraft();
  draft.setup_mode = "baseline";
  draft.junction_type = initial.device_recipe.junction_type;
  draft.perovskite_bandgap = initial.device_recipe.perovskite_bandgap;
  draft.architecture = initial.device_recipe.architecture ?? "pin";
  draft.substrate = { ...initial.device_recipe.substrate };
  draft.layers = initial.device_recipe.layers.map((layer) => ({ ...layer }));
  draft.deposition_process = { ...initial.deposition_process };
  return draft;
}

interface AuthoringCatalogs {
  presets: LayerPreset[];
  materials: Material[];
  layouts: DeviceLayout[];
}

/** Single source of meaning for the Control reference recipe sent to the API. */
function baselineDeviceRecipe(draft: ExperimentDraft): DeviceRecipe {
  return {
    schema_version: 2,
    setup_mode: "baseline",
    junction_type: draft.junction_type,
    perovskite_bandgap: draft.perovskite_bandgap,
    architecture: draft.architecture,
    experimental_groups: [
      {
        group_id: "control",
        kind: "control",
        name: "Control",
        change_from_control: "Baseline fabrication procedure",
        inherits_control: false,
        adjustments: [],
        layers: null,
        deposition_process: null,
        substrate_count: null,
      },
      {
        group_id: "target-1",
        kind: "target",
        name: "Target 1",
        change_from_control: "",
        inherits_control: true,
        adjustments: [],
        layers: null,
        deposition_process: null,
        substrate_count: null,
      },
    ],
    substrate: draft.substrate,
    layers: draft.layers,
  };
}

/**
 * First-baseline authoring flow: assemble a complete Control reference
 * recipe from reusable materials, device layouts, and layer presets without
 * requiring an existing source baseline or any raw JSON input.
 */
export function BaselineAuthoring({ scope, onSubmit, initialValues }: BaselineAuthoringProps) {
  const { user } = useSession();
  const [name, setName] = useState(initialValues?.name ?? "");
  const [draft, setDraft] = useState<ExperimentDraft>(() =>
    initialValues ? draftFromInitial(initialValues) : createBlankDraft(),
  );
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [restoredDraft, setRestoredDraft] = useState(false);
  const restoreAttempted = useRef(false);

  // Restore the browser-local draft once per mount (creation flow only), so
  // values entered before switching Library pages or reloading survive.
  useEffect(() => {
    if (initialValues || user === null || restoreAttempted.current) return;
    restoreAttempted.current = true;
    const stored = loadBaselineDraft(user.id);
    if (stored && baselineDraftHasContent(stored.name, stored.draft)) {
      setName(stored.name);
      setDraft(stored.draft);
      setRestoredDraft(true);
    }
  }, [initialValues, user]);

  // Persist every change (creation flow only); cleared on save or discard.
  useEffect(() => {
    if (initialValues || user === null) return;
    saveBaselineDraft(user.id, name, draft);
  }, [initialValues, user, name, draft]);

  function discardDraft() {
    if (user !== null) clearBaselineDraft(user.id);
    setName("");
    setDraft(createBlankDraft());
    setRestoredDraft(false);
  }

  const loadCatalogs = useCallback(async (): Promise<AuthoringCatalogs> => {
    const [presets, materials, layouts] = await Promise.all([
      apiFetch<LayerPreset[]>("/api/layer-presets"),
      apiFetch<Material[]>("/api/materials"),
      apiFetch<DeviceLayout[]>("/api/device-layouts"),
    ]);
    return { presets, materials, layouts };
  }, []);
  const catalogsResource = useApiResource(loadCatalogs);
  const catalogs = catalogsResource.data;
  const catalogError = catalogsResource.status === "error" ? (catalogsResource.error ?? null) : null;
  const editorConfigResource = useEditorConfig();
  const vcdValves = editorConfigResource.data?.vcd_valves ?? VCD_VALVES;

  const issues = useMemo(
    () => validateBaselineDraft(draft, vcdValves),
    [draft, vcdValves],
  );
  const canSubmit = name.trim().length > 0
    && draft.layers.length > 0
    && issues.length === 0
    && !submitting;

  if (catalogsResource.status === "loading" && catalogs === null) {
    return <div className="page-loading" role="status">Loading authoring catalogs…</div>;
  }
  if (catalogs === null) {
    return (
      <ErrorState
        title="Unable to load authoring catalogs"
        message={catalogError ?? "The materials, presets, or device layouts could not be loaded."}
        action={
          <button type="button" className="button button--secondary" onClick={() => void catalogsResource.reload()}>
            Retry
          </button>
        }
      />
    );
  }

  return (
    <form
      className="baseline-authoring"
      onSubmit={(event) => {
        event.preventDefault();
        if (!canSubmit) return;
        setSubmitting(true);
        setError(null);
        void onSubmit({
          name: name.trim(),
          device_recipe: baselineDeviceRecipe(draft),
          deposition_process: draft.deposition_process,
        })
          .then(() => {
            if (!initialValues && user !== null) clearBaselineDraft(user.id);
            setName("");
            setDraft(createBlankDraft());
            setRestoredDraft(false);
          })
          .catch((caught) => {
            setError(caught instanceof Error ? caught.message : "Unable to create the baseline.");
          })
          .finally(() => setSubmitting(false));
      }}
    >
      {restoredDraft && !initialValues ? (
        <div className="draft-restored-note" role="status">
          <span>Draft restored from your last editing session. Your entered values are kept until you save or discard them.</span>
          <button type="button" className="button button--secondary button--small" onClick={discardDraft}>Discard draft</button>
        </div>
      ) : null}

      <RequiredLegend />

      <div className="builder-fields builder-fields--two">
        <FormField label={initialValues ? "Baseline name" : "New baseline name"} htmlFor="new-baseline-name" required>
          <input id="new-baseline-name" className="text-input" required maxLength={240} value={name} onChange={(event) => setName(event.target.value)} />
        </FormField>
        <FormField label="Baseline scope" htmlFor="new-baseline-scope" hint="The server fixes the scope from your role; the baseline cannot be changed to the other scope later.">
          <input id="new-baseline-scope" className="text-input" readOnly value={scope === "shared" ? "Shared (lab-wide starting point)" : "Personal (visible only to you)"} />
        </FormField>
      </div>

      <SubstratePanel
        draft={draft}
        materials={catalogs.materials}
        layouts={catalogs.layouts}
        onChange={setDraft}
        onLayoutChange={(layout) => {
          try {
            setDraft(applyDeviceLayout(draft, layout));
          } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to apply the device layout.");
          }
        }}
      />

      <LayerStackEditor
        draft={draft}
        presets={catalogs.presets}
        materials={catalogs.materials}
        vcdValves={vcdValves}
        onChange={setDraft}
        onError={setError}
      />

      <div className="builder-actions">
        <span>{issues.length === 0
          ? "Complete recipe: each layer and the Perovskite deposition process snapshot are complete."
          : `${issues.length} review items remain before this baseline can be saved.`}</span>
        <button className="button button--primary" type="submit" disabled={!canSubmit}>
          {submitting ? "Saving…" : initialValues ? "Save new revision" : scope === "shared" ? "Save shared baseline" : "Save personal baseline"}
        </button>
      </div>
      {issues.length > 0 ? (
        <div className="builder-issue-summary" role="alert" aria-labelledby="baseline-issues-title">
          <h3 id="baseline-issues-title">Complete these values before saving</h3>
          <ul>{issues.map((issue, index) => <li key={`${issue.path}-${index}`}><code>{issue.path}</code> — {issue.message}</li>)}</ul>
        </div>
      ) : null}
      <InlineFormError message={error} />
    </form>
  );
}