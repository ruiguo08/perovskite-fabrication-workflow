import type { Role } from "../../auth/session";
import { FormField } from "../../components/FormField";
import type { Baseline, Campaign } from "../../types/api";
import type { ExperimentDraft } from "./types";

interface StartingPointPanelProps {
  role: Role;
  user: { id: number } | null;
  draft: ExperimentDraft;
  campaigns: Campaign[];
  baselines: Baseline[];
  selectedBaselineId: string;
  onCampaignChange: (campaignId: string) => void;
  onBaselineChange: (baselineId: string) => void;
  onStartBlank: () => void;
}

export function StartingPointPanel({
  role,
  user,
  draft,
  campaigns,
  baselines,
  selectedBaselineId,
  onCampaignChange,
  onBaselineChange,
  onStartBlank,
}: StartingPointPanelProps) {
  const activeCampaigns = campaigns.filter((campaign) => campaign.status === "active");
  // Step 1 shows only active Shared baselines plus the current user's own
  // active Personal baselines - never a peer's Personal baseline.
  const activeBaselines = baselines.filter(
    (baseline) =>
      baseline.status === "active"
      && baseline.deposition_process !== null
      && (baseline.scope === "shared" || baseline.owner_user_id === user?.id),
  );
  const roleLabel = role === "student" ? "Plan from scratch" : "Start blank";

  return (
    <section className="builder-panel" aria-labelledby="builder-start-title">
      <div className="builder-panel__heading">
        <div><span className="builder-panel__eyebrow">Step 1</span><h2 id="builder-start-title">Starting point</h2></div>
        {draft.source_baseline_version_id ? <span className="builder-snapshot-mark">Expanded snapshot</span> : null}
      </div>
      <p className="builder-help">
        Three ways to begin: expand a baseline (the shortcut — its complete recipe is copied into this editable plan),
        or plan from scratch and fill in every layer, material, and process yourself. Either way the experiment stores
        its own complete snapshot; a baseline reference is provenance only.
      </p>
      <div className="builder-fields builder-fields--two">
        <FormField label="Campaign" htmlFor="builder-campaign" required>
          <select id="builder-campaign" className="text-input" value={draft.campaign_id} onChange={(event) => onCampaignChange(event.target.value)}>
            <option value="">Choose an active Campaign…</option>
            {activeCampaigns.map((campaign) => <option key={campaign.code} value={campaign.code}>{campaign.display_name} · {campaign.code}</option>)}
          </select>
        </FormField>
        <FormField label="Baseline reference (optional shortcut)" htmlFor="builder-baseline" hint="Changing this selection replaces the current editable recipe with a fresh deep copy. Leave empty to plan from scratch.">
          <select id="builder-baseline" className="text-input" value={selectedBaselineId} onChange={(event) => onBaselineChange(event.target.value)}>
            <option value="" disabled={activeBaselines.length === 0}>
              {activeBaselines.length === 0 ? "No baselines available yet — plan from scratch below" : "Choose an active baseline…"}
            </option>
            {activeBaselines.map((baseline) => <option key={baseline.id} value={baseline.id}>{baseline.name} · revision {baseline.current_revision_number}</option>)}
          </select>
        </FormField>
      </div>
      <div className="button-row">
        <button type="button" className="button button--secondary" onClick={onStartBlank}>{roleLabel}</button>
        {draft.setup_mode === "blank" ? <span className="builder-help">Blank plan active</span> : null}
      </div>
    </section>
  );
}
