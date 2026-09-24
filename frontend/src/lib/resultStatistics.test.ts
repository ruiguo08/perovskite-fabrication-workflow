import { describe, expect, it } from "vitest";
import { directionalGroupStatistics } from "./resultStatistics";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";

const groups = [{ group_id: "control", name: "Control", kind: "control" }] as ResultAssignmentGroup[];
const devices = [
  { device_id: "a", label: "a", device_mark: null, substrate_id: "A001", group_id: "control", traces: [], metrics: {
    forward: { voc: 1, jsc: 20, ff: 0.7, pce: 14 },
    reverse: { voc: 1.1, jsc: 22, ff: 0.75, pce: 18.15 },
  } },
  { device_id: "b", label: "b", device_mark: null, substrate_id: "A001", group_id: "control", traces: [], metrics: {
    forward: { voc: 0.8, jsc: 10, ff: 0.5, pce: 4 },
    reverse: { voc: 0.9, jsc: 12, ff: 0.6, pce: 6.48 },
  } },
] as AnalysisDevice[];

describe("directionalGroupStatistics", () => {
  it("keeps forward and reverse separate and reports all and included devices", () => {
    const rows = directionalGroupStatistics(devices, groups, new Set(["b"]));
    expect(rows.map((row) => [row.scope, row.direction, row.deviceCount])).toEqual([
      ["all", "forward", 2], ["all", "reverse", 2],
      ["included", "forward", 1], ["included", "reverse", 1],
    ]);
    expect(rows[0].metrics.pce).toEqual({ maximum: 14, mean: 9, n: 2 });
    expect(rows[1].metrics.pce).toEqual({ maximum: 18.15, mean: 12.315, n: 2 });
    expect(rows[2].metrics.pce).toEqual({ maximum: 14, mean: 14, n: 1 });
    expect(rows[3].metrics.ff).toEqual({ maximum: 0.75, mean: 0.75, n: 1 });
  });

  it("ignores nonfinite or missing metrics without mixing directions", () => {
    const rows = directionalGroupStatistics([
      { ...devices[0], metrics: { forward: { pce: Number.NaN }, reverse: null } },
    ], groups, new Set());
    expect(rows[0].metrics.pce).toEqual({ maximum: null, mean: null, n: 0 });
    expect(rows[1].metrics.pce).toEqual({ maximum: null, mean: null, n: 0 });
  });
});
