import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConditionComparison } from "./ConditionComparison";
import type { Condition } from "../types/api";

const substrate = { material: "ITO", vendor: "Ossila", type_number: "S111", width_mm: 15, length_mm: 15 };

const perovskiteSolution = {
  formulation_type: "weighed_solids" as const,
  stock_dispersion: "",
  stock_volume_ml: null,
  solids: [{ chemical: "PbI2", weight_mg: 461 }],
  solvents: [{ solvent: "DMF", volume_ml: 0.8 }],
};

function perovskiteLayer() {
  return {
    layer_type: "perovskite",
    role: "perovskite",
    name: "Perovskite",
    preset_id: null,
    solution: perovskiteSolution,
    process: null,
  };
}

function transportLayer(powerW: number) {
  return {
    layer_type: "transport",
    role: "hole_transport",
    name: "Spiro",
    preset_id: null,
    solution: null,
    process: { method: "sputtering", sputter_mode: "rf", power_w: powerW, pressure_pa: 0.5 },
  };
}

const controlProcess = {
  method: "spin_coating_vcd" as const,
  spin_steps: [
    { rpm: 1000, seconds: 10, acceleration_rpm_per_s: 500 },
    { rpm: 4000, seconds: 30, acceleration_rpm_per_s: 1000 },
  ],
  vcd_stages: [
    { valve: "VV02", pressure_pa: 200, seconds: 60 },
    { valve: "VV03", pressure_pa: 500, seconds: 120 },
  ],
  gas_backfill_stages: [],
  vcd_step_sequence: ["spin_step1", "vcd_stage1"],
  anneal_steps: [{ temperature_c: 100, seconds: 3600 }],
};

function snapshot(spinStep2Rpm: number, annealTemperatureC: number, layers: ReturnType<typeof perovskiteLayer | typeof transportLayer>[]) {
  return {
    schema_version: 3,
    device: {
      schema_version: 2,
      setup_mode: "baseline",
      junction_type: "single_junction",
      perovskite_bandgap: "normal_bandgap",
      tandem_type: null,
      substrate,
      layers,
    },
    deposition_process: {
      ...controlProcess,
      spin_steps: controlProcess.spin_steps.map((step, index) =>
        index === 1 ? { ...step, rpm: spinStep2Rpm } : step,
      ),
      anneal_steps: [{ temperature_c: annealTemperatureC, seconds: 3600 }],
    },
  };
}

function makeCondition(id: number, role: string, name: string, snapshotBody: ReturnType<typeof snapshot>): Condition {
  return {
    id,
    experiment_id: 7,
    role,
    condition_code: `interface-2026-v7-${role.toUpperCase().slice(0, 1)}`,
    condition_name: name,
    recipe_snapshot: snapshotBody,
    recipe_schema_version: 3,
    canonical_hash: "d".repeat(64),
    source_baseline_version_id: null,
    device_layout_code: "15x15-6",
    device_layout_snapshot: { code: "15x15-6", devices_per_substrate: 6 },
    planned_substrate_count: 3,
    expected_device_count: 18,
    requires_manual_review: false,
    created_at: "2026-08-01T08:00:00Z",
  } as Condition;
}

// Control: two layers (perovskite + transport). Target: drops the transport
// layer, raises spin step 2 to 5000 rpm, and anneals at 110 °C.
const conditions = [
  makeCondition(1, "control", "Control", snapshot(4000, 100, [perovskiteLayer(), transportLayer(80)])),
  makeCondition(2, "target", "Target A", snapshot(5000, 110, [perovskiteLayer()])),
];

function group(title: string): HTMLDetailsElement {
  const element = screen.getByText(title).closest("details");
  expect(element).not.toBeNull();
  return element!;
}

describe("ConditionComparison", () => {
  it("orders groups by device stack with the perovskite process inside its layer", () => {
    render(<ConditionComparison conditions={conditions} />);

    const summaries = screen
      .getAllByRole("group")
      .map((details) => details.querySelector("summary")?.textContent ?? "");
    expect(summaries).toEqual([
      expect.stringContaining("Device"),
      expect.stringContaining("1 · Perovskite"),
      expect.stringContaining("2 · Spiro"),
    ]);

    const perovskite = group("1 · Perovskite");
    const rowLabels = within(perovskite).getAllByRole("row").map((row) => row.textContent ?? "");
    expect(rowLabels.join("\n")).toContain("Spin step 1");
    expect(rowLabels.join("\n")).toContain("VCD stage 1");
    expect(rowLabels.join("\n")).toContain("Anneal step 1");
  });

  it("opens layers with differences and highlights the differing cells against the control", () => {
    render(<ConditionComparison conditions={conditions} />);

    const perovskite = group("1 · Perovskite");
    expect(perovskite).toHaveAttribute("open");
    expect(within(perovskite).getByText("2 differences")).toBeInTheDocument();

    const spinRow = within(perovskite).getByText("Spin step 2").closest("tr");
    const spinCells = within(spinRow!).getAllByRole("cell");
    expect(spinCells[0]).toHaveTextContent("4000 rpm · 30 s · 1000 rpm/s");
    expect(spinCells[1]).toHaveTextContent("5000 rpm · 30 s · 1000 rpm/s");
    expect(spinCells[0]).toHaveClass("condition-comparison__cell--shared");
    expect(spinCells[1]).toHaveClass("condition-comparison__cell--diff");

    // The target dropped the transport layer: the missing cell reads as an
    // em dash highlighted as a difference.
    const spiro = group("2 · Spiro");
    expect(spiro).toHaveAttribute("open");
    const missingCells = within(within(spiro).getByText("Name").closest("tr")!).getAllByRole("cell");
    expect(missingCells[0]).toHaveTextContent("Spiro (hole transport · transport)");
    expect(missingCells[1]).toHaveTextContent("—");
    expect(missingCells[1]).toHaveClass("condition-comparison__cell--diff");
  });

  it("keeps identical layers collapsed and marked identical", () => {
    const identicalConditions = [
      makeCondition(1, "control", "Control", snapshot(4000, 100, [perovskiteLayer(), transportLayer(80)])),
      makeCondition(2, "target", "Target B", snapshot(4000, 100, [perovskiteLayer(), transportLayer(80)])),
    ];
    render(<ConditionComparison conditions={identicalConditions} />);

    for (const title of ["Device", "1 · Perovskite", "2 · Spiro"]) {
      const element = group(title);
      expect(element).not.toHaveAttribute("open");
      expect(within(element).getByText("identical")).toBeInTheDocument();
    }
  });

  it("dims values shared with the control inside open layers", () => {
    render(<ConditionComparison conditions={conditions} />);

    const perovskite = group("1 · Perovskite");
    const sharedCells = within(perovskite).getAllByRole("cell", {
      name: "1000 rpm · 10 s · 500 rpm/s",
    });
    expect(sharedCells.length).toBeGreaterThan(0);
    for (const cell of sharedCells) {
      expect(cell).toHaveClass("condition-comparison__cell--shared");
    }
  });
});
