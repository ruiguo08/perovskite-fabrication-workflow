/** Formatting helpers shared across the application. */

const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return DATE_TIME_FORMAT.format(date);
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

/** Format a number with fixed digits, or an em dash for null/NaN/Infinity. */
export function formatNumber(value: number | null | undefined, digits: number): string {
  return Number.isFinite(value) ? (value as number).toFixed(digits) : "—";
}

/**
 * Scale a server-provided metric for display. FF is stored as a 0–1 fraction
 * and shown as a percent; other metrics pass through. Null/non-finite values
 * stay null so {@link formatNumber} renders an em dash.
 */
export function scaleMetric(name: string, value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return name === "ff" ? value * 100 : value;
}