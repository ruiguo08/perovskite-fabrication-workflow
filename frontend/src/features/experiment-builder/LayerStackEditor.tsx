import { useMemo, useRef, useState } from "react";
import type { DeviceLayer, LayerPreset, Material } from "../../types/api";
import { RequiredLegend } from "../../components/RequiredLegend";
import { VCD_VALVES } from "../../lib/constraints";
import { completeDepositionProcess, completeLayer } from "./validation";
import type { DraftIssue, ExperimentDraft } from "./types";
import {
  addBlankLayer,
  addLayer,
  canAddLayerType,
  canReorderLayers,
  expandLayerPreset,
  LAYER_TYPE_DEFS,
  moveLayerWithinRole,
  removeLayer,
  reorderLayer,
  replacePrimaryLayer,
  replacePrimaryProcess,
  setArchitecture,
} from "./state";
import { LayerProcessEditor, PerovskiteProcessEditor } from "./ProcessEditor";
import { SolutionEditor } from "./SolutionEditor";

interface LayerStackEditorProps {
  draft: ExperimentDraft;
  presets: LayerPreset[];
  materials: Material[];
  /** Authoritative valve choices from GET /api/editor-config. */
  vcdValves?: readonly string[];
  onChange: (draft: ExperimentDraft) => void;
  onError: (message: string | null) => void;
}

function layerLabel(layer: DeviceLayer): string {
  return `${layer.name} · ${layer.role.replace(/_/g, " ")}`;
}

export function LayerStackEditor({ draft, presets, materials, vcdValves, onChange, onError }: LayerStackEditorProps) {
  const [presetId, setPresetId] = useState("");
  const [blankType, setBlankType] = useState("");
  const valves = vcdValves ?? VCD_VALVES;
  const activePresets = useMemo(
    () => presets.filter((preset) => preset.status === "active").sort((left, right) => left.name.localeCompare(right.name)),
    [presets],
  );
  // Surface incomplete values on the collapsed cards so students know which
  // card hides the review item: the perovskite card stores its process in
  // draft.deposition_process; other layers carry their own process/solution.
  const perovskiteIncomplete = useMemo(() => {
    const found: DraftIssue[] = [];
    completeDepositionProcess(draft.deposition_process, found, "deposition_process", "perovskite", valves);
    return found.length > 0;
  }, [draft.deposition_process, valves]);
  const incompleteLayers = useMemo(() => {
    const incomplete = new Set<number>();
    draft.layers.forEach((layer, index) => {
      const found: DraftIssue[] = [];
      completeLayer(layer, index, found);
      if (found.length > 0) {
        incomplete.add(index);
      }
    });
    return incomplete;
  }, [draft.layers]);

  function apply(action: () => ExperimentDraft) {
    try {
      onChange(action());
      onError(null);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to update the layer stack.");
    }
  }

  // Drag-and-drop reordering. Only same role + layer_type runs are reorderable
  // (enforced by canReorderLayers/reorderLayer); the handle is rendered only on
  // cards where a legal move exists, and illegal drop targets reject the drop
  // (no preventDefault → the browser shows its not-allowed cursor) instead of
  // silently doing nothing.
  const draggedIndex = useRef<number | null>(null);
  const [dropTarget, setDropTarget] = useState<{ index: number; edge: "before" | "after" } | null>(null);

  function handleDragStart(index: number, event: { dataTransfer: DataTransfer | null; currentTarget: Element }) {
    draggedIndex.current = index;
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      // Firefox only starts a drag once the data store is populated.
      event.dataTransfer.setData("text/plain", String(index));
      const card = event.currentTarget.closest(".builder-layer-card");
      if (card && typeof event.dataTransfer.setDragImage === "function") {
        // Drag the whole card, not the tiny handle glyph.
        event.dataTransfer.setDragImage(card, 24, 12);
      }
    }
  }

  function handleDragOver(index: number, event: { preventDefault: () => void; dataTransfer: DataTransfer | null }) {
    const from = draggedIndex.current;
    if (from === null || from === index || !canReorderLayers(draft, from, index)) {
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "none";
      }
      setDropTarget((current) => (current === null ? current : null));
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "move";
    }
    const edge: "before" | "after" = index > from ? "after" : "before";
    setDropTarget((current) => (current && current.index === index && current.edge === edge ? current : { index, edge }));
  }

  function handleDrop(index: number, event: { preventDefault: () => void }) {
    event.preventDefault();
    const from = draggedIndex.current;
    draggedIndex.current = null;
    setDropTarget(null);
    if (from === null || !canReorderLayers(draft, from, index)) {
      return;
    }
    apply(() => reorderLayer(draft, from, index));
  }

  function handleDragEnd() {
    draggedIndex.current = null;
    setDropTarget(null);
  }

  function addSelectedPreset() {
    const preset = activePresets.find((item) => String(item.id) === presetId);
    if (!preset) return;
    apply(() => addLayer(draft, preset));
    setPresetId("");
  }

  function addSelectedBlankLayer() {
    if (!blankType) return;
    apply(() => addBlankLayer(draft, blankType));
    setBlankType("");
  }

  return (
    <section className="builder-panel" aria-labelledby="builder-layers-title">
      <div className="builder-panel__heading">
        <div><span className="builder-panel__eyebrow">Step 3</span><h2 id="builder-layers-title">Functional layer stack</h2></div>
        <span className="record-count">{draft.layers.length} layers</span>
      </div>
      <p className="builder-help">Adding or replacing a preset copies its complete values into this draft. Later preset revisions cannot alter the saved experiment.</p>
      <RequiredLegend />
      <div className="builder-architecture-picker">
        <label className="builder-field" htmlFor="builder-architecture"><span>Device architecture</span>
          <select id="builder-architecture" className="text-input" value={draft.architecture} onChange={(event) => onChange(setArchitecture(draft, event.target.value as "pin" | "nip"))}>
            <option value="pin">p-i-n (inverted: HTL on substrate)</option>
            <option value="nip">n-i-p (regular: ETL on substrate)</option>
          </select>
        </label>
        <p className="builder-help">Sets the deposition role order. Switching re-sorts the stack; within-role material order is preserved.</p>
      </div>
      <div className="builder-preset-picker">
        <label className="builder-field" htmlFor="builder-add-preset"><span>Layer preset</span>
          <select id="builder-add-preset" className="text-input" value={presetId} onChange={(event) => setPresetId(event.target.value)}>
            <option value="">Choose an active preset…</option>
            {activePresets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name} · {preset.layer.layer_type} · {preset.scope}</option>)}
          </select>
        </label>
        <button type="button" className="button button--secondary" disabled={!presetId} onClick={addSelectedPreset}>Add copied preset</button>
      </div>
      <div className="builder-preset-picker">
        <label className="builder-field" htmlFor="builder-add-blank"><span>New blank layer</span>
          <select id="builder-add-blank" className="text-input" value={blankType} onChange={(event) => setBlankType(event.target.value)}>
            <option value="">Choose a layer type…</option>
            {LAYER_TYPE_DEFS.filter((definition) => canAddLayerType(draft, definition.layerType)).map((definition) => (
              <option key={definition.layerType} value={definition.layerType}>{definition.label} · {definition.role.replace(/_/g, " ")}</option>
            ))}
          </select>
        </label>
        <button type="button" className="button button--secondary" disabled={!blankType} onClick={addSelectedBlankLayer}>Add blank layer</button>
      </div>
      <p className="builder-help">A blank layer starts with no solution and no process — add them via “Edit complete layer values”. Presets are a shortcut, not a requirement.</p>
      <p className="builder-help">Layers of the same material type can be resequenced by dragging the handle; different materials retain the required device order.</p>

      <div className="builder-layer-list">
        {draft.layers.length === 0 ? <p className="builder-empty-editor">No layers yet. Add copied presets or blank layers; they are placed in the required device order.</p> : null}
        {draft.layers.map((layer, index) => {
          const replacementPresets = activePresets.filter((preset) => preset.layer.layer_type === layer.layer_type);
          const canMoveEarlier = index > 0 && draft.layers[index - 1].role === layer.role && draft.layers[index - 1].layer_type === layer.layer_type;
          const canMoveLater = index < draft.layers.length - 1 && draft.layers[index + 1].role === layer.role && draft.layers[index + 1].layer_type === layer.layer_type;
          const reorderable = canMoveEarlier || canMoveLater;
          const dropClass = dropTarget?.index === index ? ` builder-layer-card--drop-${dropTarget.edge}` : "";
          return (
            <article className={`builder-layer-card${dropClass}`} key={`${layer.layer_type}-${index}`} aria-label={layerLabel(layer)} onDragOver={(event) => handleDragOver(index, event)} onDrop={(event) => handleDrop(index, event)}>
              <div className="builder-layer-card__header">
                <div>
                  {reorderable ? (
                    <span
                      className="builder-layer-card__drag"
                      draggable
                      onDragStart={(event) => handleDragStart(index, event)}
                      onDragEnd={handleDragEnd}
                      title="Drag to reorder"
                      aria-hidden="true"
                    >
                      ⠿
                    </span>
                  ) : (
                    <span className="builder-layer-card__drag builder-layer-card__drag--placeholder" aria-hidden="true">⠿</span>
                  )}
                  <span className="builder-layer-card__index">{String(index + 1).padStart(2, "0")}</span>
                  <h3>{layer.name}</h3>
                  <p>{layer.role.replace(/_/g, " ")} · <code>{layer.layer_type}</code>{layer.preset_id ? ` · copied from ${layer.preset_id}` : ""}</p>
                  {layer.layer_type === "perovskite" && perovskiteIncomplete ? (
                    <p className="builder-layer-card__warning">Perovskite process incomplete — open “Edit complete layer values” and fill in every vacuum stage.</p>
                  ) : layer.layer_type !== "perovskite" && incompleteLayers.has(index) ? (
                    <p className="builder-layer-card__warning">Layer values incomplete — open “Edit complete layer values” and fill in the missing process or solution values.</p>
                  ) : null}
                </div>
                <div className="button-row">
                  <button type="button" className="button button--secondary button--small" disabled={!canMoveEarlier} aria-label={`Move ${layer.name} up`} onClick={() => apply(() => moveLayerWithinRole(draft, index, -1))}>↑</button>
                  <button type="button" className="button button--secondary button--small" disabled={!canMoveLater} aria-label={`Move ${layer.name} down`} onClick={() => apply(() => moveLayerWithinRole(draft, index, 1))}>↓</button>
                  <button type="button" className="button button--secondary button--small" onClick={() => apply(() => removeLayer(draft, index))}>Remove</button>
                </div>
              </div>
              <details className="builder-layer-card__editor">
                <summary>Edit complete layer values</summary>
                <div className="builder-fields builder-fields--two">
                  <label className="builder-field"><span>Layer name</span><input className="text-input" value={layer.name} onChange={(event) => onChange(replacePrimaryLayer(draft, index, { ...layer, name: event.target.value }))} /></label>
                  <label className="builder-field"><span>Replace from same-type preset</span>
                    <select className="text-input" value="" onChange={(event) => { const preset = replacementPresets.find((item) => String(item.id) === event.target.value); if (preset) apply(() => expandLayerPreset(draft, index, preset)); }}>
                      <option value="">Keep current expanded values</option>
                      {replacementPresets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name} · revision {preset.current_revision_number}</option>)}
                    </select>
                  </label>
                </div>
                <SolutionEditor idPrefix={`layer-${index}`} solution={layer.solution} materials={materials} onChange={(solution) => onChange(replacePrimaryLayer(draft, index, { ...layer, solution }))} />
                {layer.layer_type === "perovskite" ? (
                  <PerovskiteProcessEditor process={draft.deposition_process} materials={materials} vcdValves={valves} onChange={(process) => onChange(replacePrimaryProcess(draft, process))} />
                ) : (
                  <LayerProcessEditor layerType={layer.layer_type} process={layer.process} materials={materials} onChange={(process) => onChange(replacePrimaryLayer(draft, index, { ...layer, process }))} />
                )}
              </details>
            </article>
          );
        })}
      </div>

    </section>
  );
}
