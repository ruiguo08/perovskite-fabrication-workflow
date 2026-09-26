import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { ResultListItem } from "../types/api";

function buildQuery(experimentId: string, batchId: string): string {
  const params = new URLSearchParams();
  if (experimentId.trim() !== "") {
    params.set("experiment_id", experimentId.trim());
  }
  if (batchId.trim() !== "") {
    params.set("fabrication_batch_id", batchId.trim());
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function ResultsPage() {
  const [experimentId, setExperimentId] = useState("");
  const [batchId, setBatchId] = useState("");
  const loadResults = useCallback(
    () => apiFetch<ResultListItem[]>(`/api/results${buildQuery(experimentId, batchId)}`),
    [experimentId, batchId],
  );
  const resource = useApiResource(loadResults, { resetOnLoaderChange: true });

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading results…</div>;
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
          title="Unable to load results"
          message={resource.error ?? "The results could not be loaded."}
          action={retry}
        />
      );
    }
    return (
      <div className="inline-form-error" role="alert">
        <p>
          Unable to refresh results: {resource.error ?? "the request failed."}{" "}
          The displayed rows may not match the selected filter.
        </p>
        {retry}
      </div>
    );
  }
  const results = resource.data ?? [];

  return (
    <>
      <PageHeader
        title="Characterization results"
        description="Every uploaded result file authorized for your role, newest first."
        meta={`${results.length} records`}
      />
      <section className="panel" aria-labelledby="result-list-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="result-list-title">Result records</h2>
          <div className="filter-grid">
            <label className="form-field">
              <span className="form-field__label">Experiment</span>
              <input
                className="text-input"
                aria-label="Experiment"
                inputMode="numeric"
                placeholder="Experiment id"
                value={experimentId}
                onChange={(event) => setExperimentId(event.target.value)}
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Batch</span>
              <input
                className="text-input"
                aria-label="Batch"
                inputMode="numeric"
                placeholder="Fabrication batch id"
                value={batchId}
                onChange={(event) => setBatchId(event.target.value)}
              />
            </label>
          </div>
        </div>
        {results.length === 0 ? (
          <EmptyState
            title="No characterization results."
            description="Uploaded result files appear here once an in-progress batch is characterized."
          />
        ) : (
          <div className="result-list">
            {results.map((result) => (
              <article className="result-summary-card" key={result.id} data-result-row={result.id}>
                <div className="result-summary-card__row">
                  <Link className="record-link" to={`/results/${result.id}`}>
                    {result.filename}
                  </Link>
                  <span className="run-sheet-muted">{formatDateTime(result.created_at)}</span>
                </div>
                <span className="record-title">
                  {result.experiment_code ?? `Experiment ${result.experiment_id}`}
                </span>
                <span className="run-sheet-muted">{result.batch_code}</span>
                <span className="run-sheet-muted">{result.size_bytes} bytes</span>
                <code title={result.sha256}>{result.sha256.slice(0, 16)}…</code>
                <span className="run-sheet-muted">Schema v{result.analysis_schema_version}</span>
                {result.group_assignment ? (
                  <span className="run-sheet-muted">Assigned</span>
                ) : (
                  <span className="run-sheet-muted">Unassigned</span>
                )}
                <Link className="record-link" to={`/results/${result.id}`}>View direction-specific statistics</Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
