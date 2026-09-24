import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { useApiResource } from "../lib/useApiResource";
import type { ExperimentDetail } from "../types/api";

const MAX_RESULT_FILE_BYTES = 10 * 1024 * 1024;
const ELIGIBLE_STATUSES = new Set(["in_progress", "completed"]);

interface UploadedResult {
  id: number;
}

export function UploadResultPage() {
  const { experimentId } = useParams();
  const experimentIdNumber = Number(experimentId);
  const navigate = useNavigate();
  const { show } = useToast();
  const loadExperiment = useCallback(
    () => apiFetch<ExperimentDetail>(`/api/experiments/${experimentIdNumber}`),
    [experimentIdNumber],
  );
  const resource = useApiResource(loadExperiment, { resetOnLoaderChange: true });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [batchId, setBatchId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Route-generation guard: synchronously invalidate on experimentId change
  // and on unmount so a pending upload response cannot navigate or show a
  // stale toast after the user leaves the page.
  const routeGeneration = useRef(0);
  const routeKey = `${experimentIdNumber}`;
  useLayoutEffect(() => {
    routeGeneration.current += 1;
    setFile(null);
    setBatchId("");
    setSubmitting(false);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    return () => {
      routeGeneration.current += 1;
    };
  }, [routeKey]);
  const isCurrentGeneration = useCallback(
    (generation: number) => routeGeneration.current === generation,
    [],
  );

  const detail = resource.data;
  // Only render experiment data whose id matches the URL; a stale response from
  // a previous experiment route is never shown or used for an upload.
  const activeDetail = detail && detail.experiment.id === experimentIdNumber ? detail : null;

  const eligibleBatches = useMemo(
    () => (activeDetail?.fabrication_batches ?? []).filter((batch) => ELIGIBLE_STATUSES.has(batch.status)),
    [activeDetail],
  );

  // The experiment API returns per-condition records (not the legacy
  // recipe.device_recipe.experimental_groups blob): condition_name is the
  // display name and role is the control/target/standalone kind.
  const groups = useMemo(
    () => activeDetail?.conditions ?? [],
    [activeDetail],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const generation = routeGeneration.current;
    setError(null);
    if (!activeDetail) {
      return;
    }
    if (!file) {
      setError("Choose a CSV result file before submitting.");
      return;
    }
    if (file.size > MAX_RESULT_FILE_BYTES) {
      setError("Result file must not exceed 10 MB. Choose a smaller file.");
      return;
    }
    if (!batchId) {
      setError("Choose the fabrication batch that produced these devices.");
      return;
    }
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("fabrication_batch_id", batchId);
      formData.append("result_file", file);
      const uploaded = await apiFetch<UploadedResult>(
        `/api/experiments/${experimentIdNumber}/results`,
        { method: "POST", multipart: formData },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      show("Result uploaded. Assigning devices to conditions…", "success");
      navigate(`/results/${uploaded.id}`);
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setError(caught instanceof Error ? caught.message : "Unable to upload the result file.");
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setError(null);
  }

  if (resource.status === "loading" && activeDetail === null) {
    return <div className="page-loading" role="status">Loading experiment…</div>;
  }
  if (resource.status === "error" && activeDetail === null) {
    return (
      <ErrorState
        title="Unable to load experiment"
        message={resource.error ?? "The experiment could not be loaded."}
        action={
          <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>
            Retry
          </button>
        }
      />
    );
  }
  if (!activeDetail) {
    return null;
  }

  return (
    <>
      <PageHeader
        title="Upload characterization result"
        description="Read devices from a JV CSV and continue to the assignment step."
        meta={null}
        actions={<Link className="button button--secondary" to={`/experiments/${experimentIdNumber}`}>Back to plan</Link>}
      />
      {groups.length > 0 ? (
        <section className="panel" aria-labelledby="expected-groups-title">
          <div className="panel__heading">
            <h2 className="panel__title" id="expected-groups-title">Expected groups</h2>
          </div>
          <div className="badge-row">
            {groups.map((condition) => (
              <span
                key={condition.condition_code}
                className={`status-badge ${condition.role === "control" ? "status-badge--neutral" : "status-badge--planned"}`}
              >
                {condition.condition_name}
              </span>
            ))}
          </div>
        </section>
      ) : null}
      {eligibleBatches.length === 0 ? (
        <EmptyState
          title="No eligible fabrication batches."
          description="Start a fabrication batch and mark it in progress before uploading results."
        />
      ) : (
        <form className="panel" aria-labelledby="upload-form-title" onSubmit={(event) => void submit(event)}>
          <div className="panel__heading">
            <h2 className="panel__title" id="upload-form-title">Result file</h2>
          </div>
          <label className="form-field">
            <span className="form-field__label">Fabrication batch</span>
            <select
              className="text-input"
              aria-label="Fabrication batch"
              value={batchId}
              onChange={(event) => setBatchId(event.target.value)}
            >
              <option value="">Choose the batch that produced these devices…</option>
              {eligibleBatches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.batch_code} ({batch.status.replace(/_/g, " ")})
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-field__label">CSV result file</span>
            <input
              ref={fileInputRef}
              className="text-input"
              type="file"
              accept=".csv,text/csv"
              aria-label="CSV result file"
              onChange={selectFile}
            />
          </label>
          <p className="run-sheet-muted">Maximum size 10 MB. The server re-validates size, type, and integrity.</p>
          <button className="button button--primary" type="submit" disabled={submitting}>
            {submitting ? "Reading devices…" : "Read devices and continue"}
          </button>
          <InlineFormError message={error} />
        </form>
      )}
    </>
  );
}
