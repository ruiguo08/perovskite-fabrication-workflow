import { describe, expect, it } from "vitest";
import type { PerovskiteDepositionProcess } from "../../types/api";
import { processFromUnified, unifiedFromProcess } from "./ProcessEditor";
import type { UnifiedStage } from "./ProcessEditor";

const base: PerovskiteDepositionProcess = {
  method: "spin_coating_vcd",
  spin_steps: [],
  vcd_stages: [],
  gas_backfill_stages: [],
  vcd_step_sequence: [],
  anneal_steps: [],
};

function evac(valve: string, pressure: number, seconds: number): UnifiedStage {
  return { kind: "evacuate", valve, pressure_pa: pressure, seconds, gas: "", flow_sccm: null, target_pressure_pa: null, hold_seconds: null };
}

function backfill(gas: string, flow: number, target: number, end: number): UnifiedStage {
  return { kind: "gas_backfill", valve: "VV02", pressure_pa: null, seconds: null, gas, flow_sccm: flow, target_pressure_pa: target, hold_seconds: end };
}

describe("vacuum and gas-backfill program round-trip", () => {
  it("preserves an interleaved evacuate -> backfill -> evacuate order", () => {
    const program = [evac("VV02", 100, 5), backfill("N2", 30, 15, 20), evac("VV03", 200, 8)];
    const process = processFromUnified(program, base);

    expect(process.vcd_step_sequence).toEqual(["vcd_stage1", "gas_backfill_stage1", "vcd_stage2"]);
    expect(process.vcd_stages).toEqual([
      { valve: "VV02", pressure_pa: 100, seconds: 5 },
      { valve: "VV03", pressure_pa: 200, seconds: 8 },
    ]);
    expect(process.gas_backfill_stages).toEqual([
      { gas: "N2", flow_sccm: 30, target_pressure_pa: 15, hold_seconds: 20 },
    ]);

    // Round-trip: process -> unified preserves the exact execution order.
    expect(unifiedFromProcess(process).map((stage) => stage.kind)).toEqual([
      "evacuate",
      "gas_backfill",
      "evacuate",
    ]);
  });

  it("keeps the exact sequence unchanged when a stage field is edited", () => {
    const program = [evac("VV02", 100, 5), backfill("N2", 30, 15, 20), evac("VV03", 200, 8)];
    const snapshot = processFromUnified(program, base);

    // Edit a field on the middle gas-backfill stage; the sequence must not move.
    const edited = processFromUnified(
      [program[0], { ...program[1], flow_sccm: 40 }, program[2]],
      snapshot,
    );
    expect(edited.vcd_step_sequence).toEqual(["vcd_stage1", "gas_backfill_stage1", "vcd_stage2"]);
    expect(edited.gas_backfill_stages[0].flow_sccm).toBe(40);
  });

  it("renumbers the sequence correctly after a stage is removed", () => {
    const program = [evac("VV02", 100, 5), backfill("N2", 30, 15, 20), evac("VV03", 200, 8), evac("VV06", 300, 10)];
    // Remove the gas-backfill stage; the remaining evacuates renumber 1..3.
    const process = processFromUnified(program.filter((_, index) => index !== 1), base);

    expect(process.vcd_step_sequence).toEqual(["vcd_stage1", "vcd_stage2", "vcd_stage3"]);
    expect(process.gas_backfill_stages).toEqual([]);
    expect(process.vcd_stages).toHaveLength(3);
  });

  it("imports a historical interleaved snapshot without reordering", () => {
    const saved: PerovskiteDepositionProcess = {
      ...base,
      vcd_stages: [
        { valve: "VV02", pressure_pa: 100, seconds: 5 },
        { valve: "VV03", pressure_pa: 200, seconds: 8 },
      ],
      gas_backfill_stages: [
        { gas: "N2", flow_sccm: 30, target_pressure_pa: 15, hold_seconds: 20 },
      ],
      vcd_step_sequence: ["vcd_stage1", "gas_backfill_stage1", "vcd_stage2"],
    };

    const program = unifiedFromProcess(saved);
    expect(program.map((stage) => stage.kind)).toEqual(["evacuate", "gas_backfill", "evacuate"]);
    expect(program[0]).toMatchObject({ valve: "VV02", pressure_pa: 100, seconds: 5 });
    expect(program[1]).toMatchObject({ gas: "N2", flow_sccm: 30 });
    expect(program[2]).toMatchObject({ valve: "VV03", pressure_pa: 200, seconds: 8 });

    // Re-serializing yields the identical stored snapshot (full round-trip).
    expect(processFromUnified(program, saved).vcd_step_sequence).toEqual(saved.vcd_step_sequence);
  });
});
