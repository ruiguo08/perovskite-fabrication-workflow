import type { Baseline, Campaign, DeviceLayout } from "../../types/api";
import type { DraftIssue, ExperimentDraft } from "./types";

interface ReviewPanelProps {
  draft: ExperimentDraft;
  campaigns: Campaign[];
  baselines: Baseline[];
  layouts: DeviceLayout[];
  issues: DraftIssue[];
}

export function ReviewPanel({ draft, campaigns, baselines, layouts, issues }: ReviewPanelProps) {
  const campaign = campaigns.find((item) => item.code === draft.campaign_id);
  const baseline = baselines.find((item) => item.current_version_id === draft.source_baseline_version_id);

  return (
    <section className="builder-panel builder-panel--review" aria-labelledby="builder-review-title">
      <div className="builder-panel__heading">
        <div><span className="builder-panel__eyebrow">Step 5</span><h2 id="builder-review-title">Review complete plan</h2></div>
        <span className={`builder-review-state ${issues.length === 0 ? "builder-review-state--ready" : ""}`}>{issues.length === 0 ? "Ready to save" : `${issues.length} items need attention`}</span>
      </div>

      {issues.length > 0 ? (
        <div className="builder-issue-summary" role="alert" aria-labelledby="builder-issues-title">
          <h3 id="builder-issues-title">Complete these values before saving</h3>
          <ul>{issues.map((issue, index) => <li key={`${issue.path}-${index}`}><code>{issue.path}</code> — {issue.message}</li>)}</ul>
        </div>
      ) : null}

      <div className="builder-review-grid">
        <article>
          <h3>Provenance</h3>
          <dl>
            <div><dt>Campaign</dt><dd>{campaign ? `${campaign.display_name} · ${campaign.code}` : "Not selected"}</dd></div>
            <div><dt>Starting point</dt><dd>{baseline ? `${baseline.name} · revision ${baseline.current_revision_number}` : "Blank plan"}</dd></div>
            <div><dt>Baseline version</dt><dd>{draft.source_baseline_version_id ?? "None"}</dd></div>
            <div><dt>Setup mode</dt><dd>{draft.setup_mode}</dd></div>
          </dl>
        </article>
        <article>
          <h3>Substrate</h3>
          <p>{draft.substrate.material || "Not selected"} · {draft.substrate.vendor || "No supplier"} · {draft.substrate.type_number || "No catalog number"}</p>
          <p>{draft.substrate.width_mm || "—"} × {draft.substrate.length_mm || "—"} mm</p>
        </article>
        <article>
          <h3>Ordered functional layers</h3>
          <ol className="builder-review-layers">{draft.layers.map((layer, index) => <li key={`${layer.layer_type}-${index}`}><strong>{layer.name}</strong><span>{layer.role.replace(/_/g, " ")} · {layer.process?.method ?? (layer.layer_type === "perovskite" ? "spin coating + VCD" : "no process")}</span></li>)}</ol>
        </article>
        <article>
          <h3>Perovskite process</h3>
          <dl>
            <div><dt>Spin stages</dt><dd>{draft.deposition_process.spin_steps.length}</dd></div>
            <div><dt>VCD stages</dt><dd>{draft.deposition_process.vcd_stages.length}</dd></div>
            <div><dt>Gas backfills</dt><dd>{draft.deposition_process.gas_backfill_stages.length}</dd></div>
            <div><dt>Annealing stages</dt><dd>{draft.deposition_process.anneal_steps.length}</dd></div>
            <div><dt>VCD sequence</dt><dd><code>{draft.deposition_process.vcd_step_sequence?.join(" → ") || "Not recorded"}</code></dd></div>
          </dl>
        </article>
      </div>

      <div className="builder-review-conditions">
        <h3>Condition plan</h3>
        <div className="table-wrap"><table><thead><tr><th>Condition</th><th>Role</th><th>Layout</th><th>Substrates</th><th>Expected devices</th><th>Snapshot</th></tr></thead><tbody>
          {draft.conditions.map((condition) => {
            const layout = layouts.find((item) => item.code === condition.device_layout_code);
            return <tr key={condition.group_id}><td>{condition.name}</td><td>{condition.kind}</td><td>{layout?.description ?? (condition.device_layout_code || "Not selected")}</td><td>{condition.planned_substrate_count}</td><td>{layout ? layout.devices_per_substrate * condition.planned_substrate_count : "—"}</td><td>{condition.kind === "target" ? "Complete independent copy" : "Primary recipe"}</td></tr>;
          })}
        </tbody></table></div>
      </div>
    </section>
  );
}
