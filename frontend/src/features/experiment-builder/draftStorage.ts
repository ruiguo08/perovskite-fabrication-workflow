import { createDraftStore } from "../../lib/draftPersistence";
import type { ExperimentDraft } from "./types";

/**
 * Browser-local persistence for the in-progress experiment-plan draft.
 * See lib/draftPersistence.ts for the shared storage contract.
 */

function isExperimentDraftLike(value: unknown): value is ExperimentDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Partial<ExperimentDraft>;
  return typeof draft.campaign_id === "string"
    && typeof draft.substrate === "object" && draft.substrate !== null
    && Array.isArray(draft.layers)
    && typeof draft.deposition_process === "object" && draft.deposition_process !== null
    && Array.isArray(draft.conditions);
}

export function experimentDraftHasContent(draft: ExperimentDraft): boolean {
  return draft.campaign_id.trim().length > 0
    || draft.source_baseline_version_id !== null
    || draft.substrate.material.trim().length > 0
    || draft.substrate.vendor.trim().length > 0
    || draft.substrate.type_number.trim().length > 0
    || draft.layers.length > 0
    || draft.deposition_process.spin_steps.length > 0
    || draft.deposition_process.vcd_stages.length > 0
    || draft.deposition_process.gas_backfill_stages.length > 0
    || draft.deposition_process.anneal_steps.length > 0
    || draft.conditions.length > 0;
}

export const experimentDraftStore = createDraftStore<ExperimentDraft>({
  scope: "experiment",
  isEmpty: (draft) => !experimentDraftHasContent(draft),
  isValid: isExperimentDraftLike,
});
