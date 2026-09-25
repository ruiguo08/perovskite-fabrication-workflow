import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnalysisDevice } from "../types/api";
import { DeviceExclusionsPanel } from "./DeviceExclusionsPanel";

function device(id: string, forward: Record<string, number> | null, reverse: Record<string, number> | null): AnalysisDevice {
  return {
    device_id: id,
    label: id,
    device_mark: null,
    substrate_id: "substrate-1",
    group_id: "control",
    metrics: { forward, reverse },
    traces: [],
  };
}

describe("DeviceExclusionsPanel automatic rule", () => {
  it("uses a union of metric failures within each direction and requires both directions to fail", () => {
    const onChange = vi.fn();
    render(<DeviceExclusionsPanel
      devices={[
        device("different-metrics", { voc: 0.65, pce: 12, ff: 0.7 }, { voc: 0.9, pce: 12, ff: 0.55 }),
        device("forward-only", { voc: 0.65, pce: 12, ff: 0.7 }, { voc: 0.9, pce: 12, ff: 0.7 }),
        device("missing-reverse", { voc: 0.5, pce: 5, ff: 0.3 }, null),
      ]}
      groups={[{ group_id: "control", batch_condition_id: 1, condition_code: "C", kind: "control", name: "Control" }]}
      exclusions={new Map()}
      onChange={onChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Flag matching devices" }));

    const selected = onChange.mock.lastCall?.[0] as Map<string, string>;
    expect([...selected.keys()]).toEqual(["different-metrics"]);
    expect(selected.get("different-metrics")).toMatch(/Forward.*Voc.*0\.65.*Reverse.*FF.*55/);
  });

  it("recalculates automatic flags while preserving manual exclusions", () => {
    const onChange = vi.fn();
    render(<DeviceExclusionsPanel
      devices={[
        device("now-passes", { voc: 0.9, pce: 12, ff: 0.7 }, { voc: 0.9, pce: 12, ff: 0.7 }),
        device("manual", { voc: 0.9, pce: 12, ff: 0.7 }, { voc: 0.9, pce: 12, ff: 0.7 }),
      ]}
      groups={[]}
      exclusions={new Map([["now-passes", "Automatic: Forward Voc 0.6 V < 0.8 V; Reverse Voc 0.6 V < 0.8 V"], ["manual", "Observed a damaged contact"]])}
      onChange={onChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Flag matching devices" }));
    const selected = onChange.mock.lastCall?.[0] as Map<string, string>;
    expect([...selected.entries()]).toEqual([["manual", "Observed a damaged contact"]]);
  });
});
