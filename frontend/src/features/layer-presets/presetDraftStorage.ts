import { createDraftStore } from "../../lib/draftPersistence";
import type {
  LayerProcess,
  LayerSolution,
  PerovskiteDepositionProcess,
} from "../../types/api";

/**
 * Browser-local persistence for in-progress inline edits of a layer preset.
 * Only edits that differ from the preset's current values are stored, so
 * cards without changes never announce a restore. See lib/draftPersistence.ts
 * for the shared storage contract.
 */

export interface PresetDraftEntry {
  name: string;
  layerName: string;
  solution: LayerSolution | null;
  layerProcess: LayerProcess | null;
  depositionProcess: PerovskiteDepositionProcess | null;
}

export interface PresetDraftOriginal {
  name: string;
  layerName: string;
  solution: LayerSolution | null;
  layerProcess: LayerProcess | null;
  depositionProcess: PerovskiteDepositionProcess | null;
}

function sameJSON(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function matchesOriginal(entry: PresetDraftEntry, original: PresetDraftOriginal): boolean {
  return entry.name === original.name
    && entry.layerName === original.layerName
    && sameJSON(entry.solution, original.solution)
    && sameJSON(entry.layerProcess, original.layerProcess)
    && sameJSON(entry.depositionProcess, original.depositionProcess);
}

function isPresetDraftLike(value: unknown): value is PresetDraftEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<PresetDraftEntry>;
  return typeof entry.name === "string" && typeof entry.layerName === "string";
}

export function createPresetDraftStore(presetId: number, original: PresetDraftOriginal) {
  return createDraftStore<PresetDraftEntry>({
    scope: `preset-${presetId}`,
    isEmpty: (entry) => matchesOriginal(entry, original),
    isValid: isPresetDraftLike,
  });
}
