import type { AnalysisDevice, AnalysisTrace, DirectionalMetrics } from "../types/api";

/**
 * Directional-metrics helpers (schema 7).
 *
 * Every scan stays an individual trace with its own instrument-reported
 * metrics; a device's per-direction `metrics` record holds the
 * representative scan (highest-PCE valid scan, or the user's explicit
 * choice). `combined` only exists on analyses migrated from the old flat
 * schema 5. UI surfaces choose a reading order:
 *
 * - directional reading: the named tier only.
 * - trace-level reading (schema 7): the best-PCE valid trace per direction,
 *   recomputed from `device.traces`, is the display default.
 */

function firstFinite(record: Record<string, number> | null | undefined, name: string): number | null {
  const value = record?.[name];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Any tier present at all (shape check for "device has metrics"). */
export function hasMetrics(metrics: DirectionalMetrics | null | undefined): boolean {
  return Boolean(metrics && (metrics.combined || metrics.forward || metrics.reverse));
}

/** Value from one named tier ("forward" | "reverse" | "combined"); null otherwise. */
export function directionalMetric(
  metrics: DirectionalMetrics | null | undefined,
  direction: "forward" | "reverse" | "combined",
  name: string,
): number | null {
  return firstFinite(metrics?.[direction], name);
}

/** Best PCE across all tiers — used by "select best per group". */
export function bestPce(device: AnalysisDevice): number | null {
  const tiers = [device.metrics?.combined, device.metrics?.forward, device.metrics?.reverse];
  const values = tiers
    .map((tier) => firstFinite(tier, "pce"))
    .filter((value): value is number => value !== null);
  return values.length ? Math.max(...values) : null;
}

/**
 * Flat rows for the per-device metrics table: one row per available
 * direction, in a stable order (combined first — migrated analyses only —
 * then forward, then reverse).
 */
export function metricRows(
  device: AnalysisDevice,
): { direction: "combined" | "forward" | "reverse"; label: string }[] {
  const rows: { direction: "combined" | "forward" | "reverse"; label: string }[] = [];
  if (device.metrics?.combined) {
    rows.push({ direction: "combined", label: "Combined" });
  }
  if (device.metrics?.forward) {
    rows.push({ direction: "forward", label: "Forward" });
  }
  if (device.metrics?.reverse) {
    rows.push({ direction: "reverse", label: "Reverse" });
  }
  return rows;
}

/** PCE of a trace's metrics record; null when absent or not a finite number. */
function tracePce(trace: AnalysisTrace): number | null {
  const value = trace.metrics?.pce;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * The best-PCE valid trace of one direction (schema 7 display default):
 * the scan the device-level representative record holds. First wins ties,
 * matching the backend rule; null when the direction has no valid scan.
 */
export function bestTrace(
  traces: AnalysisTrace[] | undefined,
  direction: "forward" | "reverse",
): AnalysisTrace | null {
  let best: AnalysisTrace | null = null;
  let bestPce: number | null = null;
  for (const trace of traces ?? []) {
    if (!trace.valid || trace.direction !== direction) {
      continue;
    }
    const pce = tracePce(trace);
    if (pce === null) {
      continue;
    }
    if (best === null || bestPce === null || pce > bestPce) {
      best = trace;
      bestPce = pce;
    }
  }
  return best;
}

/** All valid scans of one direction, in stored (file) order. */
export function tracesOfDirection(
  traces: AnalysisTrace[] | undefined,
  direction: "forward" | "reverse",
): AnalysisTrace[] {
  return (traces ?? []).filter(
    (trace) => trace.valid && trace.direction === direction,
  );
}
