import { describe, expect, it } from "vitest";
import type { AnalysisDevice } from "../types/api";
import { evaluateDeviceExclusion, type ExclusionThresholds } from "./deviceExclusionRules";

function device(forward: Record<string, number> | null, reverse: Record<string, number> | null): AnalysisDevice {
  return {
    device_id: "device-1",
    label: "Device 1",
    device_mark: null,
    substrate_id: "substrate-1",
    group_id: "control",
    metrics: { forward, reverse },
    traces: [],
  };
}

const thresholds: ExclusionThresholds = { voc: 0.8, pce: null, ff: 60 };

describe("evaluateDeviceExclusion", () => {
  it("uses the union of enabled metrics in each direction and records both reasons", () => {
    const reason = evaluateDeviceExclusion(
      device({ voc: 0.75, ff: 0.7 }, { voc: 0.9, ff: 0.55 }),
      thresholds,
    );
    expect(reason).toMatch(/Forward Voc 0\.75 V < 0\.8 V/);
    expect(reason).toMatch(/Reverse FF 55 % < 60 %/);
  });

  it("keeps the device when one direction passes or is missing", () => {
    expect(evaluateDeviceExclusion(device({ voc: 0.75, ff: 0.7 }, { voc: 0.8, ff: 0.6 }), thresholds)).toBeNull();
    expect(evaluateDeviceExclusion(device({ voc: 0.75, ff: 0.7 }, null), thresholds)).toBeNull();
  });

  it("uses the same strict threshold for forward and reverse scans", () => {
    expect(evaluateDeviceExclusion(device({ voc: 0.79, ff: 0.6 }, { voc: 0.79, ff: 0.6 }), thresholds)).toMatch(/Reverse Voc/);
    expect(evaluateDeviceExclusion(device({ voc: 0.8, ff: 0.6 }, { voc: 0.79, ff: 0.6 }), thresholds)).toBeNull();
  });
});
