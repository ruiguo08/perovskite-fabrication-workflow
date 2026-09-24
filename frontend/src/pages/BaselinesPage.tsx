import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { useSession } from "../auth/session";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { FormField } from "../components/FormField";
import { InlineFormError } from "../components/InlineFormError";
import { PageHeader } from "../components/PageHeader";
import { RecipeSnapshotSummary } from "../components/RecipeSnapshotSummary";
import { StatusBadge } from "../components/StatusBadge";
import { useToast } from "../components/Toast";
import { VersionHistory } from "../components/VersionHistory";
import { BaselineAuthoring, type BaselineAuthoringValues } from "../features/baseline-builder/BaselineAuthoring";
import { apiFetch } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { useApiResource } from "../lib/useApiResource";
import type { Baseline, BaselineVersion } from "../types/api";

function sortBaselines(rows: Baseline[]): Baseline[] {
  return [...rows].sort((left, right) => left.name.localeCompare(right.name));
}

function BaselineReviseEditor({
  baseline,
  onRevised,
  onError,
}: {
  baseline: Baseline;
  onRevised: (baseline: Baseline) => void;
  onError: (message: string | null) => void;
}) {
  const { show } = useToast();
  // Revising an active baseline always carries a complete deposition process
  // (canRevise gates on active status, which the backend requires to be complete).
  const initialValues: BaselineAuthoringValues | null = baseline.deposition_process
    ? {
        name: baseline.name,
        device_recipe: baseline.device_recipe,
        deposition_process: baseline.deposition_process,
      }
    : null;
  if (initialValues === null) {
    return <p className="run-sheet-muted">This baseline has no complete deposition process and cannot be revised.</p>;
  }
  return (
    <BaselineAuthoring
      scope={baseline.scope === "shared" ? "shared" : "personal"}
      initialValues={initialValues}
      onSubmit={async (values) => {
        try {
          const updated = await apiFetch<Baseline>(`/api/baselines/${baseline.id}`, {
            method: "PUT",
            body: {
              name: values.name.trim(),
              device_recipe: values.device_recipe,
              deposition_process: values.deposition_process,
            },
          });
          onRevised(updated);
          onError(null);
          show("A new immutable baseline revision was saved.", "success");
        } catch (caught) {
          onError(caught instanceof Error ? caught.message : "Unable to revise the baseline.");
        }
      }}
    />
  );
}

export function BaselinesPage() {
  const { user } = useSession();
  const { show } = useToast();
  const isManager = user?.role === "instructor" || user?.role === "administrator";
  const isAdministrator = user?.role === "administrator";
  const fixedScope: "personal" | "shared" = isManager ? "shared" : "personal";

  const loadBaselines = useCallback(() => apiFetch<Baseline[]>("/api/baselines"), []);
  const resource = useApiResource(loadBaselines);
  const [baselines, setBaselines] = useState<Baseline[] | null>(null);
  const rows = useMemo(() => sortBaselines(baselines ?? resource.data ?? []), [baselines, resource.data]);
  const sharedRows = rows.filter((baseline) => baseline.scope === "shared");
  const personalRows = rows.filter((baseline) => baseline.scope === "personal");

  // Discard the optimistic overlay once fresh server data arrives so a later
  // reload (manual refresh, retry after an error) is never shadowed by a stale
  // local mutation. resource.data only changes identity on a successful fetch,
  // so this fires per reload rather than per render.
  useEffect(() => {
    setBaselines(null);
  }, [resource.data]);

  function replaceBaseline(replacement: Baseline) {
    setBaselines((current) => sortBaselines((current ?? rows).some((row) => row.id === replacement.id)
      ? (current ?? rows).map((row) => row.id === replacement.id ? replacement : row)
      : [...(current ?? rows), replacement]));
  }

  async function createBaseline(values: BaselineAuthoringValues) {
    const created = await apiFetch<Baseline>("/api/baselines", {
      method: "POST",
      body: {
        name: values.name,
        device_recipe: values.device_recipe,
        deposition_process: values.deposition_process,
      },
    });
    replaceBaseline(created);
    show(`Baseline saved as ${created.scope === "shared" ? "Shared" : "Personal"} with a complete versioned snapshot.`, "success");
  }

  if (resource.status === "loading" && resource.data === null) {
    return <div className="page-loading" role="status">Loading baselines…</div>;
  }
  if (resource.status === "error" && resource.data === null) {
    return <ErrorState message={resource.error ?? "Unable to load baselines."} action={
      <button type="button" className="button button--secondary" onClick={() => void resource.reload()}>Retry</button>
    } />;
  }

  return (
    <>
      <PageHeader
        title="Baselines"
        description="Complete Control reference recipes used as experiment starting points. Personal baselines belong to their owner; Shared baselines are lab-wide."
      />
      <section className="panel panel--accent" aria-labelledby="create-baseline-title">
        <h2 className="panel__title" id="create-baseline-title">Create baseline</h2>
        <p className="builder-help">
          Assemble a new baseline from reusable materials, device layouts, and layer presets.
          {isManager
            ? " Instructor and administrator creation is Shared (a lab-wide starting point)."
            : " Student creation is Personal and visible only to you until an instructor promotes it to Shared."}
        </p>
        <BaselineAuthoring scope={fixedScope} onSubmit={createBaseline} />
      </section>

      <BaselineGroup
        title="Shared baselines"
        rows={sharedRows}
        user={user}
        isManager={isManager}
        isAdministrator={isAdministrator}
        onChange={replaceBaseline}
      />
      <BaselineGroup
        title="Personal baselines"
        rows={personalRows}
        user={user}
        isManager={isManager}
        isAdministrator={isAdministrator}
        onChange={replaceBaseline}
      />
    </>
  );
}

function BaselineGroup({
  title,
  rows,
  user,
  isManager,
  isAdministrator,
  onChange,
}: {
  title: string;
  rows: Baseline[];
  user: { id: number; role: string } | null;
  isManager: boolean;
  isAdministrator: boolean;
  onChange: (baseline: Baseline) => void;
}) {
  const groupId = `baseline-group-${title.replaceAll(" ", "-").toLowerCase()}`;
  return (
    <section className="catalog-group" aria-labelledby={groupId}>
      <div className="catalog-group__heading">
        <h2 id={groupId}>{title}</h2>
        <span className="record-count">{rows.length} records</span>
      </div>
      <div className="baseline-list">
        {rows.length === 0 ? <EmptyState title={`No ${title.toLowerCase()} are available.`} /> : rows.map((baseline) => (
          <BaselineCard
            key={baseline.id}
            baseline={baseline}
            user={user}
            isManager={isManager}
            isAdministrator={isAdministrator}
            onChange={onChange}
          />
        ))}
      </div>
    </section>
  );
}

function BaselineCard({
  baseline,
  user,
  isManager,
  isAdministrator,
  onChange,
}: {
  baseline: Baseline;
  user: { id: number; role: string } | null;
  isManager: boolean;
  isAdministrator: boolean;
  onChange: (baseline: Baseline) => void;
}) {
  const { show } = useToast();
  const canRevise = baseline.scope === "personal"
    ? baseline.owner_user_id === user?.id
    : isAdministrator;
  const canPromote = baseline.scope === "personal" && isManager;
  const [promoteNote, setPromoteNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function promote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const updated = await apiFetch<Baseline>(`/api/baselines/${baseline.id}/promote`, {
        method: "POST",
        body: { note: promoteNote.trim() || null },
      });
      onChange(updated);
      setPromoteNote("");
      show("Baseline promoted to Shared. The original owner remains recorded as provenance.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to promote the baseline.");
    } finally {
      setSubmitting(false);
    }
  }

  async function archive() {
    setConfirming(false);
    setError(null);
    try {
      await apiFetch<void>(`/api/baselines/${baseline.id}`, { method: "DELETE" });
      onChange({ ...baseline, status: "archived" });
      show("Baseline archived. Existing snapshots remain unchanged.", "success");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to archive the baseline.");
    }
  }

  const owner = baseline.owner_user_id === user?.id
    ? "You"
    : baseline.owner_display_name ?? `user ${baseline.owner_user_id ?? "—"}`;
  const titleId = `baseline-title-${baseline.id}`;
  return (
    <article className="baseline-card" aria-labelledby={titleId}>
      <header className="preset-card__header">
        <div className="material-card__title-line">
          <h3 id={titleId}>{baseline.name}</h3>
          <StatusBadge status={baseline.status} />
          <span className="scope-chip">{baseline.scope}</span>
        </div>
        <span className="version-mark">r{baseline.current_revision_number ?? "—"} · {formatDateTime(baseline.updated_at)}</span>
      </header>
      <p className="catalog-provenance">
        {baseline.scope === "personal"
          ? `Owned by ${owner}`
          : baseline.owner_user_id
            ? `Shared · originating owner ${owner}`
            : "Shared · created directly by staff"}
        {baseline.promoted_at && baseline.promoted_by_display_name
          ? ` · Promoted by ${baseline.promoted_by_display_name} on ${formatDateTime(baseline.promoted_at)}${baseline.promotion_note ? ` · ${baseline.promotion_note}` : ""}`
          : null}
      </p>
      <RecipeSnapshotSummary deviceRecipe={baseline.device_recipe} depositionProcess={baseline.deposition_process} />
      {baseline.canonical_hash ? <code className="catalog-hash">{baseline.canonical_hash}</code> : null}

      {canPromote && baseline.status === "active" ? (
        <details className="inline-editor">
          <summary>Promote to shared</summary>
          <form className="inline-editor__body" onSubmit={(event) => void promote(event)}>
            <FormField label={`Promotion note for ${baseline.name} (optional)`} htmlFor={`promote-note-${baseline.id}`}>
              <input id={`promote-note-${baseline.id}`} className="text-input" value={promoteNote} onChange={(event) => setPromoteNote(event.target.value)} />
            </FormField>
            <InlineFormError message={error} />
            <button className="button button--secondary" type="submit" disabled={submitting}>Promote {baseline.name} to shared</button>
          </form>
        </details>
      ) : null}

      {canRevise && baseline.status === "active" ? (
        <details className="inline-editor">
          <summary>Revise baseline</summary>
          <div className="inline-editor__body">
            <BaselineReviseEditor
              key={baseline.id}
              baseline={baseline}
              onRevised={onChange}
              onError={setError}
            />
          </div>
        </details>
      ) : null}

      <VersionHistory<BaselineVersion>
        endpoint={`/api/baselines/${baseline.id}/versions`}
        renderSnapshot={(version) => <pre className="snapshot-json">{JSON.stringify({ device_recipe: version.device_recipe, deposition_process: version.deposition_process }, null, 2)}</pre>}
      />
      <InlineFormError message={error} />
      {isAdministrator && baseline.status === "active" ? (
        <button className="button button--danger button--small catalog-danger-action" type="button" onClick={() => setConfirming(true)}>Archive {baseline.name}</button>
      ) : null}
      <ConfirmDialog
        open={confirming}
        title="Archive baseline"
        message="Existing experiments and versions retain their complete snapshots. This baseline will no longer be available to students for new plans."
        confirmLabel="Archive baseline"
        destructive
        onConfirm={() => void archive()}
        onCancel={() => setConfirming(false)}
      />
    </article>
  );
}