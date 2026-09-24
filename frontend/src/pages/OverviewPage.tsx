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
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [experimentRows, campaignRows, materialRows, layoutRows] = await Promise.all([
        apiFetch<Experiment[]>("/api/experiments"),
        apiFetch<Campaign[]>("/api/campaigns"),
        apiFetch<Material[]>("/api/materials"),
        apiFetch<DeviceLayoutSummary[]>("/api/device-layouts"),
      ]);
      setExperiments(experimentRows);
      setCampaigns(campaignRows);
      setMaterials(materialRows);
      setLayouts(layoutRows);
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

  if (experiments === null || campaigns === null || materials === null || layouts === null) {
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

  return (
    <>
      <PageHeader title="Overview" description="Laboratory activity at a glance." />
      <SetupChecklist role={user?.role ?? ""} layouts={layouts} campaigns={campaigns} />
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
