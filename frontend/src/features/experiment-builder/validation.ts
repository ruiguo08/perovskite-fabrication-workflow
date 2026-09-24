import type { DeviceLayer, PerovskiteDepositionProcess } from "../../types/api";
import { VCD_VALVES, isNonNegativeNumber, isPositiveNumber } from "../../lib/constraints";
import type { DraftIssue, ExperimentDraft } from "./types";

/**
 * Mirrors the backend's authoritative `_validate_layer_method` mapping in
 * src/perovskite_bo/device_recipe.py. Frontend copy exists only for immediate
 * editor feedback; the backend rejects mismatches at save time.
 */
export const ALLOWED_LAYER_METHODS: Record<string, string[]> = {
  niox: ["spin_coating", "sputtering"],
  sam: ["spin_coating"],
  buried_interface: ["spin_coating"],
  sio2_np: ["spin_coating"],
  passivation: ["spin_coating"],
  peai: ["spin_coating"],
  edadi: ["spin_coating"],
  pcbm: ["spin_coating"],
  c60: ["thermal_evaporation"],
  bcp: ["thermal_evaporation"],
  sno2: ["ald"],
  ag: ["thermal_evaporation"],
};

export function completeLayer(layer: DeviceLayer, index: number, issues: DraftIssue[], basePath = "layers"): void {
  const path = `${basePath}.${index}`;
  if (!layer.name.trim()) {
    issues.push({ path: `${path}.name`, message: "Enter a layer name." });
  }
  const process = layer.process;
  if (layer.layer_type !== "perovskite" && process === null) {
    issues.push({ path: `${path}.process`, message: `${layer.name} requires a layer process.` });
  }
  if (process && !(ALLOWED_LAYER_METHODS[layer.layer_type] ?? []).includes(process.method)) {
    issues.push({ path: `${path}.process.method`, message: `${layer.name} does not support ${process.method.replace(/_/g, " ")}.` });
  }
  const needsSolution = layer.layer_type === "perovskite" || process?.method === "spin_coating";
  if (needsSolution && layer.solution === null) {
    issues.push({ path: `${path}.solution`, message: `${layer.name} requires a solution formulation.` });
  }
  if (!needsSolution && layer.solution !== null) {
    issues.push({ path: `${path}.solution`, message: `${layer.name} does not use a solution formulation with ${process?.method?.replace(/_/g, " ") ?? "this process"}.` });
  }
  if (layer.solution) {
    if (layer.solution.formulation_type === "diluted_dispersion") {
      if (!layer.solution.stock_dispersion.trim() || !layer.solution.stock_volume_ml) {
        issues.push({ path: `${path}.solution`, message: `${layer.name} requires a stock dispersion name and volume.` });
      }
    } else {
      if (layer.solution.solids.length === 0) {
        issues.push({ path: `${path}.solution.solids`, message: `${layer.name} requires at least one solid ingredient.` });
      } else if (layer.solution.solids.some((solid) => !solid.chemical.trim() || !solid.weight_mg)) {
        issues.push({ path: `${path}.solution.solids`, message: `${layer.name} has an incomplete solid ingredient.` });
      }
    }
    if (layer.solution.solvents.length === 0) {
      issues.push({ path: `${path}.solution.solvents`, message: `${layer.name} requires at least one solvent.` });
    } else if (layer.solution.solvents.some((solvent) => !solvent.solvent.trim() || !solvent.volume_ml)) {
      issues.push({ path: `${path}.solution.solvents`, message: `${layer.name} has an incomplete solvent ingredient.` });
    }
  }
  completeLayerProcess(process, issues, `${path}.process`, layer.name);
}

/**
 * Process-stage completeness checks shared by draft validation and the layer
 * process editor's inline "what is missing" list.
 */
export function completeLayerProcess(
  process: DeviceLayer["process"],
  issues: DraftIssue[],
  basePath: string,
  label: string,
): void {
  if (process?.method === "spin_coating") {
    if (!process.spin_steps || process.spin_steps.length < 1 || process.spin_steps.length > 3) {
      issues.push({ path: `${basePath}.spin_steps`, message: `${label} requires one to three spin stages.` });
    } else if (process.spin_steps.some((step) => !isPositiveNumber(step.rpm) || !isPositiveNumber(step.seconds) || !isPositiveNumber(step.acceleration_rpm_per_s))) {
      issues.push({ path: `${basePath}.spin_steps`, message: `${label} has an incomplete spin step.` });
    }
    if (process.anneal_steps?.some((step) => !isPositiveNumber(step.temperature_c) || !isPositiveNumber(step.seconds))) {
      issues.push({ path: `${basePath}.anneal_steps`, message: `${label} has an incomplete annealing stage.` });
    }
  }
  if (process?.method === "sputtering") {
    if (!isPositiveNumber(process.power_w) || !isPositiveNumber(process.pressure_pa) || !(process.gas1 ?? "").trim() || !isPositiveNumber(process.gas1_flow_sccm) || !isPositiveNumber(process.duration_seconds)) {
      issues.push({ path: `${basePath}`, message: `${label} has an incomplete sputtering process.` });
    }
    if (Boolean(process.gas2) !== Boolean(process.gas2_flow_sccm)) {
      issues.push({ path: `${basePath}.gas2`, message: `${label} requires gas 2 and its flow rate together.` });
    }
  }
  if (process?.method === "thermal_evaporation" && (!isPositiveNumber(process.thickness_nm) || !isPositiveNumber(process.rate_angstrom_per_s))) {
    issues.push({ path: `${basePath}`, message: `${label} has an incomplete thermal-evaporation process.` });
  }
  if (process?.method === "ald" && (!isPositiveNumber(process.thickness_nm) || !isPositiveNumber(process.substrate_temperature_c) || !isPositiveNumber(process.cycles))) {
    issues.push({ path: `${basePath}`, message: `${label} has an incomplete ALD process.` });
  }
}

export function completeDepositionProcess(
  process: PerovskiteDepositionProcess,
  issues: DraftIssue[],
  path = "deposition_process",
  spinLabel = "perovskite",
  valves: readonly string[] = VCD_VALVES,
): void {
  if (process.spin_steps.length < 1 || process.spin_steps.length > 4) {
    issues.push({ path: `${path}.spin_steps`, message: `Record one to four complete ${spinLabel} spin stages.` });
  } else if (process.spin_steps.some((step) => !isPositiveNumber(step.rpm) || !isPositiveNumber(step.seconds) || !isPositiveNumber(step.acceleration_rpm_per_s))) {
    issues.push({ path: `${path}.spin_steps`, message: `Every ${spinLabel} spin stage must be complete.` });
  }
  if (process.vcd_stages.length < 1 || process.vcd_stages.length > 5) {
    issues.push({ path: `${path}.vcd_stages`, message: "Record one to five VCD evacuation stages." });
  } else if (process.vcd_stages.some((stage) => !valves.includes(stage.valve) || !isNonNegativeNumber(stage.pressure_pa) || !isNonNegativeNumber(stage.seconds))) {
    issues.push({ path: `${path}.vcd_stages`, message: "Every VCD evacuation stage must be complete." });
  }
  if (process.gas_backfill_stages.length > 5) {
    issues.push({ path: `${path}.gas_backfill_stages`, message: "Record at most five gas-backfill stages." });
  } else if (process.gas_backfill_stages.some((stage) =>
    !stage.gas.trim()
    || !isPositiveNumber(stage.flow_sccm)
    || !isNonNegativeNumber(stage.target_pressure_pa)
    || !isNonNegativeNumber(stage.hold_seconds),
  )) {
    issues.push({ path: `${path}.gas_backfill_stages`, message: "Every gas-backfill stage must be complete." });
  }
  if (process.anneal_steps.length < 1 || process.anneal_steps.length > 2) {
    issues.push({ path: `${path}.anneal_steps`, message: "Record one or two complete annealing stages." });
  } else if (process.anneal_steps.some((stage) => !isPositiveNumber(stage.temperature_c) || !isPositiveNumber(stage.seconds))) {
    issues.push({ path: `${path}.anneal_steps`, message: "Every annealing stage must be complete." });
  }
  const expectedSequenceLength = process.vcd_stages.length + process.gas_backfill_stages.length;
  if ((process.vcd_step_sequence ?? []).length !== expectedSequenceLength) {
    issues.push({ path: `${path}.vcd_step_sequence`, message: "The VCD sequence must include every evacuation and gas-backfill stage exactly once." });
  } else {
    const expected = new Set([
      ...process.vcd_stages.map((_, index) => `vcd_stage${index + 1}`),
      ...process.gas_backfill_stages.map((_, index) => `gas_backfill_stage${index + 1}`),
    ]);
    const actual = process.vcd_step_sequence ?? [];
    if (new Set(actual).size !== expected.size || actual.some((entry) => !expected.has(entry))) {
      issues.push({ path: `${path}.vcd_step_sequence`, message: "The VCD sequence must include every evacuation and gas-backfill stage exactly once." });
    }
  }
}

export function validateDraft(
  draft: ExperimentDraft,
  options: { vcdValves?: readonly string[] } = {},
): DraftIssue[] {
  const valves = options.vcdValves ?? VCD_VALVES;
  const issues: DraftIssue[] = [];
  if (!draft.campaign_id.trim()) {
    issues.push({ path: "campaign_id", message: "Select an active Campaign." });
  }
  if (!draft.substrate.material.trim()) {
    issues.push({ path: "substrate.material", message: "Select a substrate material from the reusable directory." });
  }
  if (!draft.substrate.vendor.trim()) {
    issues.push({ path: "substrate.vendor", message: "Select a substrate supplier product." });
  }
  if (!draft.substrate.type_number.trim()) {
    issues.push({ path: "substrate.type_number", message: "Select a substrate catalog number." });
  }
  if (draft.substrate.width_mm <= 0 || draft.substrate.length_mm <= 0) {
    issues.push({ path: "substrate.dimensions", message: "Record positive substrate dimensions." });
  }
  if (draft.layers.length === 0) {
    issues.push({ path: "layers", message: "Add the complete functional layer stack." });
  } else {
    const roles = new Set(draft.layers.map((layer) => layer.role));
    for (const role of ["htl", "perovskite", "etl", "top_electrode"]) {
      if (!roles.has(role)) {
        issues.push({ path: "layers", message: `The device stack requires a ${role.replace(/_/g, " ")} layer.` });
      }
    }
    if (!draft.layers.some((layer) => layer.layer_type === "c60")) {
      issues.push({ path: "layers", message: "The ETL stack requires C60." });
    }
    const transportCount = draft.layers.filter((layer) => layer.layer_type === "bcp" || layer.layer_type === "sno2").length;
    if (transportCount !== 1) {
      issues.push({ path: "layers", message: "The ETL stack requires exactly one of BCP or SnO2." });
    }
    draft.layers.forEach((layer, index) => completeLayer(layer, index, issues));
  }
  completeDepositionProcess(draft.deposition_process, issues, "deposition_process", "perovskite", valves);
  if (draft.conditions.length === 0) {
    issues.push({ path: "conditions", message: "Create the required standalone or comparative conditions." });
  } else {
    draft.conditions.forEach((condition, index) => {
      if (!condition.device_layout_code) {
        issues.push({ path: `conditions.${index}.device_layout_code`, message: `${condition.name} requires a device layout.` });
      }
      if (!isPositiveNumber(condition.planned_substrate_count)) {
        issues.push({ path: `conditions.${index}.planned_substrate_count`, message: `${condition.name} requires at least one substrate.` });
      }
      if (condition.kind === "target") {
        if (condition.layers.length === 0) {
          issues.push({ path: `conditions.${index}.layers`, message: `${condition.name} requires a complete independent layer stack.` });
        } else {
          condition.layers.forEach((layer, layerIndex) => completeLayer(layer, layerIndex, issues, `conditions.${index}.layers`));
        }
        completeDepositionProcess(condition.deposition_process, issues, `conditions.${index}.deposition_process`, `${condition.name.toLowerCase()} perovskite`, valves);
      }
    });
  }
  return issues;
}

/**
 * Baseline authoring validation: a baseline must store a complete Control
 * reference recipe (substrate, every layer's expanded solution and process,
 * and the Perovskite deposition process snapshot). This mirrors the backend
 * ``_baseline_values`` contract without experiment-plan bookkeeping such as
 * campaigns, conditions, or a saved-baseline source.
 */
export function validateBaselineDraft(
  draft: ExperimentDraft,
  vcdValves?: readonly string[],
): DraftIssue[] {
  const issues: DraftIssue[] = [];
  if (!draft.substrate.material.trim()) {
    issues.push({ path: "substrate.material", message: "Select a substrate material from the reusable directory." });
  }
  if (!draft.substrate.vendor.trim()) {
    issues.push({ path: "substrate.vendor", message: "Select a substrate supplier product." });
  }
  if (!draft.substrate.type_number.trim()) {
    issues.push({ path: "substrate.type_number", message: "Select a substrate catalog number." });
  }
  if (draft.substrate.width_mm <= 0 || draft.substrate.length_mm <= 0) {
    issues.push({ path: "substrate.dimensions", message: "Record positive substrate dimensions." });
  }
  if (draft.layers.length === 0) {
    issues.push({ path: "layers", message: "Add the complete functional layer stack." });
  } else {
    draft.layers.forEach((layer, index) => completeLayer(layer, index, issues));
  }
  // A baseline always stores a complete Perovskite deposition process snapshot
  // (BaselinePayload.deposition_process is required on the backend), so validate
  // it regardless of whether a perovskite layer is present in the draft.
  completeDepositionProcess(draft.deposition_process, issues, "deposition_process", "perovskite", vcdValves ?? VCD_VALVES);
  return issues;
}
