/** Status transitions offered for a solution preparation, by current status. */
export function preparationStatusOptions(current: string): string[] {
  if (current === "planned") return ["preparing", "ready", "discarded"];
  if (current === "preparing") return ["ready", "discarded"];
  if (current === "ready") return ["consumed", "discarded"];
  return [];
}

/** Status transitions offered for a process execution, by current status. */
export function executionStatusOptions(current: string): string[] {
  if (current === "planned") return ["ready", "running", "cancelled"];
  if (current === "ready") return ["running"];
  if (current === "running") return ["completed", "failed", "cancelled"];
  return [];
}

export function parseJsonField(name: string, value: string): Record<string, unknown> | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    throw new Error(`${name} must be valid JSON`);
  }
}

/** Shallow copy of a snapshot dict so the editor never mutates run-sheet data. */
export function snapshotCopy(value: Record<string, unknown>): Record<string, unknown> {
  return { ...value };
}
