import { VCD_VALVES } from "./constraints";

/**
 * Single source of parameter metadata for the perovskite process and solution
 * fields. Drives both editing (NumberField/SelectField read min/step/options)
 * and read-only display (QuantityRow reads label/unit/digits/scale), and
 * mirrors the pydantic bounds in src/perovskite_bo/device_recipe.py.
 *
 * Labels for edit controls are caller-supplied (spin/anneal stages need a
 * "Stage N" index), so this registry stores unit/bounds/options for editing
 * and label/digits/scale for read-only metric display.
 */
export interface FieldMeta {
  unit?: string;
  min?: number;
  max?: number;
  step?: string;
  options?: readonly string[];
  help?: string;
  /** Read-only display label (metrics). */
  label?: string;
  /** Read-only display precision. */
  digits?: number;
  /** Read-only display multiplier (FF stored 0-1, shown as %). */
  scale?: number;
}

export const FIELD_META: Record<string, FieldMeta> = {
  // VCD setpoints are whole numbers: pressures are integer Pa (sub-1 Pa
  // pump-downs only control time, not pressure), durations are whole
  // seconds (0 s = reach the pressure and move on without holding), and
  // MFC flows are integer sccm.
  valve: { options: VCD_VALVES },
  pressure_pa: { unit: "Pa", min: 0, step: "1" },
  seconds: { unit: "s", min: 0, step: "1" },
  // gas backfill
  flow_sccm: { unit: "sccm", min: 1, step: "1" },
  target_pressure_pa: { unit: "Pa", min: 0, step: "1" },
  hold_seconds: { unit: "s", min: 0, step: "1" },
  // spin coating
  rpm: { unit: "rpm", min: 0, step: "1" },
  acceleration_rpm_per_s: { unit: "rpm/s", min: 0, step: "1" },
  // annealing
  temperature_c: { unit: "°C", min: 0, step: "1" },
  // sputtering
  power_w: { unit: "W", min: 0, step: "any" },
  gas1_flow_sccm: { unit: "sccm", min: 0, step: "any" },
  gas2_flow_sccm: { unit: "sccm", min: 0, step: "any" },
  duration_seconds: { unit: "s", min: 0, step: "1" },
  // thermal evaporation / ALD
  thickness_nm: { unit: "nm", min: 0, step: "any" },
  rate_angstrom_per_s: { unit: "Å/s", min: 0, step: "any" },
  substrate_temperature_c: { unit: "°C", min: 0, step: "1" },
  cycles: { min: 0, step: "1" },
  // solution
  weight_mg: { unit: "mg", min: 0, step: "any" },
  volume_ml: { unit: "mL", min: 0, step: "any" },
  stock_volume_ml: { unit: "mL", min: 0, step: "any" },

  // metrics — read-only display
  voc: { label: "Voc", unit: "V", digits: 3 },
  jsc: { label: "Jsc", unit: "mA/cm²", digits: 2 },
  ff: { label: "FF", unit: "%", digits: 2, scale: 100 },
  pce: { label: "PCE", unit: "%", digits: 2 },
};

export function fieldMeta(name: string): FieldMeta {
  return FIELD_META[name] ?? {};
}
