import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { DeviceExclusionsPanel } from "../components/DeviceExclusionsPanel";
import { ErrorState } from "../components/ErrorState";
import { InlineFormError } from "../components/InlineFormError";
import { JvChart } from "../components/JvChart";
import { PublicationFigure, type FigureColorScale } from "../components/PublicationFigure";
import { PageHeader } from "../components/PageHeader";
import { useToast } from "../components/Toast";
import { apiFetch } from "../lib/api";
import { formatDateTime, formatNumber, scaleMetric } from "../lib/format";
import { bestTrace, pooledMetric } from "../lib/deviceMetrics";
import { directionalGroupStatistics } from "../lib/resultStatistics";
import { DeviceScanHistoryPanel } from "../components/DeviceScanHistoryPanel";
import { useApiResource } from "../lib/useApiResource";
import type {
  AnalysisDevice,
  AnalysisStatistics,
  ParsedAnalysis,
  ResultDetail,
  ResultAssignment,
  ResultAssignmentGroup,
} from "../types/api";

const METRIC_META: { name: "voc" | "jsc" | "ff" | "pce"; label: string }[] = [
  { name: "voc", label: "Voc (V)" },
  { name: "jsc", label: "Jsc (mA cm⁻²)" },
  { name: "ff", label: "FF (%)" },
  { name: "pce", label: "PCE (%)" },
];

type ResultSection = "figures" | "statistics" | "assignments" | "records";
type FigureSection = "jv" | "uniformity" | "distributions";
const CATEGORICAL_PALETTES = [
  ["nature-classic", "Nature Classic"], ["science-tol", "Science / Paul Tol"],
  ["lancet-clinical", "Lancet Clinical"], ["nejm", "NEJM Palette"],
] as const;
const GRADIENT_PALETTES = [
  ["rdylgn", "RdYlGn"], ["nature-warm", "Nature warm"],
  ["science-purple", "Science deep purple"], ["lancet-blue", "Lancet deep blue"],
  ["nejm-red", "NEJM medical red"], ["cell-blue", "Cell blue-dominant"],
  ["wong-orange", "Wong bright orange"], ["viridis", "Viridis"],
  ["red-blue", "Diverging red-blue"], ["medical-gray", "Medical grayscale"],
  ["rainbow", "Rainbow red-to-blue"],
] as const;

function FigureScopePair({ resultId, kind, metric, direction, excludedDeviceIds, revision, alt, palette, scale }: {
  resultId: number;
  kind: "uniformity" | "boxplot";
  metric: "voc" | "jsc" | "ff" | "pce";
  direction?: "forward" | "reverse";
  excludedDeviceIds: string[];
  revision: number;
  alt: string;
  palette: string;
  scale?: FigureColorScale;
}) {
  return <div className="figure-scope-pair">
    {([
      { label: "All devices", excludedIds: [] },
      { label: `Exclude flagged devices (${excludedDeviceIds.length})`, excludedIds: excludedDeviceIds },
    ]).map(({ label, excludedIds }) =>
      <div key={label} className="figure-scope-pair__item" role="group" aria-label={label}>
        <h3>{label}</h3>
        <PublicationFigure resultId={resultId} kind={kind} metric={metric} direction={direction}
          excludedDeviceIds={excludedIds} revision={revision} palette={palette} scale={scale} alt={`${alt} · ${label}`} />
      </div>)}
  </div>;
}

function isStatistics(value: unknown): value is AnalysisStatistics {
  return typeof value === "object" && value !== null && "groups" in value && Array.isArray((value as { groups: unknown[] }).groups);
}

function isParsedAnalysis(value: unknown): value is ParsedAnalysis {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  const devices = candidate.devices;
  const substrates = candidate.substrates;
  if (!Array.isArray(devices) || !Array.isArray(substrates)) return false;
  // Every device must carry the nested fields the rendering layer accesses
  // (substrate_id, device_id, traces array); every trace in the array must
  // be an object with trace_id; every substrate must carry substrate_id,
  // device_ids, and instrument_labels.
  for (const device of devices) {
    if (
      typeof device !== "object" ||
      device === null ||
      typeof (device as Record<string, unknown>).substrate_id !== "string" ||
      typeof (device as Record<string, unknown>).device_id !== "string" ||
      !Array.isArray((device as Record<string, unknown>).traces)
    ) {
      return false;
    }
    for (const trace of (device as Record<string, unknown>).traces as unknown[]) {
      if (
        typeof trace !== "object" ||
        trace === null ||
        typeof (trace as Record<string, unknown>).trace_id !== "string"
      ) {
        return false;
      }
    }
  }
  for (const substrate of substrates) {
    if (
      typeof substrate !== "object" ||
      substrate === null ||
      typeof (substrate as Record<string, unknown>).substrate_id !== "string" ||
      !Array.isArray((substrate as Record<string, unknown>).device_ids) ||
      !Array.isArray((substrate as Record<string, unknown>).instrument_labels)
    ) {
      return false;
    }
  }
  return true;
}

interface SubstrateRow {
  substrate_id: string;
  device_ids: string[];
  instrument_labels: string[];
  group_id: string;
  batch_condition_id?: number;
}

function substrateList(analysis: ParsedAnalysis | null | undefined): SubstrateRow[] {
  if (!analysis) {
    return [];
  }
  return (analysis.substrates ?? []) as SubstrateRow[];
}

interface AssignmentFormProps {
  substrates: SubstrateRow[];
  assignments: Map<string, number>;
  groups: ResultAssignmentGroup[];
  inconsistent: Set<string>;
  submitting: boolean;
  error: string | null;
  allAssigned: boolean;
  statisticsPresent: boolean;
  onAssign: (substrateId: string, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

function AssignmentForm({
  substrates,
  assignments,
  groups,
  inconsistent,
  submitting,
  error,
  allAssigned,
  statisticsPresent,
  onAssign,
  onSubmit,
}: AssignmentFormProps) {
  return (
    <form id="result-assignment-form" className="assignment-form" onSubmit={onSubmit}>
      {substrates.map((substrate) => (
        <div className="assignment-row" key={substrate.substrate_id}>
          <label className="form-field">
            <span className="form-field__label">{substrate.substrate_id}</span>
            <select
              className="text-input"
              aria-label={`Assign ${substrate.substrate_id} to`}
              value={assignments.get(substrate.substrate_id) ?? ""}
              onChange={(event) => onAssign(substrate.substrate_id, event.target.value)}
            >
              <option value="">Choose a condition…</option>
              {groups.map((group) => (
                <option key={group.batch_condition_id} value={group.batch_condition_id}>
                  {group.name} ({group.kind})
                </option>
              ))}
            </select>
          </label>
          {inconsistent.has(substrate.substrate_id) ? (
            <p className="inline-form-error" role="alert">
              Inconsistent condition assignment: the device rows for this substrate disagree. Review the saved assignments.
            </p>
          ) : null}
        </div>
      ))}
      <button className="button button--primary assignment-form__save" type="submit" disabled={!allAssigned || submitting}>
        {submitting ? "Saving…" : statisticsPresent ? "Save assignments and update analysis" : "Save assignments"}
      </button>
      <InlineFormError message={error} />
    </form>
  );
}

interface DeviceInspectionTableProps {
  devices: AnalysisDevice[];
  groups: ResultAssignmentGroup[];
}

function DeviceInspectionTable({ devices, groups }: DeviceInspectionTableProps) {
  const groupNames = useMemo(
    () => new Map(groups.map((group) => [group.group_id, group.name])),
    [groups],
  );
  return (
    <section className="panel" aria-labelledby="device-inspection-title" data-device-inspection="true">
      <div className="panel__heading">
        <h2 className="panel__title" id="device-inspection-title">Parsed devices</h2>
        <span className="record-count">{devices.length} devices</span>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Device</th>
              <th>Substrate</th>
              <th>Group</th>
              <th>Traces</th>
              <th>Voc</th>
              <th>Jsc</th>
              <th>FF</th>
              <th>PCE</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => {
              const validCount = device.traces.filter((trace) => trace.valid).length;
              return (
                <tr key={device.device_id}>
                  <td>{device.device_id}</td>
                  <td>{device.substrate_id}</td>
                  <td>{groupNames.get(device.group_id) || "Unassigned"}</td>
                  <td>
                    {device.traces.map((trace) => (
                      <span key={trace.trace_id} className={`status-badge ${trace.valid ? "status-badge--success" : "status-badge--danger"}`}>
                        {trace.direction} {trace.valid ? "valid" : "invalid"}
                      </span>
                    ))}
                    {validCount === 0 ? <span className="status-badge status-badge--danger">No valid trace</span> : null}
                  </td>
                  <td>{formatNumber(pooledMetric(device.metrics, "voc"), 3)}</td>
                  <td>{formatNumber(pooledMetric(device.metrics, "jsc"), 2)}</td>
                  <td>{formatNumber(scaleMetric("ff", pooledMetric(device.metrics, "ff")), 2)}</td>
                  <td>{formatNumber(pooledMetric(device.metrics, "pce"), 2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

interface ProvenanceTableProps {
  rows: ResultAssignment[];
}

function ProvenanceTable({ rows }: ProvenanceTableProps) {
  if (rows.length === 0) {
    return <p className="run-sheet-muted">No saved assignment provenance rows.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Analysis device</th>
            <th>Analysis substrate</th>
            <th>Instrument label</th>
            <th>Fabrication device</th>
            <th>Substrate</th>
            <th>Condition</th>
            <th>Batch condition</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.analysis_device_id}</td>
              <td>{row.analysis_substrate_id}</td>
              <td>{row.instrument_label}</td>
              <td>{row.device_code ?? row.device_mark ?? "—"}</td>
              <td>{row.substrate_code ?? row.substrate_mark ?? "—"}</td>
              <td>{row.condition_code} ({row.condition_name})</td>
              <td>{row.batch_condition_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ResultDetailPage() {
  const { resultId } = useParams();
  const resultIdNumber = Number(resultId);
  const { show } = useToast();
  const loadDetail = useCallback(
    () => apiFetch<ResultDetail>(`/api/results/${resultIdNumber}`),
    [resultIdNumber],
  );
  const resource = useApiResource(loadDetail, { resetOnLoaderChange: true });
  const serverDetail = resource.data;
  const [localDetail, setLocalDetail] = useState<ResultDetail | null>(null);
  const [assignments, setAssignments] = useState<Map<string, number>>(new Map());
  const [figureRevision, setFigureRevision] = useState(0);
  const [inconsistent, setInconsistent] = useState<Set<string>>(new Set());
  const [exclusions, setExclusions] = useState<Map<string, string>>(new Map());
  const [uniformityMetric, setUniformityMetric] = useState<"voc" | "jsc" | "ff" | "pce">("pce");
  const [distributionMetric, setDistributionMetric] = useState<"voc" | "jsc" | "ff" | "pce">("pce");
  const [uniformityDirection, setUniformityDirection] = useState<"forward" | "reverse">("forward");
  const [uniformityPalette, setUniformityPalette] = useState("rdylgn");
  const [distributionPalette, setDistributionPalette] = useState("nature-classic");
  const [uniformityScaleDraft, setUniformityScaleDraft] = useState({ minimum: "", maximum: "", threshold: "" });
  const [uniformityScale, setUniformityScale] = useState<FigureColorScale>({});
  const [uniformityScaleError, setUniformityScaleError] = useState<string | null>(null);
  const [assignmentExpanded, setAssignmentExpanded] = useState(true);
  const [activeSection, setActiveSection] = useState<ResultSection>("assignments");
  const [figuresVisited, setFiguresVisited] = useState(false);
  const [figureSection, setFigureSection] = useState<FigureSection>("jv");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const detail = localDetail ?? serverDetail;
  // Only render a detail whose id matches the current route; a stale detail from
  // a previous result route is never shown or used for mutations.
  const activeDetail = detail && detail.id === resultIdNumber ? detail : null;

  // Route-generation guard: invalidate the previous result during the synchronous
  // commit phase (useLayoutEffect) and on unmount (cleanup runs synchronously
  // before any Promise microtask), so an old-route assignment response cannot
  // update a new route or show a stale toast after leaving.
  const routeGeneration = useRef(0);
  // The detail object the assignment/exclusion prefill last applied to; the
  // prefill effect must run once per loaded detail and never re-run later
  // (a late re-run under load would wipe edits made in between).
  const prefilledDetailRef = useRef<unknown>(null);
  const routeKey = `${resultIdNumber}`;
  useLayoutEffect(() => {
    routeGeneration.current += 1;
    prefilledDetailRef.current = null;
    setLocalDetail(null);
    setAssignments(new Map());
    setInconsistent(new Set());
    setExclusions(new Map());
    setUniformityMetric("pce");
    setDistributionMetric("pce");
    setUniformityDirection("forward");
    setUniformityScaleDraft({ minimum: "", maximum: "", threshold: "" });
    setUniformityScale({});
    setUniformityScaleError(null);
    setAssignmentExpanded(true);
    setActiveSection("assignments");
    setFiguresVisited(false);
    setFigureSection("jv");
    setSubmitting(false);
    setError(null);
    return () => {
      routeGeneration.current += 1;
    };
  }, [routeKey]);

  const isCurrentGeneration = useCallback(
    (generation: number) => routeGeneration.current === generation,
    [],
  );

  const analysis = useMemo<ParsedAnalysis | null>(() => {
    if (!activeDetail) {
      return null;
    }
    const raw = activeDetail.analysis;
    return isParsedAnalysis(raw) ? (raw as ParsedAnalysis) : null;
  }, [activeDetail]);

  const substrates = useMemo(() => substrateList(analysis), [analysis]);
  const devices = useMemo<AnalysisDevice[]>(() => analysis?.devices ?? [], [analysis]);
  // Schema 7: no aggregate summaries are stored — the page-level numbers are
  // derived from the per-trace records (the file's best scan per direction).
  const allTraces = useMemo(() => devices.flatMap((device) => device.traces ?? []), [devices]);
  const validTraceCount = allTraces.filter((trace) => trace.valid).length;
  const bestForwardTrace = useMemo(() => bestTrace(allTraces, "forward"), [allTraces]);
  const bestReverseTrace = useMemo(() => bestTrace(allTraces, "reverse"), [allTraces]);
  const statistics = useMemo<AnalysisStatistics | null>(() => {
    if (!analysis) {
      return null;
    }
    return isStatistics(analysis.statistics) ? analysis.statistics : null;
  }, [analysis]);
  const analysisWarnings = useMemo<string[]>(() => {
    const raw = analysis?.warnings;
    return Array.isArray(raw)
      ? raw.filter((item): item is string => typeof item === "string")
      : [];
  }, [analysis]);
  const groups = useMemo<ResultAssignmentGroup[]>(() => activeDetail?.groups ?? [], [activeDetail]);
  const directionalStatistics = useMemo(
    () => directionalGroupStatistics(devices, groups, new Set(exclusions.keys())),
    [devices, groups, exclusions],
  );
  // Saved assignment provenance comes straight from the detail response, which
  // the backend builds with the same rows as GET /api/results/{id}/assignments.
  // Using it directly removes a same-route GET/POST race where a stale secondary
  // GET could overwrite rows just written by a fresh save; the post-save handler
  // updates localDetail so this stays current without an extra round-trip.
  const effectiveProvenance = useMemo<ResultAssignment[]>(
    () => activeDetail?.assignments ?? [],
    [activeDetail],
  );

  // Detect device-row inconsistency from the effective provenance rows.
  useEffect(() => {
    if (effectiveProvenance.length === 0) {
      setInconsistent(new Set());
      return;
    }
    const bySubstrate = new Map<string, Set<number>>();
    for (const row of effectiveProvenance) {
      const set = bySubstrate.get(row.analysis_substrate_id) ?? new Set<number>();
      set.add(row.batch_condition_id);
      bySubstrate.set(row.analysis_substrate_id, set);
    }
    const bad = new Set<string>();
    for (const [substrateId, conditionIds] of bySubstrate) {
      if (conditionIds.size > 1) {
        bad.add(substrateId);
        continue;
      }
      const substrateRow = substrates.find((s) => s.substrate_id === substrateId);
      if (substrateRow?.batch_condition_id !== undefined) {
        const only = Array.from(conditionIds)[0];
        if (only !== substrateRow.batch_condition_id) {
          bad.add(substrateId);
        }
      }
    }
    setInconsistent(bad);
  }, [effectiveProvenance, substrates]);

  // Preselect from analysis.substrates[].batch_condition_id only, and restore
  // any saved device exclusions so a re-save keeps them until cleared. The
  // ref guard applies this once per loaded detail; a later re-run (new Map
  // identities are irrelevant) would otherwise reset user edits mid-session.
  useEffect(() => {
    if (!activeDetail || prefilledDetailRef.current === activeDetail) {
      return;
    }
    const firstLoad = prefilledDetailRef.current === null;
    prefilledDetailRef.current = activeDetail;
    const next = new Map<string, number>();
    for (const substrate of substrates) {
      if (substrate.batch_condition_id !== undefined) {
        next.set(substrate.substrate_id, substrate.batch_condition_id);
      }
    }
    setAssignments(next);
    const savedExclusions = new Map<string, string>();
    for (const device of devices) {
      if (device.excluded) {
        savedExclusions.set(device.device_id, device.exclusion_reason ?? "");
      }
    }
    setExclusions(savedExclusions);
    if (firstLoad) {
      const hasSavedStatistics = isStatistics(activeDetail.analysis.statistics);
      setAssignmentExpanded(!hasSavedStatistics);
      setActiveSection("assignments");
    }
  }, [activeDetail, substrates, devices]);

  const allAssigned = substrates.length > 0 && substrates.every((s) => assignments.has(s.substrate_id));

  function handleAssign(substrateId: string, value: string) {
    setAssignments((current) => {
      const next = new Map(current);
      if (value === "") {
        next.delete(substrateId);
      } else {
        next.set(substrateId, Number(value));
      }
      return next;
    });
  }

  function applyUniformityScale(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parse = (value: string) => value.trim() === "" ? undefined : Number(value);
    const minimum = parse(uniformityScaleDraft.minimum);
    const maximum = parse(uniformityScaleDraft.maximum);
    const threshold = parse(uniformityScaleDraft.threshold);
    if ([minimum, maximum, threshold].some((value) => value !== undefined && !Number.isFinite(value))) {
      setUniformityScaleError("Enter finite numeric values for the color range.");
      return;
    }
    if ((minimum === undefined) !== (maximum === undefined)) {
      setUniformityScaleError("Enter both a minimum and maximum, or leave both blank for the automatic range.");
      return;
    }
    if (minimum !== undefined && maximum !== undefined && minimum >= maximum) {
      setUniformityScaleError("The color bar minimum must be lower than its maximum.");
      return;
    }
    if (threshold !== undefined && minimum !== undefined && maximum !== undefined &&
        (threshold <= minimum || threshold >= maximum)) {
      setUniformityScaleError("The problem threshold must be inside the color bar range.");
      return;
    }
    setUniformityScale({ minimum, maximum, threshold });
    setUniformityScaleError(null);
  }

  function resetUniformityScale() {
    setUniformityScaleDraft({ minimum: "", maximum: "", threshold: "" });
    setUniformityScale({});
    setUniformityScaleError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeDetail) {
      return;
    }
    const generation = routeGeneration.current;
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        assignments: substrates.map((s) => ({
          analysis_substrate_id: s.substrate_id,
          batch_condition_id: assignments.get(s.substrate_id)!,
        })),
        exclusions: [...exclusions.entries()].map(([analysis_device_id, reason]) => ({
          analysis_device_id,
          reason: reason.trim() || "flagged as an outlier",
        })),
      };
      const updated = await apiFetch<ResultDetail>(
        `/api/results/${resultIdNumber}/assignments`,
        { method: "POST", body: payload },
      );
      if (!isCurrentGeneration(generation)) {
        return;
      }
      // Replace local state with the complete returned ResultDetailResponse.
      setLocalDetail(updated);
      setFigureRevision((current) => current + 1);
      setAssignmentExpanded(false);
      setActiveSection("statistics");
      show("Assignments saved. Analysis updated.", "success");
    } catch (caught) {
      if (isCurrentGeneration(generation)) {
        setError(caught instanceof Error ? caught.message : "Unable to save assignments.");
      }
    } finally {
      if (isCurrentGeneration(generation)) {
        setSubmitting(false);
      }
    }
  }

  if (!Number.isInteger(resultIdNumber) || resultIdNumber <= 0) {
    return <ErrorState title="Invalid result" message="The result identifier is not valid." />;
  }
  if (resource.status === "loading" && activeDetail === null) {
    return <div className="page-loading" role="status">Loading result…</div>;
  }
  if (resource.status === "error" && activeDetail === null) {
    return (
      <ErrorState
        title="Unable to load result"
        message={resource.error ?? "The result could not be loaded."}
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
  if (!analysis) {
    return (
      <div data-result-detail="true">
        <PageHeader
          title={activeDetail.filename}
          description={`Result file ${activeDetail.id} · ${activeDetail.content_type}`}
        />
        <ErrorState
          title="Characterization analysis unavailable"
          message="The characterization analysis for this result is not available in a readable form. Re-upload the result file or contact an instructor."
        />
      </div>
    );
  }

  const experimentId = activeDetail.experiment_id;
  const statisticsPresent = statistics !== null;

  return (
    <div data-result-detail="true">
      <PageHeader
        title={activeDetail.filename}
        description={`Result file ${activeDetail.id} · ${activeDetail.content_type}`}
        meta={`Uploaded ${formatDateTime(activeDetail.created_at)}`}
        actions={
          <>
            <Link className="button button--secondary" to={`/experiments/${experimentId}`}>Experiment</Link>
            <Link className="button button--secondary" to={`/experiments/${experimentId}/batches/${activeDetail.fabrication_batch_id}`}>Batch</Link>
          </>
        }
      />

      {analysisWarnings.length > 0 ? (
        <div className="analysis-warnings" role="alert">
          <strong>Measurement quality warnings</strong>
          <ul>
            {analysisWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="stat-tiles" role="list">
        <div className="stat-tile" role="listitem">
          <span className="stat-tile__value">{substrates.length}</span>
          <span className="stat-tile__label">Substrates</span>
        </div>
        <div className="stat-tile" role="listitem">
          <span className="stat-tile__value">{devices.length}</span>
          <span className="stat-tile__label">Devices</span>
        </div>
        <div className="stat-tile" role="listitem">
          <span className="stat-tile__value">
            {validTraceCount || "—"}{allTraces.length ? ` / ${allTraces.length}` : ""}
          </span>
          <span className="stat-tile__label">Valid traces</span>
        </div>
        <div className="stat-tile" role="listitem">
          <span className="stat-tile__value">
            {formatNumber(bestForwardTrace?.metrics?.pce, 2)}
          </span>
          <span className="stat-tile__label">Best forward PCE (%)</span>
        </div>
        <div className="stat-tile" role="listitem">
          <span className="stat-tile__value">{formatNumber(bestReverseTrace?.metrics?.pce, 2)}</span>
          <span className="stat-tile__label">Best reverse PCE (%)</span>
        </div>
      </div>

      <nav className="result-section-nav" aria-label="Result sections">
        {([
          ["assignments", "Assignments"],
          ["statistics", "Statistics"],
          ["figures", "Figures"],
          ["records", "Data & provenance"],
        ] as const).map(([section, label]) => (
          <button key={section} type="button"
            className={`result-section-nav__button${activeSection === section ? " result-section-nav__button--active" : ""}`}
            aria-pressed={activeSection === section}
            disabled={section === "statistics" && !statisticsPresent}
            onClick={() => {
              if (section === "figures") setFiguresVisited(true);
              setActiveSection(section);
            }}>
            {label}
            {section === "assignments" ? <span className="result-section-nav__count">{assignments.size}/{substrates.length}</span> : null}
          </button>
        ))}
      </nav>

      {activeSection === "figures" ? (
        <nav className="result-figure-nav" aria-label="Figure types">
          {([
            ["jv", "J–V curves"],
            ["uniformity", "Uniformity"],
            ["distributions", "Distributions"],
          ] as const).map(([section, label]) => (
            <button key={section} type="button"
              className={`result-figure-nav__button${figureSection === section ? " result-figure-nav__button--active" : ""}`}
              aria-pressed={figureSection === section}
              disabled={section !== "jv" && !statisticsPresent}
              onClick={() => setFigureSection(section)}>{label}</button>
          ))}
        </nav>
      ) : null}

      {activeSection === "records" ? <>
      <section className="panel" aria-labelledby="result-meta-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="result-meta-title">Integrity &amp; provenance</h2>
        </div>
        <dl className="meta-grid">
          <div><dt>Experiment</dt><dd>{experimentId}</dd></div>
          <div><dt>Size</dt><dd>{activeDetail.size_bytes} bytes</dd></div>
          <div><dt>SHA-256</dt><dd><code title={activeDetail.sha256}>{(activeDetail.sha256 ?? "").slice(0, 16)}…</code></dd></div>
          <div><dt>Analysis schema</dt><dd>Schema v{activeDetail.analysis_schema_version}</dd></div>
          <div><dt>Uploaded by</dt><dd>{activeDetail.created_by_id === null ? "Not available" : activeDetail.created_by_id}</dd></div>
        </dl>
      </section>
      </> : null}

      {activeSection === "assignments" ? <>
      <section className="panel" aria-labelledby="assignment-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="assignment-title">Substrate condition assignment</h2>
          <div className="panel__heading-actions">
            {statisticsPresent ? <span className="record-count">{statistics!.groups.length} groups</span> : null}
            {!assignmentExpanded ? (
              <button
                type="button"
                className="button button--secondary button--small"
                aria-expanded="false"
                onClick={() => setAssignmentExpanded(true)}
              >
                Edit assignments
              </button>
            ) : null}
          </div>
        </div>
        <p className="run-sheet-muted">
          Select exactly one experiment condition for each substrate name read from the measurement file.
          Names do not set conditions automatically. If a name is not a physical laser mark, condition
          statistics and figures remain available, while physical device linkage stays unresolved.
        </p>
        {!statisticsPresent ? (
          <p className="run-sheet-muted">All substrates must be assigned before statistics are calculated.</p>
        ) : null}
        {assignmentExpanded ? (
          <AssignmentForm
            substrates={substrates}
            assignments={assignments}
            groups={groups}
            inconsistent={inconsistent}
            submitting={submitting}
            error={error}
            allAssigned={allAssigned}
            statisticsPresent={statisticsPresent}
            onAssign={handleAssign}
            onSubmit={(event) => void submit(event)}
          />
        ) : (
          <p className="run-sheet-muted">Assignments saved for {substrates.length} substrates.</p>
        )}
      </section>

      <details className="result-exclusions-details">
        <summary>Device exclusions <span>{exclusions.size} selected</span></summary>
        <DeviceExclusionsPanel
          devices={devices}
          groups={groups}
          exclusions={exclusions}
          onChange={(next) => {
            setExclusions(next);
            setAssignmentExpanded(true);
          }}
        />
        {assignmentExpanded ? (
          <button className="button button--primary" type="submit" form="result-assignment-form" disabled={!allAssigned || submitting}>
            {submitting ? "Saving…" : "Save condition and exclusion changes"}
          </button>
        ) : null}
      </details>
      </> : null}

      {activeSection === "records" ? <>
      <details className="result-collapsible">
        <summary>Device scan history <span>{effectiveProvenance.length} assignments</span></summary>
      <DeviceScanHistoryPanel assignments={effectiveProvenance} />
      </details>

      <details className="result-collapsible">
        <summary>Saved assignment provenance <span>{effectiveProvenance.length} rows</span></summary>
      <section className="panel" aria-labelledby="provenance-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="provenance-title">Saved assignment provenance</h2>
        </div>
        <ProvenanceTable rows={effectiveProvenance} />
      </section>
      </details>
      <details className="result-collapsible">
        <summary>Parsed devices <span>{devices.length} devices</span></summary>
      <DeviceInspectionTable devices={devices} groups={groups} />
      </details>
      </> : null}

      {figuresVisited ? <div hidden={activeSection !== "figures" || figureSection !== "jv"}>
        <JvChart key={resultIdNumber} resultId={resultIdNumber} devices={devices} groups={groups} figureRevision={figureRevision} />
      </div> : null}
      {activeSection === "figures" && figureSection === "uniformity" ? (
      <section className="panel" aria-labelledby="uniformity-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="uniformity-title">Publication substrate uniformity</h2>
          <label>Metric <select className="text-input" value={uniformityMetric}
            onChange={(event) => {
              setUniformityMetric(event.target.value as typeof uniformityMetric);
              resetUniformityScale();
            }}>
            {METRIC_META.map((metric) => <option key={metric.name} value={metric.name}>{metric.label}</option>)}
          </select></label>
          <label>Scan direction <select className="text-input" value={uniformityDirection}
            onChange={(event) => setUniformityDirection(event.target.value as typeof uniformityDirection)}>
            <option value="forward">Forward</option>
            <option value="reverse">Reverse</option>
          </select></label>
          <label>Color palette <select className="text-input" value={uniformityPalette}
            onChange={(event) => setUniformityPalette(event.target.value)}>
            {GRADIENT_PALETTES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        </div>
        <form className="figure-scale-controls" onSubmit={applyUniformityScale}>
          <div className="figure-scale-controls__fields">
            <label>Color bar minimum <input className="text-input" type="number" step="any"
              value={uniformityScaleDraft.minimum}
              onChange={(event) => setUniformityScaleDraft((current) => ({ ...current, minimum: event.target.value }))} /></label>
            <label>Color bar maximum <input className="text-input" type="number" step="any"
              value={uniformityScaleDraft.maximum}
              onChange={(event) => setUniformityScaleDraft((current) => ({ ...current, maximum: event.target.value }))} /></label>
            <label>Problem threshold <input className="text-input" type="number" step="any"
              value={uniformityScaleDraft.threshold}
              onChange={(event) => setUniformityScaleDraft((current) => ({ ...current, threshold: event.target.value }))} /></label>
          </div>
          <div className="button-row">
            <button className="button button--secondary button--small" type="submit">Apply color range</button>
            <button className="button button--secondary button--small" type="button" onClick={resetUniformityScale}>Reset color range</button>
          </div>
          <InlineFormError message={uniformityScaleError} />
        </form>
        <p className="run-sheet-muted">Values use the selected metric's unit. Blank bounds use the automatic range. The threshold marks the color scale midpoint; with RdYlGn, values below it are red/yellow and values above it are green. Both device scopes share the scale. For diverging red-blue, white marks the threshold when set; otherwise it marks the all-device median if within range, or the selected range midpoint. Color bar ticks and cell numbers show the measured metric.</p>
        <FigureScopePair resultId={resultIdNumber} kind="uniformity" metric={uniformityMetric} direction={uniformityDirection}
          excludedDeviceIds={[...exclusions.keys()]} revision={figureRevision} palette={uniformityPalette} scale={uniformityScale}
          alt={`Publication substrate uniformity for ${uniformityMetric}, ${uniformityDirection} scan`} />
      </section>
      ) : null}

      {statisticsPresent && activeSection === "statistics" ? (
          <section className="panel" aria-labelledby="stats-title">
            <div className="panel__heading">
              <h2 className="panel__title" id="stats-title">Directional group statistics</h2>
            </div>
            <p className="run-sheet-muted">One representative scan per device and direction. Best and mean are calculated separately for forward and reverse scans. Both scopes use the current exclusion selection.</p>
            <div className="table-scroll">
              <table className="data-table" aria-label="Directional group statistics">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Scope</th>
                    <th>Scan</th>
                    <th>Devices</th>
                    {METRIC_META.map((m) => <th key={m.name}>{m.label}<br /><span className="run-sheet-muted">Best / mean</span></th>)}
                  </tr>
                </thead>
                <tbody>
                  {directionalStatistics.map((row) => (
                    <tr key={`${row.groupId}-${row.scope}-${row.direction}`}>
                      <td>{row.groupName}</td>
                      <td>{row.scope === "all" ? "All devices" : "After exclusions"}</td>
                      <td>{row.direction === "forward" ? "Forward" : "Reverse"}</td>
                      <td>{row.deviceCount}</td>
                      {METRIC_META.map((m) => {
                        const stat = row.metrics[m.name];
                        return (
                          <td key={m.name}>
                            <strong>{formatNumber(scaleMetric(m.name, stat.maximum), 2)}</strong>
                            <br />
                            <span className="run-sheet-muted">{formatNumber(scaleMetric(m.name, stat.mean), 2)}</span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
      ) : null}

      {statisticsPresent && activeSection === "figures" && figureSection === "distributions" ? (
          <section className="panel" aria-labelledby="boxplot-title">
            <div className="panel__heading">
              <h2 className="panel__title" id="boxplot-title">Metric distributions</h2>
              <label>Metric <select className="text-input" value={distributionMetric}
                onChange={(event) => setDistributionMetric(event.target.value as typeof distributionMetric)}>
                {METRIC_META.map((metric) => <option key={metric.name} value={metric.name}>{metric.label}</option>)}
              </select></label>
              <label>Color palette <select className="text-input" value={distributionPalette}
                onChange={(event) => setDistributionPalette(event.target.value)}>
                {CATEGORICAL_PALETTES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select></label>
            </div>
            <p className="run-sheet-muted">Forward and reverse scans are separate (F/R). Both device scopes use the current exclusion selection.</p>
            <FigureScopePair resultId={resultIdNumber} kind="boxplot" metric={distributionMetric}
              excludedDeviceIds={[...exclusions.keys()]} revision={figureRevision} palette={distributionPalette}
              alt={`${METRIC_META.find((metric) => metric.name === distributionMetric)?.label} publication box plot with device points, split by scan direction`}
            />
          </section>
      ) : null}
    </div>
  );
}
