import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { Experiment } from "../types/api";

function stackSummary(experiment: Experiment): string {
  // Derived from the control condition snapshot server-side.
  return experiment.device_summary ?? "";
}

export function ExperimentsPage() {
  const loadExperiments = useCallback(() => apiFetch<Experiment[]>("/api/experiments"), []);
  const resource = useApiResource(loadExperiments);
  const [campaign, setCampaign] = useState("all");
  const [planStatus, setPlanStatus] = useState("all");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return [...(resource.data ?? [])]
      .filter((experiment) => campaign === "all" || (experiment.campaign_id ?? "unassigned") === campaign)
      .filter((experiment) => planStatus === "all" || (experiment.plan_status ?? "unknown") === planStatus)
      .filter((experiment) => {
        if (!normalizedQuery) {
          return true;
        }
        return [
          experiment.experiment_code ?? String(experiment.id),
          experiment.campaign_id ?? "unassigned",
          stackSummary(experiment),
        ].some((value) => value.toLowerCase().includes(normalizedQuery));
      })
      .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at) || right.id - left.id);
  }, [campaign, planStatus, query, resource.data]);
  const campaigns = useMemo(() => [...new Set((resource.data ?? []).map((row) => row.campaign_id ?? "unassigned"))].sort(), [resource.data]);
  const planStatuses = useMemo(() => [...new Set((resource.data ?? []).map((row) => row.plan_status ?? "unknown"))].sort(), [resource.data]);

  const columns: Column<Experiment>[] = [
    {
      key: "experiment_code",
      header: "Experiment",
      render: (row) => <Link className="record-link mono" to={`/experiments/${row.id}`}>{row.experiment_code ?? row.id}</Link>,
    },
    { key: "campaign_id", header: "Campaign", render: (row) => row.campaign_id ?? "unassigned" },
    { key: "plan_type", header: "Plan type", render: (row) => row.plan_type?.replace(/_/g, " ") ?? "—" },
    { key: "plan_status", header: "Plan", render: (row) => row.plan_status ? <StatusBadge status={row.plan_status} /> : "—" },
    { key: "status", header: "Record", render: (row) => <StatusBadge status={row.status} /> },
    { key: "stack", header: "Device stack", render: (row) => <span className="stack-summary" title={stackSummary(row)}>{stackSummary(row)}</span> },
    { key: "updated_at", header: "Updated", render: (row) => formatDateTime(row.updated_at) },
  ];

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading experiments…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load experiments."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="Experiment records"
        description="Authorized planning, fabrication, and characterization records."
        actions={<Link className="button button--primary" to="/experiments/new">Plan new experiment</Link>}
      />
      <section className="panel experiment-filters" aria-label="Experiment filters">
        <FormField label="Campaign" htmlFor="experiment-campaign-filter">
          <select id="experiment-campaign-filter" className="text-input" value={campaign} onChange={(event) => setCampaign(event.target.value)}>
            <option value="all">All Campaigns</option>
            {campaigns.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </FormField>
        <FormField label="Plan status" htmlFor="experiment-status-filter">
          <select id="experiment-status-filter" className="text-input" value={planStatus} onChange={(event) => setPlanStatus(event.target.value)}>
            <option value="all">All statuses</option>
            {planStatuses.map((value) => <option key={value} value={value}>{value.replace(/_/g, " ")}</option>)}
          </select>
        </FormField>
        <FormField label="Search experiments" htmlFor="experiment-search">
          <input id="experiment-search" className="text-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Code, Campaign, or material" />
        </FormField>
        <span className="record-count experiment-filters__count">{rows.length} records</span>
      </section>
      <section className="panel">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          ariaLabel="Experiment records"
          loading={resource.status === "loading"}
          empty={<EmptyState title="No experiments match these filters." />}
        />
      </section>
    </>
  );
}
