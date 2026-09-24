import { useState, type FormEvent } from "react";
import { InlineFormError } from "../../components/InlineFormError";
import { SnapshotEditor } from "../../components/SnapshotEditor";
import { StatusBadge } from "../../components/StatusBadge";
import type { BatchRunSheet, SolutionPreparation } from "../../types/api";
import { preparationStatusOptions, snapshotCopy } from "./helpers";
import { RecordingControl } from "./RecordingControl";

/** Human-readable label for a preparation: the solid ingredients of its
 * planned solution (e.g. "PEAI / NiOx"). Falls back to the preparation code
 * when the snapshot has no solid ingredients (e.g. a pure-solvent or
 * dispersion formulation). */
function preparationMaterialLabel(preparation: SolutionPreparation): string {
  const solids = preparation.planned_solution_snapshot?.solids;
  if (Array.isArray(solids)) {
    const names = solids
      .map((solid) => (solid && typeof solid === "object" && typeof (solid as { chemical?: unknown }).chemical === "string" ? (solid as { chemical: string }).chemical : null))
      .filter((name): name is string => Boolean(name));
    if (names.length > 0) {
      return names.join(" / ");
    }
  }
  return preparation.preparation_code;
}

interface PreparationSectionProps {
  item: { preparation: SolutionPreparation; uses: { id: number; batch_condition_id: number; layer_ordinal: number }[] };
  sheet: BatchRunSheet;
  onSave: (preparation: SolutionPreparation, payload: Record<string, unknown>) => Promise<void>;
  onSplit: (preparationId: number, memberIds: number[]) => Promise<void>;
  onRequestMerge: (preparationId: number, sourceId: number) => void;
  disabled: boolean;
}

export function PreparationSection({ item, sheet, onSave, onSplit, onRequestMerge, disabled }: PreparationSectionProps) {
  const { preparation, uses } = item;
  const editable = !["completed", "cancelled"].includes(sheet.batch.status) &&
    !["consumed", "discarded"].includes(preparation.status);
  const [status, setStatus] = useState("");
  const [recording, setRecording] = useState(preparation.actual_recording_mode ?? "");
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>(
    snapshotCopy(preparation.actual_solution_snapshot ?? preparation.planned_solution_snapshot),
  );
  const [notes, setNotes] = useState(preparation.notes);
  const [splitMembers, setSplitMembers] = useState<number[]>([]);
  const [mergeSource, setMergeSource] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [splitOpen, setSplitOpen] = useState(false);

  const mergeCandidates = item.uses.length > 0 && preparation.status === "planned"
    ? sheet.preparations.filter(
        (other) =>
          other.preparation.id !== preparation.id &&
          other.preparation.status === "planned" &&
          other.preparation.planned_canonical_hash === preparation.planned_canonical_hash &&
          other.preparation.planned_snapshot_schema_version === preparation.planned_snapshot_schema_version,
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
      payload.actual_solution_snapshot = snapshot;
    }
    payload.notes = notes.trim();
    setSubmitting(true);
    setError(null);
    try {
      await onSave(preparation, payload);
      setStatus("");
      setRecording("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save the preparation.");
    } finally {
      setSubmitting(false);
    }
  }

  async function split() {
    setSubmitting(true);
    setError(null);
    try {
      await onSplit(preparation.id, splitMembers);
      setSplitMembers([]);
      setSplitOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to split the preparation.");
    } finally {
      setSubmitting(false);
    }
  }

  function requestMerge() {
    if (mergeSource === "") {
      return;
    }
    onRequestMerge(preparation.id, Number(mergeSource));
    setMergeSource("");
  }

  return (
    <article className="run-sheet-card" data-preparation={preparation.id} aria-label={`Solution preparation ${preparation.preparation_code}`}>
      <div className="run-sheet-card__heading">
        <strong>{preparation.preparation_code}</strong>
        <StatusBadge status={preparation.status} />
      </div>
      <div className="run-sheet-card__material">{preparationMaterialLabel(preparation)}</div>
      <code>{preparation.planned_canonical_hash.slice(0, 16)}…</code>
      {preparation.actual_recording_mode ? (
        <StatusBadge status="Recorded" tone="success" />
      ) : (
        <StatusBadge status="Not yet" tone="neutral" />
      )}
      {editable ? (
        <form className="run-sheet-form" onSubmit={(event) => void save(event)}>
          <label className="form-field">
            <span className="form-field__label">Status</span>
            <select className="text-input" data-prep-status="true" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Keep current</option>
              {preparationStatusOptions(preparation.status).map((option) => (
                <option key={option} value={option}>{option.replace(/_/g, " ")}</option>
              ))}
            </select>
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
            <input className="text-input" data-prep-notes="true" maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <button className="button button--primary" type="submit" data-save-preparation={preparation.id} disabled={submitting || disabled}>
            Save preparation
          </button>
        </form>
      ) : null}

      {editable && uses.length > 1 && sheet.batch.status === "draft" ? (
        <section className="run-sheet-split">
          <button
            type="button"
            className="button button--secondary button--small"
            aria-expanded={splitOpen}
            onClick={() => setSplitOpen(!splitOpen)}
          >
            Split preparation {splitOpen ? "▲" : "▼"}
          </button>
          {splitOpen ? (
            <div className="run-sheet-split__body">
              {uses.map((use) => (
                <label className="run-sheet-split__member" key={use.id}>
                  <input
                    type="checkbox"
                    data-split-member={use.id}
                    checked={splitMembers.includes(use.id)}
                    onChange={(event) =>
                      setSplitMembers((current) =>
                        event.target.checked
                          ? [...current, use.id]
                          : current.filter((member) => member !== use.id),
                      )
                    }
                  />
                  condition {use.batch_condition_id}, layer {use.layer_ordinal}
                </label>
              ))}
              <button
                type="button"
                className="button button--secondary button--small"
                data-split-submit={preparation.id}
                disabled={splitMembers.length === 0 || splitMembers.length >= uses.length || submitting}
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
            <span className="form-field__label">Merge into this preparation</span>
            <select className="text-input" data-merge-source={preparation.id} value={mergeSource} onChange={(event) => setMergeSource(event.target.value === "" ? "" : Number(event.target.value))}>
              <option value="">Select a source preparation</option>
              {mergeCandidates.map((other) => (
                <option key={other.preparation.id} value={other.preparation.id}>
                  {other.preparation.preparation_code}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="button button--secondary button--small"
            data-merge-submit={preparation.id}
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
