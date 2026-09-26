import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../auth/session";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { CompleteBatchDialog, type CompleteConditionInput } from "../components/CompleteBatchDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import { DeviationSection } from "./batch-detail/DeviationSection";
import { ExecutionSection } from "./batch-detail/ExecutionSection";
import { PreparationSection } from "./batch-detail/PreparationSection";
import type {
  BatchRunSheet,
  CompletionShortfallDeviation,
  Deviation,
  ProcessExecution,
  SolutionPreparation,
} from "../types/api";

const BATCH_NEXT_STATUS: Record<string, { status: string; label: string } | null> = {
  draft: { status: "ready", label: "Mark ready" },
  ready: { status: "in_progress", label: "Start execution" },
  in_progress: { status: "completed", label: "Complete batch" },
};

export function BatchDetailPage() {
  const { experimentId, batchId } = useParams();
  const experimentIdNumber = Number(experimentId);
  const id = Number(batchId);
  const { user } = useSession();
  const { show } = useToast();
  const canCancel = user?.role === "instructor" || user?.role === "administrator";
  const loadSheet = useCallback(
    () => apiFetch<BatchRunSheet>(`/api/fabrication-batches/${id}/run-sheet`),
    [id],
  );
  const resource = useApiResource(loadSheet, { resetOnLoaderChange: true });
  const [localSheet, setLocalSheet] = useState<BatchRunSheet | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<{
    title: string;
    message: string;
    run: () => Promise<void>;
  } | null>(null);
  const [pendingCompletedCounts, setPendingCompletedCounts] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const sheet = localSheet ?? resource.data;

  // Guard against old-route async operations touching the current route. Each
  // mutation captures the route generation it started on; after every await it
  // bails out if the route changed, so a slow save/split/merge from batch A can
  // never mutate batch B's state, toast the user, or refetch A's run sheet.
  const routeGeneration = useRef(0);

  // Invalidate the previous route during the synchronous commit phase so no
  // Promise microtask can observe a stale route after batch B commits. A passive
  // useEffect would run after the browser paint, leaving a window in which a
  // route-A continuation (PATCH refetch, toast, state update) could still pass
  // isCurrentGeneration and supersede B. useLayoutEffect runs synchronously
  // before any microtask is drained, so by the time any awaited Promise resumes,
  // routeGeneration already reflects the new route.
  const routeKey = `${experimentIdNumber}:${id}`;
  useLayoutEffect(() => {
    routeGeneration.current += 1;
    setLocalSheet(null);
    setActionError(null);
    setSubmitting(false);
    setPendingConfirm(null);
    setRefreshFailed(false);
    // Route-scoped form state inside child sections is remounted via key.
  }, [routeKey]);

  const isCurrentGeneration = useCallback(
    (generation: number) => routeGeneration.current === generation,
    [],
  );

  // Clear the refresh-failure block once any load succeeds so the authoritative
  // fresh run sheet renders (used by the post-failure Retry path).
  useEffect(() => {
    if (resource.status === "success") {
      setRefreshFailed(false);
      setActionError(null);
      setLocalSheet(null);
    }
  }, [resource.status]);

  // A sheet whose batch does not match the current route is stale: never
  // render it as the current batch or expose its mutation actions.
  const activeSheet: BatchRunSheet | null =
    sheet !== null && sheet.batch.id === id ? sheet : null;

  const replacePreparation = useCallback((replacement: SolutionPreparation) => {
    setLocalSheet((current) => {
      const base = current ?? resource.data;
      if (!base) {
        return current;
      }
      return {
        ...base,
        preparations: base.preparations.map((item) =>
          item.preparation.id === replacement.id
            ? { ...item, preparation: replacement }
            : item,
        ),
      };
    });
  }, [resource.data]);

  const replaceExecution = useCallback((replacement: ProcessExecution) => {
    setLocalSheet((current) => {
      const base = current ?? resource.data;
      if (!base) {
        return current;
      }
      return {
        ...base,
        executions: base.executions.map((item) =>
          item.execution.id === replacement.id
            ? { ...item, execution: replacement }
            : item,
        ),
      };
    });
  }, [resource.data]);

  async function savePreparation(preparation: SolutionPreparation, payload: Record<string, unknown>) {
    const generation = routeGeneration.current;
    try {
      const updated = await apiFetch<SolutionPreparation>(
        `/api/fabrication-batches/${id}/solution-preparations/${preparation.id}`,
        { method: "PATCH", body: payload },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      replacePreparation(updated);
      show("Solution preparation saved.", "success");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to save the preparation.");
    }
  }

  async function saveExecution(execution: ProcessExecution, payload: Record<string, unknown>) {
    const generation = routeGeneration.current;
    try {
      const updated = await apiFetch<ProcessExecution>(
        `/api/fabrication-batches/${id}/process-executions/${execution.id}`,
        { method: "PATCH", body: payload },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      replaceExecution(updated);
      show("Process execution saved.", "success");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to save the execution.");
    }
  }

  async function refetchSheet(message: string) {
    const generation = routeGeneration.current;
    const outcome = await resource.reload();
    if (!isCurrentGeneration(generation)) {
      // A newer route owns the resource now; never surface this refresh.
      return;
    }
    if (outcome === "applied") {
      // Drop the optimistic copy so the authoritative fresh run sheet renders
      // (a previous PATCH localSheet would otherwise mask topology changes
      // such as split/merge preparation and execution counts).
      setLocalSheet(null);
      setActionError(null);
      setRefreshFailed(false);
      show(message, "success");
      return;
    }
    if (outcome === "superseded") {
      // A newer reload on this same route owns the data and will settle the
      // sheet when it lands. Stay silent and keep the optimistic copy: a
      // premature success toast or localSheet wipe here would briefly show
      // the pre-split topology as if the split had been applied.
      return;
    }
    // Do not let the previous run sheet masquerade as the current batch after
    // a failed refresh: mark the refresh failure so the error state renders.
    setLocalSheet(null);
    setRefreshFailed(true);
    setActionError(
      "Unable to refresh the run sheet. The displayed data may be outdated; verify the current batch state before continuing.",
    );
  }

  async function changeBatchStatus(nextStatus: string) {
    const generation = routeGeneration.current;
    if (!activeSheet) {
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      await apiFetch<void>(`/api/fabrication-batches/${id}/status`, {
        method: "PATCH",
        body: { status: nextStatus },
      });
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet(`Batch status changed to ${nextStatus.replace(/_/g, " ")}.`);
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setActionError(caught instanceof Error ? caught.message : "Unable to update the batch status.");
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  async function completeBatch(inputs: Record<number, CompleteConditionInput>) {
    const generation = routeGeneration.current;
    if (!activeSheet) {
      return;
    }
    setSubmitting(true);
    setCompleteError(null);
    try {
      const actualSubstrateCounts: Record<string, number> = {};
      const shortfallDeviations: CompletionShortfallDeviation[] = [];
      for (const condition of activeSheet.conditions) {
        const input = inputs[condition.id];
        if (
          !input ||
          typeof input.actualCount !== "number" ||
          !Number.isInteger(input.actualCount) ||
          input.actualCount < 0
        ) {
          throw new Error(`condition ${condition.condition_name} needs a valid actual substrate count`);
        }
        actualSubstrateCounts[String(condition.id)] = input.actualCount;
        if (input.actualCount < condition.planned_substrate_count) {
          const description = input.deviationDescription.trim();
          if (!description) {
            throw new Error(`condition ${condition.condition_name} needs a deviation reason for its shortfall`);
          }
          shortfallDeviations.push({ condition_id: condition.id, description });
        }
      }
      // One transaction on the server: shortfall deviations, actual counts,
      // materialized rows, and the status change commit together or not at
      // all, so a failed PATCH assumes nothing was saved.
      await apiFetch<void>(`/api/fabrication-batches/${id}/status`, {
        method: "PATCH",
        body: {
          status: "completed",
          actual_substrate_counts: actualSubstrateCounts,
          shortfall_deviations: shortfallDeviations,
        },
      });
      if (!isCurrentGeneration(generation)) {
        return;
      }
      setPendingCompletedCounts(false);
      await refetchSheet(`Batch status changed to completed.`);
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setCompleteError(
          caught instanceof Error ? caught.message : "Unable to complete the batch.",
        );
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  function requestCancelBatch() {
    if (!activeSheet) {
      return;
    }
    setActionError(null);
    setPendingConfirm({
      title: "Cancel batch",
      message: `Cancel batch ${activeSheet.batch.batch_code}? Cancellation is final and the run sheet cannot be reopened.`,
      run: async () => {
        await changeBatchStatus("cancelled");
      },
    });
  }

  function requestRecordAllAsPlanned() {
    if (!activeSheet || pendingRecordCount === 0) {
      return;
    }
    setActionError(null);
    setPendingConfirm({
      title: "Record all as planned",
      message: `Record all ${pendingRecordCount} unrecorded run-sheet items as matching the plan? Each item copies its planned parameters as the actual record; items you already adjusted are untouched.`,
      run: async () => {
        await recordAllAsPlanned();
      },
    });
  }

  async function recordAllAsPlanned() {
    const generation = routeGeneration.current;
    setSubmitting(true);
    setActionError(null);
    try {
      const counts = await apiFetch<{ preparations: number; executions: number }>(
        `/api/fabrication-batches/${id}/record-as-planned`,
        { method: "POST" },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet(
        `Recorded ${counts.preparations + counts.executions} run-sheet items as planned.`,
      );
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setActionError(
          caught instanceof Error ? caught.message : "Unable to record the run sheet as planned.",
        );
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  function requestMergePreparation(preparationId: number, sourceId: number) {
    if (!activeSheet) {
      return;
    }
    const target = activeSheet.preparations.find((item) => item.preparation.id === preparationId)?.preparation;
    const source = activeSheet.preparations.find((item) => item.preparation.id === sourceId)?.preparation;
    setActionError(null);
    setPendingConfirm({
      title: "Merge preparation",
      message: `Merge ${source?.preparation_code ?? `preparation ${sourceId}`} into ${target?.preparation_code ?? `preparation ${preparationId}`}? The source preparation will be merged and deleted.`,
      run: async () => {
        try {
          await mergePreparation(preparationId, sourceId);
        } catch (caught) {
          setActionError(caught instanceof Error ? caught.message : "Unable to merge the preparations.");
        }
      },
    });
  }

  function requestMergeExecution(executionId: number, sourceId: number) {
    if (!activeSheet) {
      return;
    }
    const target = activeSheet.executions.find((item) => item.execution.id === executionId)?.execution;
    const source = activeSheet.executions.find((item) => item.execution.id === sourceId)?.execution;
    setActionError(null);
    setPendingConfirm({
      title: "Merge execution",
      message: `Merge ${source?.execution_code ?? `execution ${sourceId}`} into ${target?.execution_code ?? `execution ${executionId}`}? The source execution will be merged and deleted.`,
      run: async () => {
        try {
          await mergeExecution(executionId, sourceId);
        } catch (caught) {
          setActionError(caught instanceof Error ? caught.message : "Unable to merge the executions.");
        }
      },
    });
  }

  async function splitPreparation(preparationId: number, memberIds: number[]) {
    const generation = routeGeneration.current;
    try {
      await apiFetch<SolutionPreparation>(
        `/api/fabrication-batches/${id}/solution-preparations/${preparationId}/split`,
        { method: "POST", body: { member_ids: memberIds, notes: "" } },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet("Split saved.");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to split the preparation.");
    }
  }

  async function mergePreparation(preparationId: number, sourceId: number) {
    const generation = routeGeneration.current;
    try {
      await apiFetch<SolutionPreparation>(
        `/api/fabrication-batches/${id}/solution-preparations/${preparationId}/merge`,
        { method: "POST", body: { source_id: sourceId } },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet("Preparations merged.");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to merge the preparations.");
    }
  }

  async function splitExecution(executionId: number, memberIds: number[]) {
    const generation = routeGeneration.current;
    try {
      await apiFetch<ProcessExecution>(
        `/api/fabrication-batches/${id}/process-executions/${executionId}/split`,
        { method: "POST", body: { member_ids: memberIds, notes: "" } },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet("Split saved.");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to split the execution.");
    }
  }

  async function mergeExecution(executionId: number, sourceId: number) {
    const generation = routeGeneration.current;
    try {
      await apiFetch<ProcessExecution>(
        `/api/fabrication-batches/${id}/process-executions/${executionId}/merge`,
        { method: "POST", body: { source_id: sourceId } },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      await refetchSheet("Executions merged.");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to merge the executions.");
    }
  }

  async function addDeviation(payload: Record<string, unknown>) {
    const generation = routeGeneration.current;
    try {
      const created = await apiFetch<Deviation>(
        `/api/fabrication-batches/${id}/deviations`,
        { method: "POST", body: payload },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      setLocalSheet((current) => {
        const base = current ?? resource.data;
        if (!base) {
          return current;
        }
        return { ...base, deviations: [...base.deviations, created] };
      });
      show("Deviation recorded.", "success");
    } catch (caught) {
      if (!isCurrentGeneration(generation)) {
        return;
      }
      throw new Error(caught instanceof Error ? caught.message : "Unable to record the deviation.");
    }
  }

  if (!Number.isInteger(experimentIdNumber) || experimentIdNumber <= 0 || !Number.isInteger(id) || id <= 0) {
    return <ErrorState title="Invalid batch" message="The fabrication batch identifier is not valid." />;
  }
  if (refreshFailed) {
    return (
      <ErrorState
        title="Unable to refresh run sheet"
        message={
          actionError ??
          "Unable to refresh the run sheet. The displayed data may be outdated; verify the current batch state before continuing."
        }
        action={
          <button
            type="button"
            className="button button--secondary"
            // Keep the blocking refresh-failed state until the retry succeeds;
            // the success effect clears it when the fresh run sheet renders.
            onClick={() => void resource.reload()}
          >
            Retry
          </button>
        }
      />
    );
  }
  if (activeSheet === null) {
    if (resource.status === "loading") {
      return <div className="page-loading" role="status">Loading run sheet…</div>;
    }
    if (resource.status === "error") {
      return (
        <ErrorState
          title="Unable to load run sheet"
          message={resource.error ?? "The run sheet could not be loaded."}
          action={
            <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>
              Retry
            </button>
          }
        />
      );
    }
    return null;
  }

  const batch = activeSheet.batch;
  const planExperimentId = batch.experiment_id;
  if (experimentIdNumber !== planExperimentId) {
    return (
      <ErrorState
        title="Batch not found"
        message="The batch does not belong to the requested experiment."
      />
    );
  }
  const nextAction = BATCH_NEXT_STATUS[batch.status];
  const terminal = batch.status === "completed" || batch.status === "cancelled";
  // Run-sheet recording progress: a row is recorded once its actual snapshot
  // mode is set; pending rows are the unrecorded non-terminal ones the bulk
  // "Record all as planned" action will fill in.
  const recordedPreparations = activeSheet.preparations.filter(
    (item) => item.preparation.actual_recording_mode !== null,
  ).length;
  const recordedExecutions = activeSheet.executions.filter(
    (item) => item.execution.actual_recording_mode !== null,
  ).length;
  const pendingRecordCount = activeSheet.preparations.filter(
    (item) =>
      item.preparation.actual_recording_mode === null &&
      !["consumed", "discarded"].includes(item.preparation.status),
  ).length +
    activeSheet.executions.filter(
      (item) =>
        item.execution.actual_recording_mode === null &&
        !["completed", "failed", "cancelled"].includes(item.execution.status),
    ).length;

  return (
    <div data-run-sheet="true">
      <PageHeader
        title={batch.batch_code}
        description={`Fabrication batch ${batch.batch_number} (frozen condition set ${batch.condition_set_hash.slice(0, 10)}…)`}
        meta={`Created ${formatDateTime(batch.created_at)} · Updated ${formatDateTime(batch.updated_at)}`}
        actions={
          <>
            <a className="button button--secondary" href={`/experiments/${planExperimentId}/batches/${id}/export.json`}>Export JSON</a>
            <a className="button button--secondary" href={`/experiments/${planExperimentId}/batches/${id}/export.pdf`}>Export PDF</a>
            <Link className="button button--secondary" to={`/experiments/${planExperimentId}`}>Back to plan</Link>
          </>
        }
      />

      <section className="panel" aria-labelledby="batch-status-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="batch-status-title">Batch status</h2>
          <StatusBadge status={batch.status} />
        </div>
        <p>{batch.notes || "No batch notes."}</p>
        <div className="status-row" data-recording-progress="true">
          <span>
            Recorded {recordedPreparations}/{activeSheet.preparations.length} preparations ·{" "}
            {recordedExecutions}/{activeSheet.executions.length} executions
          </span>
          {!terminal && pendingRecordCount > 0 ? (
            <button
              type="button"
              className="button button--secondary"
              data-record-all="true"
              disabled={submitting}
              onClick={requestRecordAllAsPlanned}
            >
              Record all as planned ({pendingRecordCount})
            </button>
          ) : null}
        </div>
        {!terminal ? (
          <div className="button-row">
            {nextAction ? (
              <button
                type="button"
                className="button button--primary"
                data-status-action={nextAction.status}
                disabled={submitting}
                onClick={() => {
                  if (nextAction.status === "completed") {
                    setCompleteError(null);
                    setPendingCompletedCounts(true);
                  } else {
                    void changeBatchStatus(nextAction.status);
                  }
                }}
              >
                {nextAction.label}
              </button>
            ) : null}
            {canCancel ? (
              <button
                type="button"
                className="button button--danger"
                data-status-action="cancelled"
                disabled={submitting}
                onClick={requestCancelBatch}
              >
                Cancel batch
              </button>
            ) : null}
          </div>
        ) : null}
        <InlineFormError message={actionError} />
      </section>

      <nav className="run-sheet-jump" aria-label="Run sheet sections">
        <span>Jump to</span>
        <a href="#preparation-directory-title">Preparations ({recordedPreparations}/{activeSheet.preparations.length})</a>
        <a href="#execution-directory-title">Executions ({recordedExecutions}/{activeSheet.executions.length})</a>
        <a href="#deviation-directory-title">Deviations ({activeSheet.deviations.length})</a>
        <a href="#frozen-conditions-title">Conditions</a>
        <a href="#substrate-directory-title">Substrates</a>
      </nav>

      <section className="panel" aria-labelledby="frozen-conditions-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="frozen-conditions-title">Frozen conditions</h2>
          <span className="record-count">{activeSheet.conditions.length} records</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Role</th>
                <th>Layout</th>
                <th>Substrates</th>
                <th>Devices</th>
                <th>Source hash</th>
              </tr>
            </thead>
            <tbody>
              {activeSheet.conditions.map((condition) => (
                <tr key={condition.id}>
                  <td><code>{condition.condition_code}</code></td>
                  <td>{condition.condition_name}</td>
                  <td><StatusBadge status={condition.role} /></td>
                  <td>{condition.device_layout_code}</td>
                  <td>{condition.planned_substrate_count}</td>
                  <td>{condition.expected_device_count}</td>
                  <td><code>{condition.source_condition_hash.slice(0, 16)}…</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="substrate-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="substrate-directory-title">Substrates &amp; devices</h2>
          <span className="record-count">{activeSheet.substrates.length} substrates</span>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Mark</th>
                <th>Substrate</th>
                <th>Status</th>
                <th>Devices</th>
              </tr>
            </thead>
            <tbody>
              {activeSheet.substrates.map((substrate) => {
                const devices = activeSheet.devices.filter((device) => device.substrate_id === substrate.id);
                return (
                  <tr key={substrate.id}>
                    <td><code>{substrate.substrate_mark}</code></td>
                    <td>{substrate.substrate_code}</td>
                    <td><StatusBadge status={substrate.status} /></td>
                    <td>{devices.map((device) => device.device_mark).join(", ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="preparation-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="preparation-directory-title">Solution preparations</h2>
          <span className="record-count">{activeSheet.preparations.length} records</span>
        </div>
        {activeSheet.preparations.length === 0 ? (
          <EmptyState title="No solution preparations." />
        ) : (
          activeSheet.preparations.map((item) => (
            <PreparationSection
              key={item.preparation.id}
              item={item}
              sheet={activeSheet}
              onSave={savePreparation}
              onSplit={splitPreparation}
              onRequestMerge={requestMergePreparation}
              disabled={submitting}
            />
          ))
        )}
      </section>

      <section className="panel" aria-labelledby="execution-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="execution-directory-title">Process executions</h2>
          <span className="record-count">{activeSheet.executions.length} records</span>
        </div>
        {activeSheet.executions.length === 0 ? (
          <EmptyState title="No process executions." />
        ) : (
          activeSheet.executions.map((item) => (
            <ExecutionSection
              key={item.execution.id}
              item={item}
              sheet={activeSheet}
              onSave={saveExecution}
              onSplit={splitExecution}
              onRequestMerge={requestMergeExecution}
              disabled={submitting}
            />
          ))
        )}
      </section>

      <section className="panel" aria-labelledby="deviation-directory-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="deviation-directory-title">Deviations</h2>
          <span className="record-count">{activeSheet.deviations.length} records</span>
        </div>
        {batch.status !== "cancelled" ? (
          <DeviationSection sheet={activeSheet} onSubmit={addDeviation} disabled={submitting} />
        ) : null}
        {activeSheet.deviations.length === 0 ? (
          <EmptyState title="No deviations recorded." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Category</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Description</th>
                  <th>Recorded</th>
                </tr>
              </thead>
              <tbody>
                {activeSheet.deviations.map((deviation) => (
                  <tr key={deviation.id} id={`deviation-${deviation.id}`}>
                    <td>{deviation.id}</td>
                    <td><StatusBadge status={deviation.category} /></td>
                    <td><StatusBadge status={deviation.deviation_type} /></td>
                    <td><StatusBadge status={deviation.severity} /></td>
                    <td>{deviation.description}</td>
                    <td>{formatDateTime(deviation.recorded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {pendingCompletedCounts && activeSheet ? (
        <CompleteBatchDialog
          open
          conditions={activeSheet.conditions}
          submitting={submitting}
          error={completeError}
          onCancel={() => setPendingCompletedCounts(false)}
          onConfirm={(inputs) => void completeBatch(inputs)}
        />
      ) : null}
      {pendingConfirm ? (
        <ConfirmDialog
          open
          title={pendingConfirm.title}
          message={pendingConfirm.message}
          confirmLabel="Confirm"
          destructive
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => {
            const action = pendingConfirm;
            setPendingConfirm(null);
            void action.run();
          }}
        />
      ) : null}
    </div>
  );
}
