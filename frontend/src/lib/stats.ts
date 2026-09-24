/**
 * Client-side descriptive statistics for display-only views that the server
 * does not precompute — notably the per-scan-direction box plots, which are
 * derived from trace-level metrics. Mirrors the server's percentile convention
 * (linear interpolation between order statistics) so both views agree.
 */

export interface DescriptiveStats {
  n: number;
  mean: number | null;
  median: number | null;
  sd: number | null;
  minimum: number | null;
  q1: number | null;
  q3: number | null;
  maximum: number | null;
}

function percentile(ordered: number[], fraction: number): number {
  const position = (ordered.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) {
    return ordered[lower];
  }
  const weight = position - lower;
  return ordered[lower] * (1 - weight) + ordered[upper] * weight;
}

export function descriptiveStatistics(values: number[]): DescriptiveStats {
  if (!values.length) {
    return {
      n: 0,
      mean: null,
      median: null,
      sd: null,
      minimum: null,
      q1: null,
      q3: null,
      maximum: null,
    };
  }
  const ordered = [...values].sort((left, right) => left - right);
  const mean = ordered.reduce((sum, value) => sum + value, 0) / ordered.length;
  const variance =
    ordered.length > 1
      ? ordered.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (ordered.length - 1)
      : 0;
  return {
    n: ordered.length,
    mean,
    median: percentile(ordered, 0.5),
    sd: ordered.length > 1 ? Math.sqrt(variance) : 0,
    minimum: ordered[0],
    q1: percentile(ordered, 0.25),
    q3: percentile(ordered, 0.75),
    maximum: ordered[ordered.length - 1],
  };
}
