import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JvChart } from "./JvChart";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";

function makeDevice(overrides: Partial<AnalysisDevice> = {}): AnalysisDevice {
  return {
    device_id: "device-001", label: "A011 Channel 1", device_mark: "A011",
    substrate_id: "A011", group_id: "control",
    metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: 10 }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce: 10 } },
    traces: [{ trace_id: "f", label: "forward", direction: "forward", measured_at: null, valid: true,
      error: null, metrics: { pce: 10 }, points: [[0, -20], [1, 0]] }], ...overrides,
  };
}
const GROUPS: ResultAssignmentGroup[] = [
  { group_id: "control", batch_condition_id: 1, condition_code: "C", kind: "control", name: "Control" },
  { group_id: "target", batch_condition_id: 2, condition_code: "T", kind: "target", name: "Target" },
];

describe("JvChart", () => {
  it("generates one Python figure URL for a multi-device selection", () => {
    render(<JvChart resultId={42} devices={[makeDevice(), makeDevice({ device_id: "device-002" })]} groups={GROUPS} />);
    fireEvent.click(screen.getByText("Choose devices (0 selected)"));
    fireEvent.click(screen.getByLabelText("Choose device device-001"));
    fireEvent.click(screen.getByLabelText("Choose device device-002"));
    expect(screen.getByRole("img", { name: /All-device J-V curves/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /plot selected/i }));
    const image = screen.getByRole("img", { name: /Publication J-V curves/i });
    expect(image).toHaveAttribute("src", expect.stringContaining("/api/results/42/figures/jv?"));
    expect(image.getAttribute("src")).toContain("device_id=device-001");
    expect(image.getAttribute("src")).toContain("device_id=device-002");
    expect(screen.getAllByRole("link", { name: /SVG|PDF|TIFF/ })).toHaveLength(3);
  });

  it("shows the all-device overview by default", () => {
    render(<JvChart resultId={42} devices={[makeDevice()]} groups={GROUPS} />);
    const image = screen.getByRole("img", { name: /All-device J-V curves/i });
    expect(image).toHaveAttribute("src", expect.stringContaining("/api/results/42/figures/jv?"));
    expect(image.getAttribute("src")).not.toContain("device_id=");
    expect(image.getAttribute("src")).toContain("palette=standalone");
    fireEvent.change(screen.getByLabelText("Color palette"), { target: { value: "nejm" } });
    expect(screen.getByRole("img", { name: /All-device J-V curves/i }).getAttribute("src")).toContain("palette=nejm");
    expect(screen.getByRole("link", { name: "PDF" })).toHaveAttribute("href", expect.stringContaining("palette=nejm"));
  });

  it("lets an excluded device remain the best J–V scan in its group", () => {
    const devices = [
      makeDevice({ device_id: "d-low" }),
      makeDevice({ device_id: "d-best", metrics: { forward: { pce: 13 }, reverse: { pce: 12 } } }),
      makeDevice({ device_id: "d-excluded", excluded: true, metrics: { forward: { pce: 99 }, reverse: { pce: 99 } } }),
      makeDevice({ device_id: "d-target", group_id: "target", metrics: { forward: { pce: 11 }, reverse: null } }),
    ];
    render(<JvChart resultId={42} devices={devices} groups={GROUPS} />);
    fireEvent.click(screen.getByRole("button", { name: /select best per group/i }));
    fireEvent.click(screen.getByRole("button", { name: /plot selected/i }));
    const source = screen.getByRole("img", { name: /Publication J-V curves/i }).getAttribute("src") ?? "";
    expect(source).toContain("device_id=d-excluded");
    expect(source).toContain("device_id=d-target");
    expect(source).not.toContain("device_id=d-best");
  });

  it("caps the generated figure at 12 selected devices", () => {
    const devices = Array.from({ length: 15 }, (_, index) => makeDevice({ device_id: `d-${index}` }));
    render(<JvChart resultId={42} devices={devices} groups={GROUPS} />);
    fireEvent.click(screen.getByRole("button", { name: /select all/i }));
    expect(screen.getByText(/first 12 selected/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /plot selected/i }));
    const source = screen.getByRole("img", { name: /Publication J-V curves/i }).getAttribute("src") ?? "";
    expect((source.match(/device_id=/g) ?? [])).toHaveLength(12);
  });

  it("clears the selection and keeps FF percentage display", () => {
    render(<JvChart resultId={42} devices={[makeDevice()]} groups={GROUPS} />);
    fireEvent.click(screen.getByRole("button", { name: /select all/i }));
    fireEvent.click(screen.getByRole("button", { name: /plot selected/i }));
    expect(screen.getAllByText("50.00").length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(screen.getByRole("img", { name: /All-device J-V curves/i })).toBeInTheDocument();
  });
});
