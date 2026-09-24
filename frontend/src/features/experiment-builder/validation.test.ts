import { describe, expect, it } from "vitest";
import { createBlankDraft } from "./state";
import { validateBaselineDraft, validateDraft } from "./validation";

describe("experiment builder guidance validation", () => {
  it("allows planning from scratch without a baseline reference", () => {
    const issues = validateDraft(createBlankDraft());
    expect(issues.find((issue) => issue.path === "source_baseline")).toBeUndefined();
  });

  it("reports missing catalog-backed substrate and planning values", () => {
    const draft = createBlankDraft();
    draft.source_baseline_version_id = 1;
    const issues = validateDraft(draft);
    expect(issues.map((issue) => issue.path)).toEqual(expect.arrayContaining([
      "campaign_id",
      "substrate.material",
      "substrate.vendor",
      "substrate.type_number",
      "layers",
      "deposition_process.spin_steps",
      "conditions",
    ]));
  });

  it("reports incomplete process stages and target snapshots", () => {
    const draft = createBlankDraft();
    draft.campaign_id = "interface-2026";
    draft.source_baseline_version_id = 1;
    draft.substrate = { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 };
    draft.layers = [
      { layer_type: "niox", role: "htl", name: "NiOx", preset_id: null, solution: null, process: { method: "spin_coating", spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [] } },
      { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: null, solution: null, process: null },
      { layer_type: "c60", role: "etl", name: "C60", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.2 } },
      { layer_type: "bcp", role: "etl", name: "BCP", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 8, rate_angstrom_per_s: 0.2 } },
      { layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 100, rate_angstrom_per_s: 1 } },
    ];
    draft.deposition_process = {
      method: "spin_coating_vcd",
      spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
      vcd_stages: [{ valve: "", pressure_pa: null, seconds: null }],
      gas_backfill_stages: [{ gas: "N2", flow_sccm: null, target_pressure_pa: 500, hold_seconds: 400 }],
      vcd_step_sequence: ["vcd_stage1", "gas_backfill_stage1"],
      anneal_steps: [{ temperature_c: 100, seconds: null }],
    };
    draft.conditions = [
      { group_id: "control", kind: "control", name: "Control", layers: structuredClone(draft.layers), deposition_process: structuredClone(draft.deposition_process), device_layout_code: "15x15-6", planned_substrate_count: 3 },
      { group_id: "target-1", kind: "target", name: "Target", layers: [], deposition_process: { ...structuredClone(draft.deposition_process), spin_steps: [] }, device_layout_code: "15x15-6", planned_substrate_count: 3 },
    ];

    const messages = validateDraft(draft).map((issue) => issue.message);
    expect(messages).toEqual(expect.arrayContaining([
      "Every VCD evacuation stage must be complete.",
      "Every gas-backfill stage must be complete.",
      "Every annealing stage must be complete.",
      "Target requires a complete independent layer stack.",
      "Record one to four complete target perovskite spin stages.",
    ]));
  });

  it("aligns layer solution and process guidance with backend completeness rules", () => {
    const draft = createBlankDraft();
    draft.layers = [
      { layer_type: "niox", role: "htl", name: "NiOx", preset_id: null, solution: null, process: { method: "spin_coating", spin_steps: [], anneal_steps: [] } },
      { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: null, solution: { formulation_type: "weighed_solids", stock_dispersion: "", stock_volume_ml: null, solids: [], solvents: [] }, process: null },
      { layer_type: "c60", role: "etl", name: "C60", preset_id: null, solution: { formulation_type: "weighed_solids", stock_dispersion: "", stock_volume_ml: null, solids: [], solvents: [] }, process: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.2 } },
      { layer_type: "bcp", role: "etl", name: "BCP", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 8, rate_angstrom_per_s: 0.2 } },
      { layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 100, rate_angstrom_per_s: 1 } },
    ];

    const messages = validateDraft(draft).map((issue) => issue.message);
    expect(messages).toEqual(expect.arrayContaining([
      "NiOx requires a solution formulation.",
      "NiOx requires one to three spin stages.",
      "Perovskite requires at least one solid ingredient.",
      "Perovskite requires at least one solvent.",
      "C60 does not use a solution formulation with thermal evaporation.",
    ]));
  });

  it("flags negative and non-finite spin values the backend would reject", () => {
    const draft = createBlankDraft();
    draft.campaign_id = "interface-2026";
    draft.source_baseline_version_id = 1;
    draft.substrate = { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 };
    draft.layers = [
      { layer_type: "niox", role: "htl", name: "NiOx", preset_id: null, solution: null, process: { method: "spin_coating", spin_steps: [{ rpm: -1000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [] } },
      { layer_type: "perovskite", role: "perovskite", name: "Perovskite", preset_id: null, solution: null, process: null },
      { layer_type: "c60", role: "etl", name: "C60", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 20, rate_angstrom_per_s: 0.2 } },
      { layer_type: "bcp", role: "etl", name: "BCP", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 8, rate_angstrom_per_s: 0.2 } },
      { layer_type: "ag", role: "top_electrode", name: "Ag", preset_id: null, solution: null, process: { method: "thermal_evaporation", thickness_nm: 100, rate_angstrom_per_s: 1 } },
    ];
    draft.deposition_process = {
      method: "spin_coating_vcd",
      spin_steps: [{ rpm: Number("1e999"), seconds: 30, acceleration_rpm_per_s: 1000 }],
      vcd_stages: [{ valve: "VV02", pressure_pa: 100, seconds: 5 }],
      gas_backfill_stages: [],
      vcd_step_sequence: ["vcd_stage1"],
      anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
    };
    draft.conditions = [
      { group_id: "control", kind: "control", name: "Control", layers: structuredClone(draft.layers), deposition_process: structuredClone(draft.deposition_process), device_layout_code: "15x15-6", planned_substrate_count: 3 },
    ];

    const messages = validateDraft(draft).map((issue) => issue.message);
    expect(messages).toEqual(expect.arrayContaining([
      "NiOx has an incomplete spin step.",
      "Every perovskite spin stage must be complete.",
    ]));
  });

  it("flags VCD stages with an unknown valve", () => {
    const draft = createBlankDraft();
    draft.deposition_process = {
      method: "spin_coating_vcd",
      spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
      vcd_stages: [{ valve: "VV09", pressure_pa: 100, seconds: 5 }],
      gas_backfill_stages: [],
      vcd_step_sequence: ["vcd_stage1"],
      anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
    };
    const messages = validateDraft(draft).map((issue) => issue.message);
    expect(messages).toContain("Every VCD evacuation stage must be complete.");
  });

  it("accepts server-provided valves outside the local fallback list", () => {
    const draft = createBlankDraft();
    draft.deposition_process = {
      method: "spin_coating_vcd",
      spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }],
      vcd_stages: [{ valve: "VV07", pressure_pa: 100, seconds: 5 }],
      gas_backfill_stages: [],
      vcd_step_sequence: ["vcd_stage1"],
      anneal_steps: [{ temperature_c: 100, seconds: 1800 }],
    };
    // Without the server list the stage is incomplete...
    expect(validateDraft(draft).map((issue) => issue.message))
      .toContain("Every VCD evacuation stage must be complete.");
    // ...but a valve served by /api/editor-config is authoritative.
    const messages = validateDraft(draft, { vcdValves: ["VV07"] })
      .map((issue) => issue.message);
    expect(messages).not.toContain("Every VCD evacuation stage must be complete.");
  });

  it("validates the baseline deposition process even without a perovskite layer", () => {
    const draft = createBlankDraft();
    draft.layers = [
      { layer_type: "niox", role: "htl", name: "NiOx", preset_id: null, solution: { formulation_type: "weighed_solids", stock_dispersion: "", stock_volume_ml: null, solids: [{ chemical: "NiOx", weight_mg: 1 }], solvents: [{ solvent: "water", volume_ml: 1 }] }, process: { method: "spin_coating", spin_steps: [{ rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 }], anneal_steps: [{ temperature_c: 100, seconds: 1800 }] } },
    ];
    draft.deposition_process = {
      method: "spin_coating_vcd",
      spin_steps: [],
      vcd_stages: [],
      gas_backfill_stages: [],
      vcd_step_sequence: [],
      anneal_steps: [],
    };
    const messages = validateBaselineDraft(draft).map((issue) => issue.message);
    expect(messages).toEqual(expect.arrayContaining([
      "Record one to four complete perovskite spin stages.",
      "Record one to five VCD evacuation stages.",
      "Record one or two complete annealing stages.",
    ]));
  });
});
