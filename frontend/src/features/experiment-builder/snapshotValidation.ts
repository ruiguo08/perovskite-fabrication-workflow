function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isRecordArray(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(isRecord);
}

function hasOptionalRecordArray(value: Record<string, unknown>, key: string): boolean {
  return value[key] === undefined || isRecordArray(value[key]);
}

function hasSafeSolution(value: unknown): boolean {
  if (value === null) return true;
  if (!isRecord(value) || typeof value.formulation_type !== "string") return false;
  if (!isRecordArray(value.solids) || !isRecordArray(value.solvents)) return false;
  return value.solids.every((item) => typeof item.chemical === "string")
    && value.solvents.every((item) => typeof item.solvent === "string")
    && (value.stock_dispersion === undefined || typeof value.stock_dispersion === "string");
}

function hasSafeLayerProcess(value: unknown): boolean {
  if (value === null) return true;
  if (!isRecord(value) || typeof value.method !== "string") return false;
  return hasOptionalRecordArray(value, "spin_steps")
    && hasOptionalRecordArray(value, "anneal_steps");
}

export function validateTargetLayersObject(value: Record<string, unknown>): string | null {
  if (!Array.isArray(value.layers) || !value.layers.every(isRecord)) {
    return "The target snapshot must contain a layers array of objects.";
  }
  const valid = value.layers.every((layer) =>
    typeof layer.name === "string"
    && typeof layer.role === "string"
    && typeof layer.layer_type === "string"
    && hasSafeSolution(layer.solution)
    && hasSafeLayerProcess(layer.process),
  );
  return valid
    ? null
    : "Every target layer must contain safe name, role, type, solution, and process values.";
}

export function validateTargetProcessObject(value: Record<string, unknown>): string | null {
  const sequence = value.vcd_step_sequence;
  const valid = value.method === "spin_coating_vcd"
    && isRecordArray(value.spin_steps)
    && isRecordArray(value.vcd_stages)
    && isRecordArray(value.gas_backfill_stages)
    && isRecordArray(value.anneal_steps)
    && (sequence === undefined || (Array.isArray(sequence) && sequence.every((item) => typeof item === "string")));
  return valid
    ? null
    : "The target process must contain safe spin, VCD, gas-backfill, annealing, and sequence values.";
}
