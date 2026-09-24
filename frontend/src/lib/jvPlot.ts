/** Shared plotting helpers and colors for the J-V chart components. */

export const FORWARD_COLOR = "#d97706";
export const REVERSE_COLOR = "#0891b2";

/** Categorical palette for assignment groups (shared by box plots and overlays). */
export const GROUP_COLORS = ["#176b87", "#d97706", "#7c3aed", "#0f766e", "#be185d"];

export function groupColor(index: number): string {
  return GROUP_COLORS[index % GROUP_COLORS.length];
}

export interface PlottedPoint {
  voltage: number;
  current: number;
}

/**
 * Polarity normalization and quadrant clipping for one trace: flip the current
 * sign so the trace lives in the power-generating quadrant, then keep only the
 * points with non-negative voltage and current.
 */
export function tracePlotPoints(trace: {
  valid: boolean;
  points: number[][];
}): PlottedPoint[] {
  if (!trace.valid || !trace.points.length) {
    return [];
  }
  const atZero = trace.points.reduce(
    (best, point) => (Math.abs(point[0]) < Math.abs(best[0]) ? point : best),
    trace.points[0],
  );
  const sign = atZero[1] < 0 ? -1 : 1;
  return trace.points
    .map((point) => ({ voltage: point[0], current: point[1] * sign }))
    .filter((point) => point.voltage >= 0 && point.current >= 0);
}

/** Build an SVG polyline path string from plotted points in axis coordinates. */
export function tracePath(
  points: PlottedPoint[],
  x: (value: number) => number,
  y: (value: number) => number,
): string {
  return points
    .map((point, index) => `${index ? "L" : "M"}${x(point.voltage).toFixed(2)} ${y(point.current).toFixed(2)}`)
    .join(" ");
}
