import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BoxPlotChart } from "./BoxPlotChart";
import type { AnalysisDevice, AnalysisStatistics } from "../types/api";

const PALETTE = ["#176b87", "#d97706", "#7c3aed", "#0f766e", "#be185d"];

function makeDevice(group_id: string, pce: number): AnalysisDevice {
  return {
    device_id: `d-${group_id}-${pce}`,
    label: `s-${group_id}`,
    device_mark: null,
    substrate_id: group_id,
    group_id,
    metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce } },
    traces: [],
  };
}

function makeStatistics(): AnalysisStatistics {
  return {
    groups: [
      {
        group_id: "control",
        name: "Control",
        kind: "control",
        device_count: 2,
        valid_device_count: 2,
        metrics: {
          voc: { n: 2, mean: 1, median: 1, sd: 0, minimum: 1, q1: 1, q3: 1, maximum: 1 },
          jsc: { n: 2, mean: 20, median: 20, sd: 0, minimum: 20, q1: 20, q3: 20, maximum: 20 },
          ff: { n: 2, mean: 0.5, median: 0.5, sd: 0, minimum: 0.5, q1: 0.5, q3: 0.5, maximum: 0.5 },
          pce: { n: 2, mean: 10, median: 10, sd: 0, minimum: 9, q1: 9.5, q3: 10.5, maximum: 11 },
        },
      },
      {
        group_id: "target-1",
        name: "ADH",
        kind: "target",
        device_count: 1,
        valid_device_count: 1,
        metrics: {
          voc: { n: 1, mean: 1, median: 1, sd: 0, minimum: 1, q1: 1, q3: 1, maximum: 1 },
          jsc: { n: 1, mean: 22, median: 22, sd: 0, minimum: 22, q1: 22, q3: 22, maximum: 22 },
          ff: { n: 1, mean: 0.6, median: 0.6, sd: 0, minimum: 0.6, q1: 0.6, q3: 0.6, maximum: 0.6 },
          pce: { n: 1, mean: 13.2, median: 13.2, sd: 0, minimum: 13.2, q1: 13.2, q3: 13.2, maximum: 13.2 },
        },
      },
    ],
    comparisons: [],
  };
}

describe("BoxPlotChart", () => {
  it("renders an accessible SVG labelled with the metric", () => {
    render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[makeDevice("control", 10), makeDevice("target-1", 13.2)]}
      />,
    );
    expect(screen.getByRole("img", { name: /PCE/i })).toBeInTheDocument();
  });

  it("draws one box per group with n= labels", () => {
    render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[makeDevice("control", 10), makeDevice("target-1", 13.2)]}
    />,
    );
    expect(screen.getByText("n=2")).toBeInTheDocument();
    expect(screen.getByText("n=1")).toBeInTheDocument();
  });

  it("uses the group palette colors", () => {
    const { container } = render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[makeDevice("control", 10), makeDevice("target-1", 13.2)]}
      />,
    );
    const strokes = new Set(
      Array.from(container.querySelectorAll("rect, line, circle"))
        .map((el) => el.getAttribute("stroke") ?? "")
        .filter(Boolean),
    );
    expect(strokes.has(PALETTE[0])).toBe(true);
    expect(strokes.has(PALETTE[1])).toBe(true);
  });

  it("renders a placeholder when no group has data for the metric", () => {
    const empty = makeStatistics();
    empty.groups[0].metrics.pce = { n: 0, mean: null, median: null, sd: null, minimum: null, q1: null, q3: null, maximum: null };
    empty.groups[1].metrics.pce = { n: 0, mean: null, median: null, sd: null, minimum: null, q1: null, q3: null, maximum: null };
    render(<BoxPlotChart metric="pce" statistics={empty} devices={[]} />);
    expect(screen.getByText(/No valid assigned devices/i)).toBeInTheDocument();
  });

  it("scales FF by 100 for display", () => {
    render(
      <BoxPlotChart
        metric="ff"
        statistics={makeStatistics()}
        devices={[makeDevice("control", 10)]}
      />,
    );
    expect(screen.getByRole("img", { name: /FF \(%\) by group/i })).toBeInTheDocument();
  });

  it("produces no NaN or Infinity SVG attributes with empty device metrics", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[]}
      />,
    );
    const attrs = Array.from(container.querySelectorAll("*"))
      .flatMap((el) => Array.from(el.attributes))
      .map((attr) => attr.value);
    for (const value of attrs) {
      expect(value).not.toMatch(/NaN|Infinity/);
    }
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("filters non-finite device points without crashing", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const brokenDevice: AnalysisDevice = {
      ...makeDevice("control", 10),
      metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: NaN }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce: NaN } },
    };
    const { container } = render(
      <BoxPlotChart metric="pce" statistics={makeStatistics()} devices={[brokenDevice]} />,
    );
    const attrs = Array.from(container.querySelectorAll("*"))
      .flatMap((el) => Array.from(el.attributes))
      .map((attr) => attr.value);
    for (const value of attrs) {
      expect(value).not.toMatch(/NaN|Infinity/);
    }
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("preserves normal server-statistics rendering", () => {
    render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[makeDevice("control", 10), makeDevice("target-1", 13.2)]}
      />,
    );
    expect(screen.getByText("n=2")).toBeInTheDocument();
    expect(screen.getByText("n=1")).toBeInTheDocument();
  });

  it("scales the FF fallback axis domain by 100 when device metrics are missing", () => {
    const ffStats: AnalysisStatistics = {
      groups: [{
        group_id: "control", name: "Control", kind: "control",
        device_count: 2, valid_device_count: 2,
        metrics: {
          ff: { n: 2, mean: 0.5, median: 0.5, sd: 0.05, minimum: 0.45, q1: 0.475, q3: 0.525, maximum: 0.55 },
        },
      }],
      comparisons: [],
    };
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <BoxPlotChart metric="ff" statistics={ffStats} devices={[]} />,
    );
    // No NaN/Infinity in any attribute.
    const allAttrs = Array.from(container.querySelectorAll("*"))
      .flatMap((el) => Array.from(el.attributes))
      .map((attr) => attr.value);
    for (const value of allAttrs) {
      expect(value).not.toMatch(/NaN|Infinity/);
    }
    // The box rect y/height and median line y1/y2 must be finite and inside the SVG.
    const boxRect = container.querySelector("rect[fill-opacity]");
    expect(boxRect).toBeTruthy();
    const rectY = Number(boxRect!.getAttribute("y"));
    const rectHeight = Number(boxRect!.getAttribute("height"));
    expect(Number.isFinite(rectY)).toBe(true);
    expect(Number.isFinite(rectHeight)).toBe(true);
    expect(rectY).toBeGreaterThanOrEqual(0);
    expect(rectY + rectHeight).toBeLessThanOrEqual(310); // svg height
    // The axis tick labels are percentage-scaled (~45–55), not raw (0.45–0.55).
    const tickTexts = Array.from(container.querySelectorAll("text"))
      .map((el) => el.textContent ?? "")
      .filter((t) => t.includes("4") || t.includes("5"));
    expect(tickTexts.some((t) => Number.parseFloat(t) >= 40)).toBe(true);
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it("splits each group into forward and reverse boxes from trace metrics", () => {
    const device = (deviceId: string, forward: number, reverse: number): AnalysisDevice => ({
      device_id: deviceId,
      label: deviceId,
      device_mark: null,
      substrate_id: deviceId,
      group_id: "control",
      metrics: { forward: { voc: 1, jsc: 20, ff: 0.5, pce: forward }, reverse: { voc: 1, jsc: 20, ff: 0.5, pce: reverse } },
      traces: [
        {
          trace_id: `${deviceId}-f`, label: `${deviceId}.Forward`, direction: "forward",
          measured_at: null, valid: true, error: null,
          metrics: { voc: 1, jsc: 20, ff: 0.5, pce: forward }, points: [],
        },
        {
          trace_id: `${deviceId}-r`, label: `${deviceId}.Reverse`, direction: "reverse",
          measured_at: null, valid: true, error: null,
          metrics: { voc: 1, jsc: 20, ff: 0.5, pce: reverse }, points: [],
        },
      ],
    });
    render(
      <BoxPlotChart
        metric="pce"
        statistics={makeStatistics()}
        devices={[
          device("d-1", 10, 9),
          device("d-2", 12, 11),
          { ...device("d-dead", 2, 2), excluded: true, exclusion_reason: "shorted" },
        ]}
        splitByDirection
      />,
    );
    expect(screen.getByText("Control F")).toBeInTheDocument();
    expect(screen.getByText("Control R")).toBeInTheDocument();
    // Two valid devices feed each direction box; the excluded device (2% PCE)
    // never contributes despite having a valid forward trace.
    expect(screen.getAllByText("n=2")).toHaveLength(2);
    expect(screen.getByText(/F = forward scan, R = reverse scan/i)).toBeInTheDocument();
  });
});
