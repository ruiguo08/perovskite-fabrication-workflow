import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../auth/session";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import type { FabricationBatchListItem, ResultListItem } from "../types/api";

interface Experiment {
  id: number;
  status: string;
  created_at: string;
  updated_at: string;
  campaign_id: string | null;
  experiment_code: string | null;
  series_version: number | null;
  plan_type: string | null;
  plan_status: string | null;
  recipe: {
    device_recipe?: {
      substrate?: { material?: string };
      layers?: { name: string }[];
    } | null;
  };
}

interface Campaign {
  code: string;
  display_name: string;
  status: string;
}

interface Material {
  id: number;
  status: string;
}

interface DeviceLayoutSummary {
  code: string;
}

interface NextAction {
  label: string;
  detail: string;
  to: string | null;
}

function stackSummary(experiment: Experiment): string {
  const recipe = experiment.recipe?.device_recipe;
  if (!recipe) {
    return "—";
  }
  const parts = [recipe.substrate?.material ?? "Substrate"];
  for (const layer of recipe.layers ?? []) {
    parts.push(layer.name);
  }
  return parts.join(" / ");
}

/**
 * First-use setup checklist, shown to staff while the prerequisites students
 * need for their first experiment are missing: an admin-created device
 * layout and an instructor-created active campaign. Items link to the page
 * that fixes them and the whole panel disappears once everything is in
 * place. Students see it too (read-only, with who to ask) because a blocked
 * builder with no explanation is worse than a visible reason.
 */
function SetupChecklist({ role, layouts, campaigns }: { role: string; layouts: DeviceLayoutSummary[]; campaigns: Campaign[] }) {
  const isStaff = role === "instructor" || role === "administrator";
  const missingLayout = layouts.length === 0;
  const missingCampaign = !campaigns.some((campaign) => campaign.status === "active");
  if (!missingLayout && !missingCampaign) return null;
  const items = [
    missingLayout && {
      title: "No device layouts yet",
      detail: isStaff
        ? "An administrator creates the first device layout (substrate size, devices per substrate) under Device layouts."
        : "Ask an administrator to create the first device layout under Device layouts.",
      to: "/device-layouts",
      linkLabel: "Open device layouts",
    },
    missingCampaign && {
      title: "No active campaign yet",
      detail: isStaff
        ? "Every experiment belongs to a campaign. Create the first active campaign under Campaigns."
        : "Ask an instructor to create the first active campaign under Campaigns.",
      to: "/campaigns",
      linkLabel: "Open campaigns",
    },
  ].filter(Boolean) as { title: string; detail: string; to: string; linkLabel: string }[];
  return (
    <section className="panel panel--accent" aria-labelledby="setup-checklist-title">
      <h2 className="panel__title" id="setup-checklist-title">Finish the first-use setup</h2>
      <ul className="setup-checklist">
        {items.map((item) => (
          <li key={item.title} className="setup-checklist__item">
            <span className="setup-checklist__mark" aria-hidden="true">○</span>
            <div>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              {isStaff ? <Link className="button button--secondary button--small" to={item.to}>{item.linkLabel}</Link> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

const COLUMNS: Column<Experiment>[] = [
  {
    key: "experiment_code",
    header: "Experiment",
    render: (row) => <Link className="record-link mono" to={`/experiments/${row.id}`}>{row.experiment_code ?? row.id}</Link>,
  },
  { key: "campaign_id", header: "Series" },
  {
    key: "plan_status",
    header: "Plan",
    render: (row) =>
      row.plan_status ? <StatusBadge status={row.plan_status} /> : "—",
  },
  {
    key: "status",
    header: "Status",
    render: (row) => <StatusBadge status={row.status} />,
  },
  {
    key: "device_stack",
    header: "Device stack",
    render: (row) => (
      <span className="stack-summary" title={stackSummary(row)}>
        {stackSummary(row)}
      </span>
    ),
  },
  {
    key: "updated_at",
    header: "Updated",
    render: (row) => formatDateTime(row.updated_at),
  },
];

export function OverviewPage() {
  const { user } = useSession();
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [materials, setMaterials] = useState<Material[] | null>(null);
  const [layouts, setLayouts] = useState<DeviceLayoutSummary[] | null>(null);
  const [batches, setBatches] = useState<FabricationBatchListItem[] | null>(null);
  const [results, setResults] = useState<ResultListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [experimentRows, campaignRows, materialRows, layoutRows, batchRows, resultRows] = await Promise.all([
        apiFetch<Experiment[]>("/api/experiments"),
        apiFetch<Campaign[]>("/api/campaigns"),
        apiFetch<Material[]>("/api/materials"),
        apiFetch<DeviceLayoutSummary[]>("/api/device-layouts"),
        apiFetch<FabricationBatchListItem[]>("/api/fabrication-batches"),
        apiFetch<ResultListItem[]>("/api/results"),
      ]);
      setExperiments(experimentRows);
      setCampaigns(campaignRows);
      setMaterials(materialRows);
      setLayouts(layoutRows);
      setBatches(batchRows);
      setResults(resultRows);
      setError(null);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Unable to load overview data.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <ErrorState
        message={error}
        action={
          <button type="button" className="button button--secondary" onClick={() => void load()}>
            Retry
          </button>
        }
      />
    );
  }

  if (experiments === null || campaigns === null || materials === null || layouts === null || batches === null || results === null) {
    return (
      <div
        className="app-loading"
        role="status"
        aria-label="Loading overview data"
      >
        Loading overview data…
      </div>
    );
  }

  const planStatusCounts = new Map<string, number>();
  for (const experiment of experiments ?? []) {
    const planStatus = experiment.plan_status ?? "unknown";
    planStatusCounts.set(planStatus, (planStatusCounts.get(planStatus) ?? 0) + 1);
  }

  const recent = [...experiments]
    .sort((a, b) => {
      const timeDifference = Date.parse(b.updated_at) - Date.parse(a.updated_at);
      return timeDifference === 0 ? b.id - a.id : timeDifference;
    })
    .slice(0, 10);

  const nextActions: NextAction[] = [
    ...results.filter((result) => !result.group_assignment).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).map((result) => ({
      label: `Assign ${result.filename}`,
      detail: "Assign substrate conditions to use this result in statistics and uniformity.",
      to: `/results/${result.id}`,
    })),
    ...batches.filter((batch) => batch.status === "in_progress").sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).map((batch) => ({
      label: `Continue ${batch.batch_code}`,
      detail: "Record fabrication steps and complete the run sheet.",
      to: `/experiments/${batch.experiment_id}/batches/${batch.id}`,
    })),
    ...batches.filter((batch) => batch.status === "ready").map((batch) => ({
      label: `Start ${batch.batch_code}`,
      detail: "The run sheet is ready for fabrication.",
      to: `/experiments/${batch.experiment_id}/batches/${batch.id}`,
    })),
    ...batches.filter((batch) => batch.status === "draft").map((batch) => ({
      label: `Prepare ${batch.batch_code}`,
      detail: "Finish the run sheet and mark the batch ready.",
      to: `/experiments/${batch.experiment_id}/batches/${batch.id}`,
    })),
    ...batches.filter((batch) => batch.status === "completed" && !results.some((result) => result.fabrication_batch_id === batch.id)).map((batch) => ({
      label: `Upload results for ${batch.batch_code}`,
      detail: "Add the measurement CSV, then assign each substrate to its condition.",
      to: `/experiments/${batch.experiment_id}/upload`,
    })),
    ...(user?.role === "instructor" || user?.role === "administrator" ? experiments.filter((experiment) => experiment.plan_status === "pending_approval").map((experiment) => ({
      label: `Approve ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "Review the submitted plan before fabrication.",
      to: `/experiments/${experiment.id}`,
    })) : []),
    ...experiments.filter((experiment) => experiment.plan_status === "draft").map((experiment) => ({
      label: `Continue ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "Finish and submit the draft plan.",
      to: `/experiments/${experiment.id}`,
    })),
    ...experiments.filter((experiment) => experiment.plan_status === "approved").map((experiment) => ({
      label: `Release ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "Release the approved plan before freezing a fabrication batch.",
      to: `/experiments/${experiment.id}`,
    })),
    ...experiments.filter((experiment) => experiment.plan_status === "released" && !batches.some((batch) => batch.experiment_id === experiment.id && batch.status !== "cancelled")).map((experiment) => ({
      label: `Freeze a batch for ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "At least one active batch is required to start fabrication.",
      to: `/experiments/${experiment.id}`,
    })),
    ...experiments.filter((experiment) => experiment.plan_status === "released" && batches.some((batch) => batch.experiment_id === experiment.id && batch.status !== "cancelled")).map((experiment) => ({
      label: `Start fabrication for ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "The plan has a fabrication batch and can enter the in-progress stage.",
      to: `/experiments/${experiment.id}`,
    })),
    ...experiments.filter((experiment) => experiment.plan_status === "in_progress" &&
      batches.some((batch) => batch.experiment_id === experiment.id && batch.status === "completed") &&
      batches.filter((batch) => batch.experiment_id === experiment.id).every((batch) => batch.status === "completed" || batch.status === "cancelled")
    ).map((experiment) => ({
      label: `Complete ${experiment.experiment_code ?? `experiment ${experiment.id}`}`,
      detail: "All fabrication batches are terminal; finish the plan lifecycle.",
      to: `/experiments/${experiment.id}`,
    })),
    ...(user?.role === "student" ? experiments.filter((experiment) => experiment.plan_status === "pending_approval").map((experiment) => ({
      label: experiment.experiment_code ?? `Experiment ${experiment.id}`,
      detail: "Waiting for instructor approval before the plan can be released.",
      to: null,
    })) : []),
  ].slice(0, 5);

  return (
    <>
      <PageHeader title="Overview" description="Laboratory activity at a glance." />
      <SetupChecklist role={user?.role ?? ""} layouts={layouts} campaigns={campaigns} />
      <section className="panel next-actions" aria-labelledby="next-actions-title">
        <h2 className="panel__title" id="next-actions-title">Next actions</h2>
        {nextActions.length === 0 ? (
          <p className="run-sheet-muted">No work needs attention right now.</p>
        ) : (
          <ol className="next-actions__list">
            {nextActions.map((action) => (
              <li key={`${action.to}-${action.label}`}>
                {action.to ? <Link className="record-link" to={action.to}>{action.label}</Link> : <strong>{action.label}</strong>}
                <p>{action.detail}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
      <div className="stat-tiles">
        <Link className="stat-tile" to="/experiments" aria-label={`${experiments?.length ?? "…"} experiments, view all experiments`}>
          <span className="stat-tile__value">{experiments?.length ?? "…"}</span>
          <span className="stat-tile__label">Experiments</span>
        </Link>
        <Link className="stat-tile" to="/campaigns" aria-label="View campaigns">
          <span className="stat-tile__value">
            {campaigns?.filter((campaign) => campaign.status === "active").length ?? "…"}
          </span>
          <span className="stat-tile__label">Active campaigns</span>
        </Link>
        <Link className="stat-tile" to="/materials" aria-label={`${materials?.length ?? "…"} materials, view all materials`}>
          <span className="stat-tile__value">{materials?.length ?? "…"}</span>
          <span className="stat-tile__label">Materials</span>
        </Link>
      </div>

      <section className="panel">
        <h2 className="panel__title">Plan status</h2>
        {planStatusCounts.size === 0 ? (
          <EmptyState
            title="No experiments yet."
            description="Start by planning your first comparative deposition experiment."
            action={
              <Link className="button button--primary" to="/experiments/new">
                Plan an experiment
              </Link>
            }
          />
        ) : (
          <ul className="plan-status-list">
            {[...planStatusCounts.entries()].map(([status, count]) => (
              <li key={status} className="plan-status-list__item">
                <StatusBadge status={status} />
                <span className="plan-status-list__count">{count}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <div className="panel__heading">
          <h2 className="panel__title">Recent experiments</h2>
          <Link className="button button--secondary button--small" to="/experiments">
            View all
          </Link>
        </div>
        <DataTable
          columns={COLUMNS}
          rows={recent}
          rowKey={(row) => row.id}
          ariaLabel="Recent experiments"
          empty={<EmptyState title="No experiments yet." />}
        />
      </section>
    </>
  );
}
