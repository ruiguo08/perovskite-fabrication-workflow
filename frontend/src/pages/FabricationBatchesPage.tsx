import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { FabricationBatchListItem } from "../types/api";

const BATCH_STATUSES = ["draft", "ready", "in_progress", "completed", "cancelled"];

export function FabricationBatchesPage() {
  const [statusFilter, setStatusFilter] = useState("all");
  const loadBatches = useCallback(() => {
    const query = statusFilter === "all" ? "" : `?status=${statusFilter}`;
    return apiFetch<FabricationBatchListItem[]>(`/api/fabrication-batches${query}`);
  }, [statusFilter]);
  const resource = useApiResource(loadBatches, { resetOnLoaderChange: true });

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading fabrication batches…</div>;
  }
  if (resource.status === "error") {
    const retry = (
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>
        Retry
      </button>
    );
    if (resource.data === null) {
      return (
        <ErrorState
          title="Unable to load fabrication batches"
          message={resource.error ?? "The fabrication batches could not be loaded."}
          action={retry}
        />
      );
    }
    return (
      <div className="inline-form-error" role="alert">
        <p>
          Unable to refresh fabrication batches: {resource.error ?? "the request failed."}{" "}
          The displayed results may not match the selected filter.
        </p>
        {retry}
      </div>
    );
  }
  const batches = resource.data ?? [];

  return (
    <>
      <PageHeader
        title="Fabrication batches"
        description="Every fabrication batch authorized for your role, newest first."
        meta={`${batches.length} records`}
      />
      <section className="panel" aria-labelledby="batch-list-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="batch-list-title">Batch records</h2>
          <label className="form-field">
            <span className="form-field__label">Batch status</span>
            <select
              className="text-input"
              aria-label="Batch status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">All statuses</option>
              {BATCH_STATUSES.map((status) => (
                <option key={status} value={status}>{status.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
        </div>
        {batches.length === 0 ? (
          <EmptyState title="No fabrication batches yet." description="Fabrication batches appear here once a plan is released and a batch is frozen." />
        ) : (
          <div className="batch-list">
            {batches.map((batch) => (
              <article className="batch-summary-card" key={batch.id} data-batch-row={batch.id}>
                <div className="batch-summary-card__row">
                  <Link
                    className="record-link"
                    to={`/experiments/${batch.experiment_id}/batches/${batch.id}`}
                  >
                    {batch.batch_code}
                  </Link>
                  <StatusBadge status={batch.status} />
                </div>
                <span className="record-title">
                  {batch.experiment_code ?? `Experiment ${batch.experiment_id}`}
                </span>
                <code>{batch.condition_set_hash}</code>
                <span>{batch.notes || "No batch notes."}</span>
                <span className="run-sheet-muted">Created {formatDateTime(batch.created_at)}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}