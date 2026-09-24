import { useState, type FormEvent } from "react";
import { InlineFormError } from "../../components/InlineFormError";
import { SnapshotEditor } from "../../components/SnapshotEditor";
import { StatusBadge } from "../../components/StatusBadge";
import type { BatchRunSheet, ProcessExecution } from "../../types/api";
import { executionStatusOptions, snapshotCopy } from "./helpers";
import { RecordingControl } from "./RecordingControl";

interface ExecutionSectionProps {
  item: { execution: ProcessExecution; members: { id: number; substrate_id: number; layer_ordinal: number }[] };
  sheet: BatchRunSheet;
  onSave: (execution: ProcessExecution, payload: Record<string, unknown>) => Promise<void>;
  onSplit: (executionId: number, memberIds: number[]) => Promise<void>;
  onRequestMerge: (executionId: number, sourceId: number) => void;
  disabled: boolean;
}

export function ExecutionSection({ item, sheet, onSave, onSplit, onRequestMerge, disabled }: ExecutionSectionProps) {
  const { execution, members } = item;
  const editable = !["completed", "cancelled"].includes(sheet.batch.status) &&
    !["completed", "failed", "cancelled"].includes(execution.status);
  const [status, setStatus] = useState("");
  const [recording, setRecording] = useState(execution.actual_recording_mode ?? "");
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>(
    snapshotCopy(execution.actual_process_snapshot ?? execution.planned_process_snapshot),
  );
  const [equipment, setEquipment] = useState(execution.equipment_identifier ?? "");
  const [notes, setNotes] = useState(execution.notes);
  const [splitMembers, setSplitMembers] = useState<number[]>([]);
  const [mergeSource, setMergeSource] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [splitOpen, setSplitOpen] = useState(false);

  const mergeCandidates = execution.status === "planned"
    ? sheet.executions.filter(
        (other) =>
          other.execution.id !== execution.id &&
          other.execution.status === "planned" &&
          other.execution.planned_canonical_hash === execution.planned_canonical_hash &&
          other.execution.planned_snapshot_schema_version === execution.planned_snapshot_schema_version &&
          other.execution.method === execution.method &&
          other.execution.layer_role === execution.layer_role &&
          other.execution.layer_type === execution.layer_type &&
          other.execution.layer_name === execution.layer_name,
      )
    : [];

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: Record<string, unknown> = {};
    if (status) {
      payload.status = status;
    }
    if (recording === "copied_from_plan") {
      payload.actual_matches_planned = true;
    } else if (recording === "entered") {
      payload.actual_process_snapshot = snapshot;
    }
    payload.equipment_identifier = equipment.trim();
    payload.notes = notes.trim();
    setSubmitting(true);
    setError(null);
    try {
      await onSave(execution, payload);
      setStatus("");
      setRecording("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save the execution.");
    } finally {
      setSubmitting(false);
    }
  }

  async function split() {
    setSubmitting(true);
    setError(null);
    try {
      await onSplit(execution.id, splitMembers);
      setSplitMembers([]);
      setSplitOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to split the execution.");
    } finally {
      setSubmitting(false);
    }
  }

  function requestMerge() {
    if (mergeSource === "") {
      return;
    }
    onRequestMerge(execution.id, Number(mergeSource));
    setMergeSource("");
  }

  return (
    <article className="run-sheet-card" data-execution={execution.id} aria-label={`Process execution ${execution.execution_code}`}>
      <div className="run-sheet-card__heading">
        <strong>{execution.execution_code}</strong>
        <StatusBadge status={execution.status} />
        <span className="run-sheet-muted">{execution.method.replace(/_/g, " ")} · {execution.layer_name}</span>
      </div>
      {execution.actual_recording_mode ? (
        <StatusBadge status="Recorded" tone="success" />
      ) : (
        <StatusBadge status="Not yet" tone="neutral" />
      )}
      {editable ? (
        <form className="run-sheet-form" onSubmit={(event) => void save(event)}>
          <label className="form-field">
            <span className="form-field__label">Status</span>
            <select className="text-input" data-exec-status="true" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Keep current</option>
              {executionStatusOptions(execution.status).map((option) => (
                <option key={option} value={option}>{option.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-field__label">Equipment identifier</span>
            <input className="text-input" data-exec-equipment="true" maxLength={120} value={equipment} onChange={(event) => setEquipment(event.target.value)} />
          </label>
          <RecordingControl
            value={recording}
            onChange={setRecording}
            editor={
              <SnapshotEditor
                snapshot={snapshot}
                editorConfig={sheet.editor_config}
                onChange={setSnapshot}
              />
            }
          />
          <label className="form-field">
            <span className="form-field__label">Notes</span>
            <input className="text-input" data-exec-notes="true" maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <button className="button button--primary" type="submit" data-save-execution={execution.id} disabled={submitting || disabled}>
            Save execution
          </button>
        </form>
      ) : null}

      {editable && members.length > 1 && sheet.batch.status === "draft" ? (
        <section className="run-sheet-split">
          <button
            type="button"
            className="button button--secondary button--small"
            aria-expanded={splitOpen}
            onClick={() => setSplitOpen(!splitOpen)}
          >
            Split execution {splitOpen ? "▲" : "▼"}
          </button>
          {splitOpen ? (
            <div className="run-sheet-split__body">
              {members.map((member) => (
                <label className="run-sheet-split__member" key={member.id}>
                  <input
                    type="checkbox"
                    data-split-member={member.id}
                    checked={splitMembers.includes(member.id)}
                    onChange={(event) =>
                      setSplitMembers((current) =>
                        event.target.checked
                          ? [...current, member.id]
                          : current.filter((selected) => selected !== member.id),
                      )
                    }
                  />
                  substrate {member.substrate_id}, layer {member.layer_ordinal}
                </label>
              ))}
              <button
                type="button"
                className="button button--secondary button--small"
                data-split-submit={execution.id}
                disabled={splitMembers.length === 0 || splitMembers.length >= members.length || submitting}
                onClick={() => void split()}
              >
                Split
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {sheet.batch.status === "draft" && mergeCandidates.length > 0 ? (
        <section className="run-sheet-merge">
          <label className="form-field">
            <span className="form-field__label">Merge into this execution</span>
            <select className="text-input" data-merge-source={execution.id} value={mergeSource} onChange={(event) => setMergeSource(event.target.value === "" ? "" : Number(event.target.value))}>
              <option value="">Select a source execution</option>
              {mergeCandidates.map((other) => (
                <option key={other.execution.id} value={other.execution.id}>
                  {other.execution.execution_code}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="button button--secondary button--small"
            data-merge-submit={execution.id}
            disabled={mergeSource === "" || submitting}
            onClick={requestMerge}
          >
            Merge
          </button>
        </section>
      ) : null}
      <InlineFormError message={error} />
    </article>
  );
}
