import { useCallback, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../auth/session";
import { ConditionCard } from "../components/ConditionCard";
import { ConditionComparison } from "../components/ConditionComparison";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { RecipeSnapshotSummary } from "../components/RecipeSnapshotSummary";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { formatDateTime, formatNumber, scaleMetric } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { ExperimentDetail, FabricationBatchSummary, SubstrateException } from "../types/api";
interface PlanAction {
  status: "pending_approval" | "approved" | "released" | "in_progress" | "completed" | "cancelled";
  label: string;
  tone: "primary" | "danger";
}

function primaryPlanAction(detail: ExperimentDetail, canApprove: boolean): PlanAction | null {
  const status = detail.experiment.plan_status;
  if (status === "draft") {
    // Strict approval workflow: a draft can only be submitted for approval.
    // Releasing requires an explicit instructor approval step first.
    return { status: "pending_approval", label: "Submit for approval", tone: "primary" };
  }
  if (status === "pending_approval" && canApprove) {
    return { status: "approved", label: "Approve plan", tone: "primary" };
  }
  if (status === "approved") {
    return { status: "released", label: "Release approved plan", tone: "primary" };
  }
  if (status === "released") {
    return { status: "in_progress", label: "Start fabrication", tone: "primary" };
  }
  if (status === "in_progress") {
    return { status: "completed", label: "Complete fabrication", tone: "primary" };
  }
  return null;
}

export function ExperimentDetailPage() {
  const { experimentId } = useParams();
  const id = Number(experimentId);
  const { user } = useSession();
  const { show } = useToast();
  const canApprove = user?.role === "instructor" || user?.role === "administrator";
  const loadDetail = useCallback(() => apiFetch<ExperimentDetail>(`/api/experiments/${id}`), [id]);
  const resource = useApiResource(loadDetail);
  const [localDetail, setLocalDetail] = useState<ExperimentDetail | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [batchNotes, setBatchNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const serverDetail = resource.data;
  const detail = localDetail ?? serverDetail;
  // Only render a detail whose id matches the current route; a stale detail
  // from a previous experiment route is never shown or used for mutations.
  const activeDetail = detail && detail.experiment.id === id ? detail : null;

  // Route-generation guard: invalidate the previous experiment during the
  // synchronous commit phase (useLayoutEffect) and on unmount, so a
  // late-resolving plan-status or batch mutation for experiment A cannot
  // overwrite experiment B's page or show a stale toast.
  const routeGeneration = useRef(0);
  const routeKey = `${id}`;
  useLayoutEffect(() => {
    routeGeneration.current += 1;
    setLocalDetail(null);
    setActionError(null);
    setBatchNotes("");
    setSubmitting(false);
    return () => {
      routeGeneration.current += 1;
    };
  }, [routeKey]);

  const isCurrentGeneration = useCallback(
    (generation: number) => routeGeneration.current === generation,
    [],
  );
  const exceptionsByCondition = useMemo(
    () => new Map((activeDetail?.substrate_exceptions ?? []).map((exception) => [exception.condition_id, exception])),
    [activeDetail?.substrate_exceptions],
  );

  function updateException(replacement: SubstrateException) {
    if (!activeDetail) {
      return;
    }
    const existing = activeDetail.substrate_exceptions.some((exception) => exception.condition_id === replacement.condition_id);
    setLocalDetail({
      ...activeDetail,
      substrate_exceptions: existing
        ? activeDetail.substrate_exceptions.map((exception) => exception.condition_id === replacement.condition_id ? replacement : exception)
        : [...activeDetail.substrate_exceptions, replacement],
    });
  }

  async function changePlanStatus(action: PlanAction) {
    if (!activeDetail) {
      return;
    }
    const generation = routeGeneration.current;
    setSubmitting(true);
    setActionError(null);
    try {
      await apiFetch<void>(`/api/experiments/${id}/plan-status`, {
        method: "PATCH",
        body: { status: action.status },
      });
      if (!isCurrentGeneration(generation)) {
        return;
      }
      setLocalDetail({ ...activeDetail, experiment: { ...activeDetail.experiment, plan_status: action.status } });
      show(`Plan status changed to ${action.status.replace(/_/g, " ")}.`, "success");
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setActionError(caught instanceof Error ? caught.message : "Unable to update the plan status.");
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  async function createBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeDetail) {
      return;
    }
    const generation = routeGeneration.current;
    setSubmitting(true);
    setActionError(null);
    try {
      const created = await apiFetch<FabricationBatchSummary>(`/api/experiments/${id}/fabrication-batches`, {
        method: "POST",
        body: { notes: batchNotes.trim() },
      });
      if (!isCurrentGeneration(generation)) {
        return;
      }
      setLocalDetail({ ...activeDetail, fabrication_batches: [...activeDetail.fabrication_batches, created] });
      setBatchNotes("");
      show("Fabrication batch frozen from the approved condition snapshots.", "success");
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setActionError(caught instanceof Error ? caught.message : "Unable to create the fabrication batch.");
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  if (!Number.isInteger(id) || id <= 0) {
    return <ErrorState title="Invalid experiment" message="The experiment identifier is not valid." />;
  }
  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading experiment…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState title="Unable to load experiment" message={resource.error ?? "The experiment could not be loaded."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }
  if (!activeDetail) {
    return null;
  }

  const experiment = activeDetail.experiment;
  const action = primaryPlanAction(activeDetail, canApprove);
  const terminal = experiment.plan_status === "completed" || experiment.plan_status === "cancelled";
  // Batches can be frozen while released (normal path) or while fabrication
  // is already in progress (recovery when the student started without one).
  const canFreezeBatches =
    experiment.plan_status === "released" || experiment.plan_status === "in_progress";
  const missingBatches = canFreezeBatches && activeDetail.fabrication_batches.length === 0;
  // The device stack comes from the control (or standalone) condition
  // snapshot: the authoritative, hash-verified configuration.
  const controlCondition =
    activeDetail.conditions.find((condition) => condition.role !== "target") ??
    activeDetail.conditions[0];
  const recipe = controlCondition?.recipe_snapshot.device ?? null;
  const process = activeDetail.conditions[0]?.recipe_snapshot.deposition_process ?? null;

  return (
    <>
      <PageHeader
        title={experiment.experiment_code ?? `Experiment ${experiment.id}`}
        description={`${experiment.plan_type?.replace(/_/g, " ") ?? "Unclassified"} plan in ${experiment.campaign_id ?? "unassigned Campaign"}.`}
        meta={`Updated ${formatDateTime(experiment.updated_at)}`}
        actions={
          <>
            <a className="button button--secondary" href={`/experiments/${id}/export.json`}>Export JSON</a>
            <a className="button button--secondary" href={`/experiments/${id}/export.pdf`}>Export PDF</a>
            <Link className="button button--secondary" to="/experiments">Back to records</Link>
          </>
        }
      />

      <section className="panel experiment-summary" aria-labelledby="experiment-summary-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="experiment-summary-title">Plan summary</h2>
          <div className="status-row">
            <StatusBadge status={experiment.status} />
            {experiment.plan_status ? <StatusBadge status={experiment.plan_status} /> : null}
          </div>
        </div>
        {recipe ? (
          <RecipeSnapshotSummary deviceRecipe={recipe} depositionProcess={process} />
        ) : null}
      </section>

      {!terminal ? (
        <section className="panel plan-actions" aria-labelledby="plan-actions-title">
          <h2 className="panel__title" id="plan-actions-title">Plan actions</h2>
          <div className="button-row">
            {action ? (
              <button className={`button button--${action.tone}`} type="button" disabled={submitting} onClick={() => void changePlanStatus(action)}>{action.label}</button>
            ) : null}
            <button className="button button--danger" type="button" disabled={submitting} onClick={() => void changePlanStatus({ status: "cancelled", label: "Cancel plan", tone: "danger" })}>Cancel plan</button>
          </div>
          <InlineFormError message={actionError} />
          {missingBatches ? (
            <p className="inline-warning" role="status">
              No fabrication batches yet. Freeze at least one batch below before starting or
              completing fabrication — characterization CSV uploads require a batch.
            </p>
          ) : null}
        </section>
      ) : null}

      <section className="catalog-group" aria-labelledby="condition-directory-title">
        <div className="catalog-group__heading">
          <h2 id="condition-directory-title">Conditions</h2>
          <span className="record-count">{activeDetail.conditions.length} records</span>
        </div>
        {activeDetail.conditions.length > 0 ? <ConditionComparison conditions={activeDetail.conditions} /> : null}
        <div className="condition-list">
          {activeDetail.conditions.map((condition) => (
            <ConditionCard
              key={condition.id}
              condition={condition}
              exception={exceptionsByCondition.get(condition.id) ?? null}
              planStatus={experiment.plan_status}
              onExceptionChange={updateException}
            />
          ))}
        </div>
      </section>

      <section className="panel" aria-labelledby="batch-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="batch-directory-title">Fabrication batches</h2>
          <span className="record-count">{activeDetail.fabrication_batches.length} records</span>
        </div>
        {canFreezeBatches ? (
          <form className="batch-create-form" onSubmit={(event) => void createBatch(event)}>
            <FormField label="Batch notes" htmlFor="batch-notes">
              <input id="batch-notes" className="text-input" maxLength={2000} value={batchNotes} onChange={(event) => setBatchNotes(event.target.value)} />
            </FormField>
            <button className="button button--primary" type="submit" disabled={submitting}>Freeze fabrication batch</button>
          </form>
        ) : null}
        {activeDetail.fabrication_batches.length === 0 ? (
          <EmptyState
            title="No fabrication batches yet."
            description={
              canFreezeBatches
                ? "Freeze a batch from the approved condition snapshots above — starting fabrication and CSV result uploads both require at least one batch."
                : "Release the plan before freezing execution records."
            }
          />
        ) : (
          <div className="batch-list">
            {activeDetail.fabrication_batches.map((batch) => (
              <article className="batch-summary-card" key={batch.id}>
                <div><Link className="record-link" to={`/experiments/${id}/batches/${batch.id}`}>{batch.batch_code}</Link><StatusBadge status={batch.status} /></div>
                <code>{batch.condition_set_hash}</code>
                <span>{batch.notes || "No notes"}</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel" aria-labelledby="result-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="result-directory-title">Characterization results</h2>
          <Link className="button button--secondary button--small" to={`/experiments/${id}/upload`}>Upload results</Link>
        </div>
        {activeDetail.results.length === 0 ? <EmptyState title="No characterization results uploaded." /> : (
          <div className="result-list">
            {activeDetail.results.map((result) => (
              <article className="result-summary-card" key={result.id} data-result-row={result.id}>
                <Link className="record-link" to={`/results/${result.id}`}>{result.filename}</Link>
                <code>{result.sha256}</code>
                <span>{Object.entries(result.metrics).map(([key, value]) => `${key}: ${formatNumber(scaleMetric(key, value), key === "voc" ? 3 : 2)}`).join(" · ") || "No summary metrics"}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
