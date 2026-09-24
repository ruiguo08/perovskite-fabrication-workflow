import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SnapshotEditor } from "./SnapshotEditor";
import type { EditorConfig } from "../types/api";

const editorConfig: EditorConfig = {
  vcd_valves: ["VV02", "VV03", "VV06", "Pudi"],
  max_solid_chemicals: 20,
  max_solvents: 10,
};

describe("SnapshotEditor", () => {
  it("renders scalar fields with unit suffixes from the field tables", () => {
    const snapshot = { method: "spin_coating", rpm: 3000, seconds: 30, acceleration_rpm_per_s: 1000 };
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={() => undefined} />);

    expect(screen.getByText("Speed (rpm)")).toBeInTheDocument();
    expect(screen.getByText("Duration (s)")).toBeInTheDocument();
    expect(screen.getByText("Acceleration (rpm/s)")).toBeInTheDocument();
    expect(screen.getByText("Method")).toBeInTheDocument();
    expect(screen.getByDisplayValue("spin_coating")).toHaveProperty("readOnly", true);
  });

  it("renders the method field read-only", () => {
    render(<SnapshotEditor snapshot={{ method: "vcd" }} editorConfig={editorConfig} onChange={() => undefined} />);
    expect(screen.getByDisplayValue("vcd")).toHaveProperty("readOnly", true);
  });

  it("normalizes the formulation when the type changes", () => {
    const snapshot = {
      formulation_type: "weighed_solids",
      stock_dispersion: "",
      stock_volume_ml: null,
      solids: [{ chemical: "Me-4PACz", weight_mg: 2 }],
      solvents: [{ solvent: "Ethanol", volume_ml: 1 }],
    };
    const emitted: Record<string, unknown>[] = [];
    const { rerender } = render(
      <SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />,
    );

    fireEvent.change(screen.getByLabelText("Formulation type"), { target: { value: "diluted_dispersion" } });
    rerender(<SnapshotEditor snapshot={emitted.at(-1) as Record<string, unknown>} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    expect(emitted.at(-1)).toMatchObject({
      formulation_type: "diluted_dispersion",
      solids: [],
      stock_dispersion: "",
      stock_volume_ml: null,
    });
    expect(screen.getByDisplayValue("Ethanol")).toBeInTheDocument();
    expect(screen.queryByText("Solid ingredients")).not.toBeInTheDocument();
  });

  it("keeps at least one solid when switching back to weighed solids", () => {
    const snapshot = {
      formulation_type: "weighed_solids",
      stock_dispersion: "",
      stock_volume_ml: null,
      solids: [{ chemical: "", weight_mg: null }],
      solvents: [{ solvent: "Ethanol", volume_ml: 1 }],
    };
    const emitted: Record<string, unknown>[] = [];
    const { rerender } = render(
      <SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />,
    );

    fireEvent.change(screen.getByLabelText("Formulation type"), { target: { value: "diluted_dispersion" } });
    const diluted = emitted.at(-1) as Record<string, unknown>;
    expect((diluted.solids as unknown[])).toHaveLength(0);
    rerender(<SnapshotEditor snapshot={diluted} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);
    fireEvent.change(screen.getByLabelText("Formulation type"), { target: { value: "weighed_solids" } });

    const last = emitted.at(-1) as Record<string, unknown>;
    expect((last.solids as { chemical: string }[])).toHaveLength(1);
    expect(last.stock_volume_ml).toBeNull();
  });

  it("enforces array bounds from editor config and defaults", () => {
    const snapshot = {
      method: "spin_coating",
      spin_steps: [{ rpm: 1000, seconds: 10, acceleration_rpm_per_s: 500 }],
    };
    const emitted: Record<string, unknown>[] = [];
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    const addStep = screen.getByRole("button", { name: "Add spin-coating step" });
    expect(addStep).not.toBeDisabled();
    const removeStep = screen.getByRole("button", { name: "Remove spin-coating step 1" });
    expect(removeStep).toBeDisabled(); // minimum of one step
    fireEvent.click(addStep);
    expect((emitted.at(-1) as { spin_steps: unknown[] }).spin_steps).toHaveLength(2);
  });

  it("emits numbers for numeric fields and null for cleared values", () => {
    const snapshot = { method: "sputtering", sputter_mode: "rf", power_w: 40, cycles: 100 };
    const emitted: Record<string, unknown>[] = [];
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    fireEvent.change(screen.getByLabelText("Power (W)"), { target: { value: "55.5" } });
    expect((emitted.at(-1) as { power_w: number }).power_w).toBe(55.5);
    fireEvent.change(screen.getByLabelText("Power (W)"), { target: { value: "" } });
    expect((emitted.at(-1) as { power_w: number | null }).power_w).toBeNull();
  });

  it("offers vcd valves from the editor config", () => {
    const snapshot = { method: "vcd", vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }], gas_backfill_stages: [] };
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={() => undefined} />);

    const select = screen.getByLabelText("Valve");
    const options = Array.from(select.querySelectorAll("option")).map((option) => option.textContent);
    expect(options).toEqual(expect.arrayContaining(["VV02", "VV03", "VV06", "Pudi"]));
  });

  it("syncs the vcd step sequence when stages are added and removed", () => {
    const snapshot = {
      method: "vcd",
      vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
      gas_backfill_stages: [],
      vcd_step_sequence: ["vcd_stage1"],
    };
    const emitted: Record<string, unknown>[] = [];
    const { rerender } = render(
      <SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Add evacuation stage" }));
    const afterAdd = emitted.at(-1) as {
      vcd_step_sequence: string[];
      vcd_stages: { valve: string; pressure_pa: number | null; seconds: number | null }[];
    };
    expect(afterAdd.vcd_step_sequence).toEqual(["vcd_stage1", "vcd_stage2"]);
    expect(afterAdd.vcd_stages).toEqual([
      { valve: "VV02", pressure_pa: 1000, seconds: 5 },
      { valve: "", pressure_pa: null, seconds: null },
    ]);
    rerender(<SnapshotEditor snapshot={afterAdd} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    fireEvent.click(screen.getByRole("button", { name: "Remove evacuation stage 1" }));
    const afterRemove = emitted.at(-1) as {
      vcd_step_sequence: string[];
      vcd_stages: { valve: string; pressure_pa: number | null; seconds: number | null }[];
    };
    expect(afterRemove.vcd_step_sequence).toEqual(["vcd_stage1"]);
    expect(afterRemove.vcd_stages).toEqual([
      { valve: "", pressure_pa: null, seconds: null },
    ]);
  });

  it("reorders the vcd step sequence with the move buttons", () => {
    const snapshot = {
      method: "vcd",
      vcd_stages: [{ valve: "VV02", pressure_pa: 1000, seconds: 5 }],
      gas_backfill_stages: [{ gas: "N2", flow_sccm: 10, target_pressure_pa: 900, hold_seconds: 100 }],
      vcd_step_sequence: ["vcd_stage1", "gas_backfill_stage1"],
    };
    const emitted: Record<string, unknown>[] = [];
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    const moveDown = screen.getByRole("button", { name: "Move vcd_stage1 down" });
    fireEvent.click(moveDown);
    const last = emitted.at(-1) as Record<string, unknown>;
    expect(last.vcd_step_sequence).toEqual([
      "gas_backfill_stage1",
      "vcd_stage1",
    ]);
    expect(last.vcd_stages).toEqual(snapshot.vcd_stages);
    expect(last.gas_backfill_stages).toEqual(snapshot.gas_backfill_stages);
  });

  it("keeps every other field untouched when one scalar is edited", () => {
    const snapshot = {
      method: "thermal_evaporation",
      thickness_nm: 20,
      rate_angstrom_per_s: 0.5,
      substrate_temperature_c: 25,
    };
    const emitted: Record<string, unknown>[] = [];
    render(<SnapshotEditor snapshot={snapshot} editorConfig={editorConfig} onChange={(next) => emitted.push(next)} />);

    fireEvent.change(screen.getByLabelText("Thickness (nm)"), { target: { value: "22" } });

    const edited = emitted.at(-1) as Record<string, unknown>;
    expect(edited.method).toBe("thermal_evaporation");
    expect(edited.thickness_nm).toBe(22);
    expect(edited.rate_angstrom_per_s).toBe(0.5);
    expect(edited.substrate_temperature_c).toBe(25);
  });
});