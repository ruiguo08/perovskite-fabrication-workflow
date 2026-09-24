import { describe, expect, it } from "vitest";
import { validateTargetLayersObject, validateTargetProcessObject } from "./snapshotValidation";

describe("target snapshot JSON validation", () => {
  it("rejects layer entries that would crash review validation", () => {
    expect(validateTargetLayersObject({ layers: [null] })).not.toBeNull();
    expect(validateTargetLayersObject({ layers: [{ name: "NiOx", role: "htl", layer_type: "niox", solution: { formulation_type: "weighed_solids", solids: [null], solvents: [] }, process: null }] })).not.toBeNull();
  });

  it("accepts a structurally safe complete-layer container", () => {
    expect(validateTargetLayersObject({
      layers: [{
        name: "C60",
        role: "etl",
        layer_type: "c60",
        solution: null,
        process: { method: "thermal_evaporation" },
      }],
    })).toBeNull();
  });

  it("rejects malformed stage and sequence containers", () => {
    expect(validateTargetProcessObject({
      method: "spin_coating_vcd",
      spin_steps: [null],
      vcd_stages: [],
      gas_backfill_stages: [],
      anneal_steps: [],
    })).not.toBeNull();
    expect(validateTargetProcessObject({
      method: "spin_coating_vcd",
      spin_steps: [],
      vcd_stages: [],
      gas_backfill_stages: [],
      anneal_steps: [],
      vcd_step_sequence: "vcd_stage1",
    })).not.toBeNull();
  });
});
