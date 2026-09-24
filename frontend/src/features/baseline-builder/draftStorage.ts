import { createDraftStore } from "../../lib/draftPersistence";
import type { ExperimentDraft } from "../experiment-builder/types";

/**
 * Browser-local persistence for the in-progress baseline authoring draft.
 * See lib/draftPersistence.ts for the shared storage contract.
 */

function isExperimentDraftLike(value: unknown): value is ExperimentDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<ExperimentDraft>;
  return typeof draft.substrate === "object" && draft.substrate !== null
    && Array.isArray(draft.layers)
    && typeof draft.deposition_process === "object" && draft.deposition_process !== null;
}

function hasContent(name: string, draft: ExperimentDraft): boolean {
  return name.trim().length > 0
    || draft.substrate.material.trim().length > 0
    || draft.substrate.vendor.trim().length > 0
    || draft.substrate.type_number.trim().length > 0
    || draft.layers.length > 0
    || draft.deposition_process.spin_steps.length > 0
    || draft.deposition_process.vcd_stages.length > 0
    || draft.deposition_process.gas_backfill_stages.length > 0
    || draft.deposition_process.anneal_steps.length > 0;
}

export function baselineDraftHasContent(name: string, draft: ExperimentDraft): boolean {
  return hasContent(name, draft);
}

interface BaselineDraftEntry {
  name: string;
  draft: ExperimentDraft;
}

const baselineDraftStore = createDraftStore<BaselineDraftEntry>({
  scope: "baseline",
  isEmpty: (entry) => !hasContent(entry.name, entry.draft),
  isValid: (value) =>
    typeof value === "object" && value !== null
    && typeof (value as Partial<BaselineDraftEntry>).name === "string"
    && isExperimentDraftLike((value as Partial<BaselineDraftEntry>).draft),
});

export function loadBaselineDraft(userId: number): BaselineDraftEntry | null {
  return baselineDraftStore.load(userId);
}

export function saveBaselineDraft(userId: number, name: string, draft: ExperimentDraft): void {
  baselineDraftStore.save(userId, { name, draft });
}

export function clearBaselineDraft(userId: number): void {
  baselineDraftStore.clear(userId);
}
