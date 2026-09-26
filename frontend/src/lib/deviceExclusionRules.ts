import type { AnalysisDevice } from "../types/api";

export type ExclusionMetric = "voc" | "pce" | "ff";
export type ExclusionThresholds = Record<ExclusionMetric, number | null>;

const METRICS: { name: ExclusionMetric; label: string; unit: string; multiplier: number; digits: number }[] = [
  { name: "voc", label: "Voc", unit: "V", multiplier: 1, digits: 3 },
  { name: "pce", label: "PCE", unit: "%", multiplier: 1, digits: 2 },
  { name: "ff", label: "FF", unit: "%", multiplier: 100, digits: 1 },
];

export function parseExclusionThreshold(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function failedMetrics(metrics: Record<string, number>, thresholds: ExclusionThresholds): string[] {
  return METRICS.flatMap(({ name, label, unit, multiplier, digits }) => {
    const limit = thresholds[name];
    const raw = metrics[name];
    if (limit === null || !Number.isFinite(raw) || raw * multiplier >= limit) return [];
    return [`${label} ${Number((raw * multiplier).toFixed(digits))} ${unit} < ${limit} ${unit}`];
  });
}

/** A device is auto-excluded only when each direction fails any enabled metric. */
export function evaluateDeviceExclusion(device: AnalysisDevice, thresholds: ExclusionThresholds): string | null {
  const forward = device.metrics?.forward;
  const reverse = device.metrics?.reverse;
  if (!forward || !reverse) return null;
  const forwardFailures = failedMetrics(forward, thresholds);
  const reverseFailures = failedMetrics(reverse, thresholds);
  if (!forwardFailures.length || !reverseFailures.length) return null;
  return `Automatic: Forward ${forwardFailures.join(", ")}; Reverse ${reverseFailures.join(", ")}`;
}
