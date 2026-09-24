import { describe, expect, it } from "vitest";
import type { Baseline, DeviceLayout, LayerPreset } from "../../types/api";
import {
  addTargetCondition,
  addBlankLayer,
  addLayer,
  canAddLayerType,
  applyDeviceLayout,
  createBlankDraft,
  expandBaseline,
  expandLayerPreset,
  materializeConditionPlans,
  moveLayerWithinRole,
  planTypeChangeImpact,
  removeLayer,
  reorderLayer,
  removeTargetCondition,
  replaceCondition,
  replacePrimaryLayer,
  replacePrimaryProcess,
  setArchitecture,
  setPlanType,
  toExperimentPayload,
} from "./state";

const spinProcess = {
  method: "spin_coating_vcd" as const,
  spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
  vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
  gas_backfill_stages: [],
  vcd_step_sequence: ["vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
};

const layers = [
  { layer_type: "niox", role: "htl", name: "NiOx", preset_id: "niox-spin", solution: null, process: { method: "spin_coating", spin_steps: [{ rpm: 4000, seconds: 30, acceleration_rpm_per_s: 2000 }], anneal_steps: [] } },
  { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: "pvk", solution: null, process: null },
  { layer_type: "c60", role: "etl", name: "C60", preset_id: "c60", solution: null, process: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.2 } },
  { layer_type: "sno2", role: "etl", name: "SnO2", preset_id: "sno2", solution: null, process: { method: "ald", thickness_nm: 20, substrate_temperature_c: 80, cycles: 100 } },
  { layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: "ag", solution: null, process: { method: "thermal_evaporation", thickness_nm: 100, rate_angstrom_per_s: 1 } },
];

const baseline: Baseline = {
  id: 1,
  name: "Reference",
  status: "active",
  scope: "shared",
  owner_user_id: null,
  owner_display_name: null,
  promoted_by_user_id: null,
  promoted_by_display_name: null,
  promoted_at: null,
  promotion_note: null,
  promoted_version_id: null,
  device_recipe: {
    schema_version: 2,
    setup_mode: "baseline",
    junction_type: "single_junction",
    perovskite_bandgap: "normal_bandgap",
    architecture: "pin",
    experimental_groups: [
      { group_id: "control", kind: "control", name: "Control", change_from_control: "Baseline fabrication procedure", inherits_control: false, adjustments: [] },
      { group_id: "target-1", kind: "target", name: "Target 1", change_from_control: "", inherits_control: true, adjustments: [], layers: null, deposition_process: null },
    ],
    substrate: { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 },
    layers,
  },
  deposition_process: spinProcess,
  current_revision_number: 1,
  current_version_id: 10,
  canonical_hash: "a".repeat(64),
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-01T08:00:00Z",
};

const layout: DeviceLayout = {
  code: "15x15-6",
  version: 1,
  substrate_width_mm: "15",
  substrate_length_mm: "15",
  devices_per_substrate: 6,
  device_active_area_cm2: "0.09",
  total_active_area_cm2: "0.54",
  description: "Six devices",
};

function preset(id: number, layer: LayerPreset["layer"]): LayerPreset {
  return {
    id,
    preset_key: `preset-${id}`,
    name: layer.name,
    status: "active",
    scope: "shared",
    layer,
    deposition_process: layer.layer_type === "perovskite" ? spinProcess : null,
    current_revision_number: 1,
    current_version_id: id + 100,
    canonical_hash: String(id).repeat(64).slice(0, 64),
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-01T08:00:00Z",
  };
}

describe("experiment builder state", () => {
  it("expands a baseline as an independent complete draft", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    draft.layers[0].name = "Edited NiOx";
    draft.conditions[1].layers[0].name = "Edited target NiOx";

    expect(baseline.device_recipe.layers[0].name).toBe("NiOx");
    expect(draft.layers[0].name).toBe("Edited NiOx");
    expect(draft.conditions[0].layers[0].name).toBe("NiOx");
    expect(draft.conditions[1].layers[0].name).toBe("Edited target NiOx");
    expect(draft.source_baseline_version_id).toBe(10);
  });

  it("expands a layer preset without retaining shared object references", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    const sam = preset(2, {
      layer_type: "sam",
      role: "htl",
      name: "2PACz",
      preset_id: "catalog-sam",
      solution: { formulation_type: "weighed_solids", stock_dispersion: "", stock_volume_ml: null, solids: [{ chemical: "2PACz", weight_mg: 1 }], solvents: [{ solvent: "ethanol", volume_ml: 1 }] },
      process: { method: "spin_coating", spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [] },
    });
    const next = addLayer(draft, sam);

    expect(next.layers.map((layer) => layer.layer_type)).toEqual(["niox", "sam", "perovskite", "c60", "sno2", "ag"]);
    next.layers[1].solution!.solids[0].weight_mg = 2;
    expect(sam.layer.solution!.solids[0].weight_mg).toBe(1);
    expect(next.layers[1].preset_id).toBe("preset-2");
  });

  it("preserves NiOx process variants and rejects unique-layer duplicates", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    const sputteredNiOx = preset(3, {
      layer_type: "niox",
      role: "htl",
      name: "Sputtered NiOx",
      preset_id: "niox-sputter",
      solution: null,
      process: { method: "sputtering", sputter_mode: "rf", power_w: 80, pressure_pa: 2, gas1: "Ar", gas1_flow_sccm: 20, gas2: "O2", gas2_flow_sccm: 1, duration_seconds: 600 },
    });
    const withVariant = expandLayerPreset(draft, 0, sputteredNiOx);
    expect(withVariant.layers[0].process?.method).toBe("sputtering");

    expect(() => addLayer(draft, preset(4, layers[2]))).toThrow(/C60 may appear only once/i);
    expect(() => addLayer(draft, preset(5, { ...layers[3], layer_type: "bcp", name: "BCP" }))).toThrow(/exactly one of BCP or SnO2/i);
  });

  it("adds blank layers from scratch in device order and rejects illegal additions", () => {
    const draft = createBlankDraft();
    expect(canAddLayerType(draft, "ag")).toBe(true);
    const withAg = addBlankLayer(draft, "ag");
    expect(withAg.layers).toHaveLength(1);
    expect(withAg.layers[0]).toMatchObject({ layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: null, solution: null, process: null });

    // Layers are placed by role even when added out of order.
    const withPerovskite = addBlankLayer(withAg, "perovskite");
    expect(withPerovskite.layers.map((layer) => layer.layer_type)).toEqual(["perovskite", "ag"]);

    // Unique types cannot be added twice, and BCP/SnO2 are exclusive.
    expect(canAddLayerType(withAg, "ag")).toBe(false);
    expect(() => addBlankLayer(withAg, "ag")).toThrow(/Ag may appear only once/i);
    const withSnO2 = addBlankLayer(withPerovskite, "sno2");
    expect(canAddLayerType(withSnO2, "bcp")).toBe(false);
    expect(() => addBlankLayer(withSnO2, "bcp")).toThrow(/exactly one of BCP or SnO2/i);
  });

  it("moves only within a functional role and removes by immutable copy", () => {
    const secondNiOx = preset(2, { layer_type: "niox", role: "htl", name: "Second NiOx", preset_id: "niox-2", solution: null, process: { method: "spin_coating", spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [] } });
    const draft = addLayer(expandBaseline(createBlankDraft(), baseline, layout), secondNiOx);
    const moved = moveLayerWithinRole(draft, 1, -1);
    expect(moved.layers.slice(0, 2).map((layer) => layer.name)).toEqual(["Second NiOx", "NiOx"]);
    expect(() => moveLayerWithinRole(moved, 1, 1)).toThrow(/functional role/i);
    const removed = removeLayer(moved, 0);
    expect(removed.layers[0].layer_type).toBe("niox");
    expect(moved.layers[0].name).toBe("Second NiOx");
  });

  it("reorders same-type layers by drag and ignores cross-type drops", () => {
    const secondNiOx = preset(2, { layer_type: "niox", role: "htl", name: "Second NiOx", preset_id: "niox-2", solution: null, process: { method: "spin_coating", spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [] } });
    const draft = addLayer(expandBaseline(createBlankDraft(), baseline, layout), secondNiOx);
    // Drag the second NiOx (index 1) above the first (index 0): same type, valid.
    const reordered = reorderLayer(draft, 1, 0);
    expect(reordered.layers.slice(0, 2).map((layer) => layer.name)).toEqual(["Second NiOx", "NiOx"]);
    // A drop across a role/type boundary (onto the perovskite slot) is a no-op.
    const noop = reorderLayer(draft, 1, 2);
    expect(noop.layers.map((layer) => layer.name)).toEqual(draft.layers.map((layer) => layer.name));
  });

  it("re-sorts the layer stack when switching architecture pin -> nip", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    expect(draft.architecture).toBe("pin");
    expect(draft.layers.map((layer) => layer.layer_type)).toEqual(["niox", "perovskite", "c60", "sno2", "ag"]);

    const nip = setArchitecture(draft, "nip");
    expect(nip.architecture).toBe("nip");
    // nip order: ETL (c60, sno2) -> perovskite -> HTL (niox) -> electrode (ag)
    expect(nip.layers.map((layer) => layer.layer_type)).toEqual(["c60", "sno2", "perovskite", "niox", "ag"]);
  });

  it("converts between comparative and standalone plans with independent target snapshots", () => {
    const comparative = expandBaseline(createBlankDraft(), baseline, layout);
    const editedTarget = replaceCondition(comparative, 1, {
      ...comparative.conditions[1],
      name: "Target interface",
      layers: comparative.conditions[1].layers.map((layer, index) => index === 0 ? { ...layer, name: "Target NiOx" } : layer),
    });
    expect(editedTarget.conditions[0].layers[0].name).toBe("NiOx");
    expect(editedTarget.conditions[1].layers[0].name).toBe("Target NiOx");

    const standalone = setPlanType(editedTarget, "standalone");
    expect(standalone.conditions).toHaveLength(1);
    expect(standalone.conditions[0].kind).toBe("standalone");
    const comparativeAgain = setPlanType(standalone, "comparative");
    expect(comparativeAgain.conditions.map((condition) => condition.kind)).toEqual(["control", "target"]);
    comparativeAgain.conditions[1].layers[0].name = "Independent target";
    expect(comparativeAgain.conditions[0].layers[0].name).toBe("NiOx");
  });

  it("materializes explicit condition plans and a complete reconstructible payload", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    draft.campaign_id = "interface-2026";
    draft.layers[0].name = "Edited";
    const plans = materializeConditionPlans(draft);
    const payload = toExperimentPayload(draft);

    expect(plans).toEqual([
      { group_id: "control", role: "control", device_layout_code: "15x15-6", planned_substrate_count: 3 },
      { group_id: "target-1", role: "target", device_layout_code: "15x15-6", planned_substrate_count: 3 },
    ]);
    expect(payload.recipe.device_recipe.layers[0].name).toBe("Edited");
    expect(payload.recipe.device_recipe.experimental_groups[1].layers?.[0].name).toBe("NiOx");
    expect(payload.recipe.device_recipe.experimental_groups[1].deposition_process).toEqual(spinProcess);
    expect(payload.recipe.spin_cast_rpm).toBe(3000);
    expect(payload.recipe.vcd_stage1_valve).toBe("VV02");
    expect(payload.source_baseline_version_id).toBe(10);
  });

  it("applies one device layout to substrate dimensions and every condition", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    const wider = { ...layout, code: "20x20-8", substrate_width_mm: "20", substrate_length_mm: "20" };
    const next = applyDeviceLayout(draft, wider);

    expect(next.substrate.width_mm).toBe(20);
    expect(next.substrate.length_mm).toBe(20);
    expect(next.conditions.every((condition) => condition.device_layout_code === "20x20-8")).toBe(true);
  });

  it("adds and removes independently editable comparative targets", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    const added = addTargetCondition(draft);
    added.conditions[2].layers[0].name = "Second target NiOx";

    expect(added.conditions.map((condition) => condition.group_id)).toEqual(["control", "target-1", "target-2"]);
    expect(added.conditions[0].layers[0].name).toBe("NiOx");
    expect(removeTargetCondition(added, 2).conditions).toHaveLength(2);
  });

  it("syncs primary edits only to control while preserving target snapshots", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    const layerEdited = replacePrimaryLayer(draft, 0, { ...draft.layers[0], name: "Control NiOx" });
    const processEdited = replacePrimaryProcess(layerEdited, {
      ...layerEdited.deposition_process,
      spin_steps: [{ rpm: 4000, seconds: 20, acceleration_rpm_per_s: 1200 }],
    });

    expect(processEdited.conditions[0].layers[0].name).toBe("Control NiOx");
    expect(processEdited.conditions[1].layers[0].name).toBe("NiOx");
    expect(processEdited.conditions[0].deposition_process.spin_steps[0].rpm).toBe(4000);
    expect(processEdited.conditions[1].deposition_process.spin_steps[0].rpm).toBe(3000);
  });

  it("resets the perovskite process to blank when a null-process preset is applied", () => {
    const draft = expandBaseline(createBlankDraft(), baseline, layout);
    // Seed a non-blank process so that inheriting the old draft process
    // (the bug) would be detectable.
    const withProcess = replacePrimaryProcess(draft, spinProcess);
    expect(withProcess.deposition_process).toEqual(spinProcess);

    const nullProcessPreset = preset(7, layers[1]);
    nullProcessPreset.deposition_process = null;
    const next = expandLayerPreset(withProcess, 1, nullProcessPreset);

    expect(next.deposition_process).toEqual({
      method: "spin_coating_vcd",
      spin_steps: [],
      vcd_stages: [],
      gas_backfill_stages: [],
      vcd_step_sequence: [],
      anneal_steps: [],
    });
  });

  it("planTypeChangeImpact reports nothing destructive without condition edits", () => {
    const draft = setPlanType(setPlanType(createBlankDraft(), "standalone"), "comparative");
    const impact = planTypeChangeImpact(draft, "standalone");
    expect(impact.destructive).toBe(false);
    expect(impact.discardedSummaries).toEqual([]);
  });

  it("planTypeChangeImpact reports which condition-specific edits a switch discards", () => {
    const base = setPlanType(createBlankDraft(), "standalone");
    base.layers = [
      {
        layer_type: "etl",
        role: "etl",
        name: "ETL",
        preset_id: null,
        solution: null,
        process: null,
      },
    ];
    const draft = setPlanType(base, "comparative");
    const target = draft.conditions.find((item) => item.kind === "target");
    if (!target) throw new Error("expected a target condition");
    target.layers = [
      {
        layer_type: "htl",
        role: "htl",
        name: "Edited HTL",
        preset_id: null,
        solution: null,
        process: null,
      },
    ];
    target.deposition_process = {
      ...target.deposition_process,
      anneal_steps: [{ temperature_c: 120, seconds: 600 }],
    };
    const impact = planTypeChangeImpact(draft, "standalone");
    expect(impact.destructive).toBe(true);
    expect(impact.discardedSummaries).toHaveLength(1);
    expect(impact.discardedSummaries[0]).toMatch(/Target 1/);
    expect(impact.discardedSummaries[0]).toMatch(/layer stack/);
    expect(impact.discardedSummaries[0]).toMatch(/perovskite process/);
  });

  it("planTypeChangeImpact is a pure preview and never mutates the draft", () => {
    const draft = setPlanType(setPlanType(createBlankDraft(), "standalone"), "comparative");
    const before = JSON.stringify(draft);
    planTypeChangeImpact(draft, "standalone");
    planTypeChangeImpact(draft, "comparative");
    expect(JSON.stringify(draft)).toBe(before);
    // Switching to the current type is never destructive.
    expect(planTypeChangeImpact(draft, "comparative").destructive).toBe(false);
  });
});
