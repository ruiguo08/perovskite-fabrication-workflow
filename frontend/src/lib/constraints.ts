// Fallback process-parameter constraints for the builders.
//
// These mirror the pydantic validators in src/perovskite_bo/device_recipe.py
// (gt=0 / ge=0 bounds and the VCD_VALVES equipment set). They are fallbacks
// only: the builders fetch the authoritative valve list from
// GET /api/editor-config at runtime (useEditorConfig) and these constants
// cover the loading/failed states. test_phase3_api pins
// editor_config.vcd_valves to perovskite_bo.VCD_VALVES, so the backend stays
// self-consistent; update here when a backend constraint changes so the
// fallback does not silently diverge.

export const VCD_VALVES = ["VV02", "VV03", "VV06", "Pudi"] as const;
export type VcdValve = (typeof VCD_VALVES)[number];

/** True for a finite number strictly greater than zero (mirrors pydantic gt=0). */
export function isPositiveNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** True for a finite number at least zero (mirrors pydantic ge=0). */
export function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}
