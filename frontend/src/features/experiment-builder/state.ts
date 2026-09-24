import type {
  AnnealStep,
  Baseline,
  DeviceLayer,
  DeviceLayout,
  DeviceRecipe,
  LayerPreset,
  PerovskiteDepositionProcess,
  SpinStep,
} from "../../types/api";
import type {
  BuilderCondition,
  BuilderPlanType,
  ExperimentCreatePayload,
  ExperimentDraft,
} from "./types";

const ROLE_ORDER = [
  "htl",
  "buried_interface_modifier",
  "perovskite",
  "top_passivation",
  "etl",
  "top_electrode",
];

const NIP_ROLE_ORDER = [
  "etl",
  "buried_interface_modifier",
  "perovskite",
  "top_passivation",
  "htl",
  "top_electrode",
];

function roleOrder(architecture: string): string[] {
  return architecture === "nip" ? NIP_ROLE_ORDER : ROLE_ORDER;
}

const TYPE_ORDER: Record<string, string[]> = {
  htl: ["niox", "sam"],
  buried_interface_modifier: ["buried_interface", "sio2_np"],
  perovskite: ["perovskite"],
  top_passivation: ["passivation", "peai", "edadi"],
  etl: ["pcbm", "c60", "bcp", "sno2"],
  top_electrode: ["ag"],
};

const UNIQUE_TYPES = new Set(["perovskite", "c60", "bcp", "sno2", "ag"]);

/** Layer types a student can add from scratch, with display names and the
 * deposition role that fixes their position in the device stack. Mirrors the
 * backend's DeviceLayer.layer_type / LAYER_ROLE_BY_TYPE. */
export const LAYER_TYPE_DEFS: readonly { layerType: string; label: string; role: string }[] = [
  { layerType: "niox", label: "NiOx", role: "htl" },
  { layerType: "sam", label: "SAM", role: "htl" },
  { layerType: "buried_interface", label: "Buried interface", role: "buried_interface_modifier" },
  { layerType: "sio2_np", label: "SiO₂ nanoparticle", role: "buried_interface_modifier" },
  { layerType: "perovskite", label: "Perovskite", role: "perovskite" },
  { layerType: "passivation", label: "Passivation", role: "top_passivation" },
  { layerType: "peai", label: "PEAI", role: "top_passivation" },
  { layerType: "edadi", label: "EDADI", role: "top_passivation" },
  { layerType: "pcbm", label: "PCBM", role: "etl" },
  { layerType: "c60", label: "C60", role: "etl" },
  { layerType: "bcp", label: "BCP", role: "etl" },
  { layerType: "sno2", label: "SnO2", role: "etl" },
  { layerType: "ag", label: "Ag", role: "top_electrode" },
];

function clone<T>(value: T): T {
  return structuredClone(value);
}

function blankProcess(): PerovskiteDepositionProcess {
  return {
    method: "spin_coating_vcd",
    spin_steps: [],
    vcd_stages: [],
    gas_backfill_stages: [],
    vcd_step_sequence: [],
    anneal_steps: [],
  };
}

export function createBlankDraft(): ExperimentDraft {
  return {
    campaign_id: "",
    source_baseline_version_id: null,
    source_baseline_name: null,
    setup_mode: "blank",
    junction_type: "single_junction",
    perovskite_bandgap: "normal_bandgap",
    architecture: "pin",
    substrate: {
      material: "",
      vendor: "",
      type_number: "",
      width_mm: 0,
      length_mm: 0,
    },
    layers: [],
    deposition_process: blankProcess(),
    plan_type: "comparative",
    conditions: [],
  };
}

function makeCondition(
  kind: BuilderCondition["kind"],
  groupId: string,
  name: string,
  layers: DeviceLayer[],
  process: PerovskiteDepositionProcess,
  layout: DeviceLayout,
  substrateCount = 3,
): BuilderCondition {
  return {
    group_id: groupId,
    kind,
    name,
    layers: clone(layers),
    deposition_process: clone(process),
    device_layout_code: layout.code,
    planned_substrate_count: substrateCount,
  };
}

export function expandBaseline(
  draft: ExperimentDraft,
  baseline: Baseline,
  layout: DeviceLayout,
): ExperimentDraft {
  if (baseline.status !== "active" || baseline.deposition_process === null) {
    throw new Error("Only an active baseline with a complete deposition process can be expanded.");
  }
  const recipe = clone(baseline.device_recipe);
  const process = clone(baseline.deposition_process);
  const planType: BuilderPlanType = recipe.experimental_groups.some((group) => group.kind === "standalone")
    ? "standalone"
    : "comparative";
  const conditions = planType === "standalone"
    ? [makeCondition("standalone", "standalone", "Standalone condition", recipe.layers, process, layout, recipe.experimental_groups[0]?.substrate_count ?? 3)]
    : [
        makeCondition("control", "control", "Control", recipe.layers, process, layout, recipe.experimental_groups.find((group) => group.kind === "control")?.substrate_count ?? 3),
        ...recipe.experimental_groups
          .filter((group) => group.kind === "target")
          .map((group, index) => makeCondition(
            "target",
            group.group_id || `target-${index + 1}`,
            group.name || `Target ${index + 1}`,
            group.layers ?? recipe.layers,
            group.deposition_process ?? process,
            layout,
            group.substrate_count ?? 3,
          )),
      ];
  if (planType === "comparative" && conditions.length === 1) {
    conditions.push(makeCondition("target", "target-1", "Target 1", recipe.layers, process, layout));
  }
  return {
    ...clone(draft),
    source_baseline_version_id: baseline.current_version_id,
    source_baseline_name: baseline.name,
    setup_mode: "baseline",
    junction_type: recipe.junction_type,
    perovskite_bandgap: recipe.perovskite_bandgap,
    architecture: recipe.architecture ?? "pin",
    substrate: clone(recipe.substrate),
    layers: clone(recipe.layers),
    deposition_process: process,
    plan_type: planType,
    conditions,
  };
}

function validateLayerAddition(layers: DeviceLayer[], layer: DeviceLayer): void {
  if (UNIQUE_TYPES.has(layer.layer_type) && layers.some((existing) => existing.layer_type === layer.layer_type)) {
    throw new Error(`${layer.name || layer.layer_type} may appear only once in the device stack.`);
  }
  if (
    (layer.layer_type === "bcp" && layers.some((existing) => existing.layer_type === "sno2"))
    || (layer.layer_type === "sno2" && layers.some((existing) => existing.layer_type === "bcp"))
  ) {
    throw new Error("The device stack must contain exactly one of BCP or SnO2.");
  }
}

function insertLayerInOrder(layers: DeviceLayer[], layer: DeviceLayer, architecture: string = "pin"): DeviceLayer[] {
  const order = roleOrder(architecture);
  const next = clone(layers);
  const roleIndex = order.indexOf(layer.role);
  const typeIndex = TYPE_ORDER[layer.role]?.indexOf(layer.layer_type) ?? 0;
  let insertionIndex = next.length;
  for (let index = 0; index < next.length; index += 1) {
    const existing = next[index];
    const existingRoleIndex = order.indexOf(existing.role);
    const existingTypeIndex = TYPE_ORDER[existing.role]?.indexOf(existing.layer_type) ?? 0;
    if (existingRoleIndex > roleIndex || (existingRoleIndex === roleIndex && existingTypeIndex > typeIndex)) {
      insertionIndex = index;
      break;
    }
  }
  next.splice(insertionIndex, 0, layer);
  return next;
}

function syncPrimary(draft: ExperimentDraft, layers: DeviceLayer[], process = draft.deposition_process): ExperimentDraft {
  const conditions = draft.conditions.map((condition, index) => index === 0
    ? { ...condition, layers: clone(layers), deposition_process: clone(process) }
    : condition);
  return { ...draft, layers, deposition_process: process, conditions };
}

export function replacePrimaryLayer(
  draft: ExperimentDraft,
  layerIndex: number,
  replacement: DeviceLayer,
): ExperimentDraft {
  if (!draft.layers[layerIndex]) {
    throw new Error("Unknown layer index.");
  }
  const layers = draft.layers.map((layer, index) => index === layerIndex ? clone(replacement) : clone(layer));
  return syncPrimary(draft, layers);
}

export function replacePrimaryProcess(
  draft: ExperimentDraft,
  process: PerovskiteDepositionProcess,
): ExperimentDraft {
  return syncPrimary(draft, clone(draft.layers), clone(process));
}

export function applyDeviceLayout(draft: ExperimentDraft, layout: DeviceLayout): ExperimentDraft {
  const width = Number(layout.substrate_width_mm);
  const length = Number(layout.substrate_length_mm);
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(length) || length <= 0) {
    throw new Error("The selected device layout has invalid substrate dimensions.");
  }
  let conditions = draft.conditions.map((condition) => ({
    ...condition,
    device_layout_code: layout.code,
  }));
  if (conditions.length === 0) {
    const base = {
      layers: clone(draft.layers),
      deposition_process: clone(draft.deposition_process),
      device_layout_code: layout.code,
      planned_substrate_count: 3,
    };
    conditions = draft.plan_type === "standalone"
      ? [{ ...base, group_id: "standalone", kind: "standalone", name: "Standalone condition" }]
      : [
          { ...clone(base), group_id: "control", kind: "control", name: "Control" },
          { ...clone(base), group_id: "target-1", kind: "target", name: "Target 1" },
        ];
  }
  return {
    ...draft,
    substrate: { ...draft.substrate, width_mm: width, length_mm: length },
    conditions,
  };
}

export function addLayer(draft: ExperimentDraft, preset: LayerPreset): ExperimentDraft {
  if (preset.status !== "active") {
    throw new Error("Only an active layer preset can be expanded.");
  }
  const layer = clone(preset.layer);
  layer.preset_id = preset.preset_key;
  validateLayerAddition(draft.layers, layer);
  const layers = insertLayerInOrder(draft.layers, layer, draft.architecture);
  const process = layer.layer_type === "perovskite"
    ? (preset.deposition_process ? clone(preset.deposition_process) : blankProcess())
    : draft.deposition_process;
  return syncPrimary(draft, layers, process);
}

/**
 * Whether `layerType` may still be added to this stack: unique types appear
 * once, and BCP/SnO2 are mutually exclusive. Used to filter the blank-layer
 * picker; `addBlankLayer` re-checks and throws as a backstop.
 */
export function canAddLayerType(draft: ExperimentDraft, layerType: string): boolean {
  if (!LAYER_TYPE_DEFS.some((definition) => definition.layerType === layerType)) {
    return false;
  }
  if (UNIQUE_TYPES.has(layerType) && draft.layers.some((existing) => existing.layer_type === layerType)) {
    return false;
  }
  if (layerType === "bcp" && draft.layers.some((existing) => existing.layer_type === "sno2")) {
    return false;
  }
  if (layerType === "sno2" && draft.layers.some((existing) => existing.layer_type === "bcp")) {
    return false;
  }
  return true;
}

/**
 * Add an empty layer of `layerType` to be filled in by hand — solution and
 * process start blank and are completed through "Edit complete layer values".
 * Presets remain the shortcut; this is the from-scratch path that also lets
 * the very first layer (and baseline) be authored without any preset.
 */
export function addBlankLayer(draft: ExperimentDraft, layerType: string): ExperimentDraft {
  const definition = LAYER_TYPE_DEFS.find((item) => item.layerType === layerType);
  if (!definition) {
    throw new Error("Unknown layer type.");
  }
  const layer: DeviceLayer = {
    layer_type: definition.layerType,
    role: definition.role,
    name: definition.label,
    preset_id: null,
    solution: null,
    process: null,
  };
  validateLayerAddition(draft.layers, layer);
  const layers = insertLayerInOrder(draft.layers, layer, draft.architecture);
  return syncPrimary(draft, layers);
}

export function expandLayerPreset(
  draft: ExperimentDraft,
  layerIndex: number,
  preset: LayerPreset,
): ExperimentDraft {
  if (preset.status !== "active") {
    throw new Error("Only an active layer preset can be expanded.");
  }
  if (!draft.layers[layerIndex]) {
    throw new Error("Unknown layer index.");
  }
  const layer = clone(preset.layer);
  layer.preset_id = preset.preset_key;
  const remaining = draft.layers.filter((_, index) => index !== layerIndex);
  validateLayerAddition(remaining, layer);
  const layers = insertLayerInOrder(remaining, layer, draft.architecture);
  const process = layer.layer_type === "perovskite"
    ? (preset.deposition_process ? clone(preset.deposition_process) : blankProcess())
    : draft.deposition_process;
  return syncPrimary(draft, layers, process);
}

export function replaceLayer(draft: ExperimentDraft, layerIndex: number, replacement: DeviceLayer): ExperimentDraft {
  if (!draft.layers[layerIndex]) {
    throw new Error("Unknown layer index.");
  }
  const remaining = draft.layers.filter((_, index) => index !== layerIndex);
  validateLayerAddition(remaining, replacement);
  return syncPrimary(draft, insertLayerInOrder(remaining, clone(replacement), draft.architecture));
}

export function moveLayerWithinRole(draft: ExperimentDraft, layerIndex: number, direction: -1 | 1): ExperimentDraft {
  const targetIndex = layerIndex + direction;
  const layer = draft.layers[layerIndex];
  const target = draft.layers[targetIndex];
  if (!layer || !target) {
    throw new Error("The layer cannot be moved beyond the device stack.");
  }
  if (layer.role !== target.role) {
    throw new Error("Layers can move only within the same functional role.");
  }
  if (layer.layer_type !== target.layer_type) {
    throw new Error("Different materials must retain the required order within their functional role.");
  }
  const layers = clone(draft.layers);
  [layers[layerIndex], layers[targetIndex]] = [layers[targetIndex], layers[layerIndex]];
  return syncPrimary(draft, layers);
}

/**
 * Whether a drag-and-drop move from `from` to `to` is a legal reordering.
 * Reordering is constrained to the same role + layer_type group, so every
 * layer between the two positions must match the moved layer; cross-type
 * boundaries keep the required device order and are never reorderable.
 */
export function canReorderLayers(draft: ExperimentDraft, from: number, to: number): boolean {
  if (from === to) {
    return false;
  }
  if (from < 0 || from >= draft.layers.length || to < 0 || to >= draft.layers.length) {
    return false;
  }
  const moved = draft.layers[from];
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  for (let index = lo; index <= hi; index++) {
    const current = draft.layers[index];
    if (current.role !== moved.role || current.layer_type !== moved.layer_type) {
      return false;
    }
  }
  return true;
}

/**
 * Move a layer to a new position via drag-and-drop. Like moveLayerWithinRole,
 * reordering is constrained to the same role + layer_type group; a drop across
 * a role/type boundary is a silent no-op (the caller does not surface an error
 * for an invalid drop target).
 */
export function reorderLayer(draft: ExperimentDraft, from: number, to: number): ExperimentDraft {
  if (!canReorderLayers(draft, from, to)) {
    return draft;
  }
  const layers = clone(draft.layers);
  const [extracted] = layers.splice(from, 1);
  layers.splice(to, 0, extracted);
  return syncPrimary(draft, layers);
}

export function removeLayer(draft: ExperimentDraft, layerIndex: number): ExperimentDraft {
  if (!draft.layers[layerIndex]) {
    throw new Error("Unknown layer index.");
  }
  return syncPrimary(
    draft,
    draft.layers.filter((_, index) => index !== layerIndex).map((item) => clone(item)),
  );
}

export function replaceCondition(draft: ExperimentDraft, conditionIndex: number, replacement: BuilderCondition): ExperimentDraft {
  if (!draft.conditions[conditionIndex]) {
    throw new Error("Unknown condition index.");
  }
  return {
    ...draft,
    conditions: draft.conditions.map((condition, index) => index === conditionIndex ? clone(replacement) : condition),
  };
}

export function addTargetCondition(draft: ExperimentDraft): ExperimentDraft {
  if (draft.plan_type !== "comparative") {
    throw new Error("Targets can be added only to a comparative plan.");
  }
  if (draft.conditions.length >= 21) {
    throw new Error("An experiment may contain at most 21 conditions.");
  }
  const usedIds = new Set(draft.conditions.map((condition) => condition.group_id));
  let number = 1;
  while (usedIds.has(`target-${number}`)) {
    number += 1;
  }
  const source = draft.conditions[0];
  const target: BuilderCondition = {
    group_id: `target-${number}`,
    kind: "target",
    name: `Target ${number}`,
    layers: clone(source?.layers ?? draft.layers),
    deposition_process: clone(source?.deposition_process ?? draft.deposition_process),
    device_layout_code: source?.device_layout_code ?? "",
    planned_substrate_count: source?.planned_substrate_count ?? 3,
  };
  return { ...draft, conditions: [...draft.conditions.map((condition) => clone(condition)), target] };
}

export function removeTargetCondition(draft: ExperimentDraft, conditionIndex: number): ExperimentDraft {
  const condition = draft.conditions[conditionIndex];
  if (!condition || condition.kind !== "target") {
    throw new Error("Only a target condition can be removed.");
  }
  const targetCount = draft.conditions.filter((item) => item.kind === "target").length;
  if (targetCount <= 1) {
    throw new Error("A comparative plan requires at least one target condition.");
  }
  return {
    ...draft,
    conditions: draft.conditions
      .filter((_, index) => index !== conditionIndex)
      .map((item) => clone(item)),
  };
}

export function setPlanType(draft: ExperimentDraft, planType: BuilderPlanType): ExperimentDraft {
  if (planType === draft.plan_type) {
    return clone(draft);
  }
  const layoutCode = draft.conditions[0]?.device_layout_code ?? "";
  const substrateCount = draft.conditions[0]?.planned_substrate_count ?? 3;
  const base = {
    layers: clone(draft.layers),
    deposition_process: clone(draft.deposition_process),
    device_layout_code: layoutCode,
    planned_substrate_count: substrateCount,
  };
  return {
    ...draft,
    plan_type: planType,
    conditions: planType === "standalone"
      ? [{ ...base, group_id: "standalone", kind: "standalone", name: "Standalone condition" }]
      : [
          { ...clone(base), group_id: "control", kind: "control", name: "Control" },
          { ...clone(base), group_id: "target-1", kind: "target", name: "Target 1" },
        ],
  };
}

export interface PlanTypeChangeImpact {
  /** True when the switch would discard condition-specific edits. */
  destructive: boolean;
  /** Human-readable summary of which edits each condition would lose. */
  discardedSummaries: string[];
}

/**
 * Pure preview of a plan-type switch: reports which condition-specific edits
 * (relative to the shared layer stack / perovskite process the rebuilt
 * conditions start from) would be discarded. Never mutates the draft.
 */
export function planTypeChangeImpact(
  draft: ExperimentDraft,
  planType: BuilderPlanType,
): PlanTypeChangeImpact {
  if (planType === draft.plan_type) {
    return { destructive: false, discardedSummaries: [] };
  }
  const sharedLayers = JSON.stringify(draft.layers);
  const sharedProcess = JSON.stringify(draft.deposition_process);
  const baseLayout = draft.conditions[0]?.device_layout_code ?? "";
  const baseCount = draft.conditions[0]?.planned_substrate_count ?? 3;
  const discardedSummaries: string[] = [];
  for (const condition of draft.conditions) {
    const parts: string[] = [];
    if (JSON.stringify(condition.layers) !== sharedLayers) {
      parts.push("layer stack");
    }
    if (JSON.stringify(condition.deposition_process) !== sharedProcess) {
      parts.push("perovskite process");
    }
    if (condition.device_layout_code !== baseLayout) {
      parts.push("device layout");
    }
    if (condition.planned_substrate_count !== baseCount) {
      parts.push("substrate count");
    }
    if (parts.length > 0) {
      discardedSummaries.push(
        `${condition.name || condition.group_id}: ${parts.join(", ")}`,
      );
    }
  }
  return { destructive: discardedSummaries.length > 0, discardedSummaries };
}

export function materializeConditionPlans(draft: ExperimentDraft): ExperimentCreatePayload["condition_plans"] {
  return draft.conditions.map((condition) => ({
    group_id: condition.group_id,
    role: condition.kind,
    device_layout_code: condition.device_layout_code,
    planned_substrate_count: condition.planned_substrate_count,
  }));
}

function spinFields(steps: SpinStep[]): Record<string, number | null> {
  const names = ["cast", "spread", "thin", "stage4"];
  return Object.fromEntries(names.flatMap((name, index) => {
    const step = steps[index];
    return [
      [`spin_${name}_rpm`, step?.rpm ?? null],
      [`spin_${name}_seconds`, step?.seconds ?? null],
      [`spin_${name}_acceleration_rpm_per_s`, step?.acceleration_rpm_per_s ?? null],
    ];
  }));
}

function vcdFields(process: PerovskiteDepositionProcess): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (let index = 1; index <= 5; index += 1) {
    const stage = process.vcd_stages[index - 1];
    values[`vcd_stage${index}_valve`] = stage?.valve ?? null;
    values[`vcd_stage${index}_pressure_pa`] = stage?.pressure_pa ?? null;
    values[`vcd_stage${index}_seconds`] = stage?.seconds ?? null;
    const backfill = process.gas_backfill_stages[index - 1];
    values[`gas_backfill_stage${index}_gas`] = backfill?.gas ?? null;
    values[`gas_backfill_stage${index}_flow_sccm`] = backfill?.flow_sccm ?? null;
    values[`gas_backfill_stage${index}_target_pressure_pa`] = backfill?.target_pressure_pa ?? null;
    values[`gas_backfill_stage${index}_hold_seconds`] = backfill?.hold_seconds ?? null;
  }
  return values;
}

function annealFields(steps: AnnealStep[]): Record<string, number | null> {
  const values: Record<string, number | null> = {};
  for (let index = 1; index <= 2; index += 1) {
    const step = steps[index - 1];
    values[`anneal_stage${index}_temperature_c`] = step?.temperature_c ?? null;
    values[`anneal_stage${index}_seconds`] = step?.seconds ?? null;
  }
  return values;
}

function experimentalGroups(draft: ExperimentDraft): DeviceRecipe["experimental_groups"] {
  return draft.conditions.map((condition) => {
    if (condition.kind === "standalone") {
      return {
        group_id: condition.group_id,
        kind: "standalone",
        name: condition.name,
        change_from_control: "",
        inherits_control: false,
        adjustments: [],
        layers: null,
        deposition_process: null,
        substrate_count: condition.planned_substrate_count,
      };
    }
    if (condition.kind === "control") {
      return {
        group_id: condition.group_id,
        kind: "control",
        name: condition.name,
        change_from_control: "Baseline fabrication procedure",
        inherits_control: false,
        adjustments: [],
        layers: null,
        deposition_process: null,
        substrate_count: condition.planned_substrate_count,
      };
    }
    return {
      group_id: condition.group_id,
      kind: "target",
      name: condition.name,
      change_from_control: "Complete independently editable target snapshot",
      inherits_control: false,
      adjustments: [],
      layers: clone(condition.layers),
      deposition_process: clone(condition.deposition_process),
      substrate_count: condition.planned_substrate_count,
    };
  });
}

/**
 * Switch the device architecture (pin/nip) and re-sort the layer stack to the
 * new deposition role order. Within-role material order is preserved.
 */
export function setArchitecture(draft: ExperimentDraft, architecture: "pin" | "nip"): ExperimentDraft {
  if (draft.architecture === architecture) {
    return draft;
  }
  const order = roleOrder(architecture);
  const sorted = [...draft.layers].sort((left, right) => {
    const leftRole = order.indexOf(left.role);
    const rightRole = order.indexOf(right.role);
    if (leftRole !== rightRole) {
      return leftRole - rightRole;
    }
    const leftType = TYPE_ORDER[left.role]?.indexOf(left.layer_type) ?? 0;
    const rightType = TYPE_ORDER[right.role]?.indexOf(right.layer_type) ?? 0;
    return leftType - rightType;
  });
  return syncPrimary({ ...draft, architecture }, clone(sorted));
}

export function toExperimentPayload(draft: ExperimentDraft): ExperimentCreatePayload {
  const deviceRecipe: DeviceRecipe = {
    schema_version: 2,
    setup_mode: draft.setup_mode,
    junction_type: draft.junction_type,
    perovskite_bandgap: draft.perovskite_bandgap,
    architecture: draft.architecture,
    experimental_groups: experimentalGroups(draft),
    substrate: clone(draft.substrate),
    layers: clone(draft.layers),
  };
  return {
    campaign_id: draft.campaign_id,
    source_baseline_version_id: draft.source_baseline_version_id,
    recipe: {
      ...spinFields(draft.deposition_process.spin_steps),
      ...vcdFields(draft.deposition_process),
      vcd_step_sequence: [...(draft.deposition_process.vcd_step_sequence ?? [])],
      ...annealFields(draft.deposition_process.anneal_steps),
      device_stack: null,
      fabrication_context: null,
      device_recipe: deviceRecipe,
    },
    condition_plans: materializeConditionPlans(draft),
  };
}
