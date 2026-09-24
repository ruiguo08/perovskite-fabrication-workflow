import { useState, type FormEvent } from "react";
import { useSession } from "../auth/session";
import { FormField } from "./FormField";
import { InlineFormError } from "./InlineFormError";
import { StatusBadge } from "./StatusBadge";
import { apiFetch } from "../lib/api";
import type { Condition, SubstrateException } from "../types/api";

interface ConditionCardProps {
  condition: Condition;
  exception: SubstrateException | null;
  planStatus: string | null;
  onExceptionChange: (exception: SubstrateException) => void;
}

export function ConditionCard({ condition, exception, planStatus, onExceptionChange }: ConditionCardProps) {
  const { user } = useSession();
  const canDecide = user?.role === "instructor" || user?.role === "administrator";
  const [reason, setReason] = useState("");
  const [decisionNote, setDecisionNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function requestException(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiFetch<SubstrateException>(`/api/conditions/${condition.id}/substrate-exceptions`, {
        method: "POST",
        body: { requested_count: condition.planned_substrate_count, reason: reason.trim() },
      });
      onExceptionChange(created);
      setReason("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request the substrate exception.");
    } finally {
      setSubmitting(false);
    }
  }

  async function decide(decision: "approved" | "rejected") {
    if (!exception) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<SubstrateException>(`/api/substrate-exceptions/${exception.id}/decision`, {
        method: "POST",
        body: { decision, decision_note: decisionNote.trim() },
      });
      onExceptionChange(updated);
      setDecisionNote("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the exception decision.");
    } finally {
      setSubmitting(false);
    }
  }

  const titleId = `condition-title-${condition.id}`;
  return (
    <article className="condition-card" aria-labelledby={titleId}>
      <header className="condition-card__header">
        <div>
          <div className="material-card__title-line">
            <h3 id={titleId}>{condition.condition_name}</h3>
            <StatusBadge status={condition.role} tone="planned" />
            {condition.requires_manual_review ? <StatusBadge status="manual review" tone="warning" /> : null}
          </div>
          <code>{condition.condition_code}</code>
        </div>
        <span className="version-mark">schema {condition.recipe_schema_version}</span>
      </header>
      <dl className="condition-facts">
        <div><dt>Layout</dt><dd>{condition.device_layout_code}</dd></div>
        <div><dt>Substrates</dt><dd>{condition.planned_substrate_count}</dd></div>
        <div><dt>Devices</dt><dd>{condition.expected_device_count} expected devices</dd></div>
        <div><dt>Source</dt><dd>{condition.source_baseline_version_id ? `Baseline version ${condition.source_baseline_version_id}` : "Standalone snapshot"}</dd></div>
      </dl>
      <code className="catalog-hash">{condition.canonical_hash}</code>

      <details className="snapshot-disclosure condition-advanced">
        <summary>Advanced: raw snapshots (JSON)</summary>
        <details className="snapshot-disclosure condition-snapshot">
          <summary>Complete condition snapshot</summary>
          <pre className="snapshot-json">{JSON.stringify(condition.recipe_snapshot, null, 2)}</pre>
        </details>
        <details className="snapshot-disclosure">
          <summary>Device layout snapshot</summary>
          <pre className="snapshot-json">{JSON.stringify(condition.device_layout_snapshot, null, 2)}</pre>
        </details>
      </details>

      {condition.planned_substrate_count < 3 ? (
        <section className="condition-exception" aria-label={`Substrate exception for ${condition.condition_name}`}>
          <h4>Substrate exception</h4>
          {exception ? (
            <div className="exception-record">
              <StatusBadge status={exception.decision} />
              <p>{exception.reason}</p>
              {exception.decision_note ? <p>Decision note: {exception.decision_note}</p> : null}
              {canDecide && exception.decision === "pending" ? (
                <div className="exception-decision">
                  <FormField label={`Decision note for ${condition.condition_name}`} htmlFor={`decision-note-${condition.id}`}>
                    <textarea id={`decision-note-${condition.id}`} className="text-input" maxLength={2000} value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} />
                  </FormField>
                  <div className="button-row">
                    <button className="button button--primary button--small" type="button" disabled={submitting} onClick={() => void decide("approved")}>Approve exception</button>
                    <button className="button button--danger button--small" type="button" disabled={submitting} onClick={() => void decide("rejected")}>Reject exception</button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : planStatus === "draft" ? (
            <form onSubmit={(event) => void requestException(event)}>
              <FormField label={`Exception reason for ${condition.condition_name}`} htmlFor={`exception-reason-${condition.id}`} required>
                <textarea id={`exception-reason-${condition.id}`} className="text-input" required maxLength={2000} value={reason} onChange={(event) => setReason(event.target.value)} />
              </FormField>
              <button className="button button--secondary button--small" type="submit" disabled={submitting}>Request exception</button>
            </form>
          ) : <p>No active exception is recorded.</p>}
          <InlineFormError message={error} />
        </section>
      ) : null}
    </article>
  );
}
