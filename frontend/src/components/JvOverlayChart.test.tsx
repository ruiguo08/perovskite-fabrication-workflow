import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JvOverlayChart } from "./JvOverlayChart";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";

function makeDevice(overrides: Partial<AnalysisDevice> = {}): AnalysisDevice {
  return {
    device_id: "device-001",
    label: "A001 Channel 1",
    device_mark: "A001",
    substrate_id: "A001",
    group_id: "control",
    metrics: { forward: { voc: 1.0, jsc: 20, ff: 0.5, pce: 10 }, reverse: { voc: 1.0, jsc: 20, ff: 0.5, pce: 10 } },
    traces: [
      {
        trace_id: "trace-001",
        label: "A001 Channel 1.Forward",
        direction: "forward",
        measured_at: null,
        valid: true,
        error: null,
        metrics: { voc: 1, jsc: 20, ff: 0.5, pce: 10 },
        points: [[0, -20], [0.5, -20], [1, 0]],
      },
      {
        trace_id: "trace-002",
        label: "A001 Channel 1.Reverse",
        direction: "reverse",
        measured_at: null,
        valid: true,
        error: null,
        metrics: { voc: 1, jsc: 20, ff: 0.5, pce: 10 },
        points: [[0, -20], [0.5, -20], [1, 0]],
      },
    ],
    ...overrides,
  };
}

const GROUPS: ResultAssignmentGroup[] = [
  { group_id: "control", batch_condition_id: 21, condition_code: "C", kind: "control", name: "Control" },
  { group_id: "target-1", batch_condition_id: 22, condition_code: "T1", kind: "target", name: "ADH" },
];

describe("JvOverlayChart", () => {
  it("prompts for assignment when no device is assigned", () => {
    const unassigned = makeDevice({ group_id: "" });
    render(<JvOverlayChart devices={[unassigned]} groups={GROUPS} />);
    expect(screen.getByText(/Assign devices to conditions/i)).toBeInTheDocument();
  });

  it("draws one curve pair per best device in each group by default", () => {
    const devices = [
      makeDevice({ device_id: "d-low", group_id: "control", metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: 8 }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce: 8 } } }),
      makeDevice({ device_id: "d-best", group_id: "control", metrics: { forward: { voc: 1, jsc: 22, ff: 0.6, pce: 13.2 }, reverse: { voc: 1, jsc: 22, ff: 0.6, pce: 13.2 } } }),
      makeDevice({ device_id: "d-tgt", group_id: "target-1", metrics: { forward: { voc: 1, jsc: 21, ff: 0.55, pce: 11.55 }, reverse: { voc: 1, jsc: 21, ff: 0.55, pce: 11.55 } } }),
    ];
    render(<JvOverlayChart devices={devices} groups={GROUPS} />);
    const svg = screen.getByRole("img", { name: /J-V curves of the assigned devices/i });
    // Best-per-group default: d-best (forward+reverse) and d-tgt (forward+reverse).
    const titled = Array.from(svg.querySelectorAll("path title")).map((title) => title.textContent);
    expect(titled).toEqual(expect.arrayContaining([
      "d-best (A001) forward",
      "d-best (A001) reverse",
      "d-tgt (A001) forward",
      "d-tgt (A001) reverse",
    ]));
    expect(titled.some((text) => text?.startsWith("d-low"))).toBe(false);
  });

  it("switches to all devices when the best-only toggle is cleared", () => {
    const devices = [
      makeDevice({ device_id: "d-low", group_id: "control", metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: 8 }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce: 8 } } }),
      makeDevice({ device_id: "d-best", group_id: "control", metrics: { forward: { voc: 1, jsc: 22, ff: 0.6, pce: 13.2 }, reverse: { voc: 1, jsc: 22, ff: 0.6, pce: 13.2 } } }),
    ];
    render(<JvOverlayChart devices={devices} groups={GROUPS} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Best device per group/i }));
    const svg = screen.getByRole("img", { name: /J-V curves of the assigned devices/i });
    const titled = Array.from(svg.querySelectorAll("path title")).map((title) => title.textContent);
    expect(titled).toEqual(expect.arrayContaining(["d-low (A001) forward", "d-best (A001) forward"]));
  });

  it("hides a group when its legend checkbox is cleared", () => {
    const devices = [
      makeDevice({ device_id: "d-ctl", group_id: "control" }),
      makeDevice({ device_id: "d-tgt", group_id: "target-1" }),
    ];
    render(<JvOverlayChart devices={devices} groups={GROUPS} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Toggle group ADH/i }));
    const svg = screen.getByRole("img", { name: /J-V curves of the assigned devices/i });
    const titled = Array.from(svg.querySelectorAll("path title")).map((title) => title.textContent);
    expect(titled).toEqual(expect.arrayContaining(["d-ctl (A001) forward"]));
    expect(titled.some((text) => text?.startsWith("d-tgt"))).toBe(false);
  });

  it("renders export controls for the overlay chart", () => {
    render(<JvOverlayChart devices={[makeDevice()]} groups={GROUPS} />);
    expect(screen.getByRole("button", { name: "Export chart as SVG" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export chart as PNG" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export chart as TIFF" })).toBeInTheDocument();
  });

  it("never draws excluded devices", () => {
    const devices = [
      makeDevice({ device_id: "d-bad", group_id: "control", excluded: true, exclusion_reason: "shorted" }),
      makeDevice({ device_id: "d-ctl", group_id: "control" }),
    ];
    render(<JvOverlayChart devices={devices} groups={GROUPS} />);
    const svg = screen.getByRole("img", { name: /J-V curves of the assigned devices/i });
    const titled = Array.from(svg.querySelectorAll("path title")).map((title) => title.textContent);
    expect(titled).toEqual(expect.arrayContaining(["d-ctl (A001) forward"]));
    expect(titled.some((text) => text?.startsWith("d-bad"))).toBe(false);
  });
});
