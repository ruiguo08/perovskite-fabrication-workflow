import { useMemo, useState } from "react";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";
import { formatNumber, scaleMetric } from "../lib/format";
import { evaluateDeviceExclusion, parseExclusionThreshold, type ExclusionThresholds } from "../lib/deviceExclusionRules";

const DEFAULT_THRESHOLDS = { voc: "0.7", pce: "10", ff: "60" };

interface DeviceExclusionsPanelProps {
  devices: AnalysisDevice[];
  groups: ResultAssignmentGroup[];
  /** Persisted manual exclusions (device id -> reason), including unsaved edits. */
  exclusions: Map<string, string>;
  onChange: (exclusions: Map<string, string>) => void;
  automaticExclusions: Map<string, string>;
  initialThresholds?: ExclusionThresholds | null;
  onApplyAutomatic: (exclusions: Map<string, string>, thresholds: ExclusionThresholds) => void;
}

/**
 * Flag outlier devices (dead/shorted cells) for statistics and statistical
 * figures. Exclusion never deletes data: the device keeps its traces,
 * metrics, and assignment, and the flag with its reason is stored in the
 * saved analysis for provenance.
 */
export function DeviceExclusionsPanel({
  devices,
  groups,
  exclusions,
  onChange,
  automaticExclusions,
  initialThresholds,
  onApplyAutomatic,
}: DeviceExclusionsPanelProps) {
  const [vocThreshold, setVocThreshold] = useState(() => initialThresholds?.voc?.toString() ?? DEFAULT_THRESHOLDS.voc);
  const [pceThreshold, setPceThreshold] = useState(() => initialThresholds?.pce?.toString() ?? DEFAULT_THRESHOLDS.pce);
  const [ffThreshold, setFfThreshold] = useState(() => initialThresholds?.ff?.toString() ?? DEFAULT_THRESHOLDS.ff);

  const groupNames = useMemo(
    () => new Map(groups.map((group) => [group.group_id, group.name])),
    [groups],
  );

  function toggle(deviceId: string) {
    const next = new Map(exclusions);
    if (next.has(deviceId)) {
      next.delete(deviceId);
    } else {
      next.set(deviceId, "flagged as an outlier");
    }
    onChange(next);
  }

  function setReason(deviceId: string, reason: string) {
    const next = new Map(exclusions);
    next.set(deviceId, reason);
    onChange(next);
  }

  function applyPreset() {
    const thresholds = {
      voc: parseExclusionThreshold(vocThreshold),
      pce: parseExclusionThreshold(pceThreshold),
      ff: parseExclusionThreshold(ffThreshold),
    };
    const next = new Map<string, string>();
    for (const device of devices) {
      const reason = evaluateDeviceExclusion(device, thresholds);
      if (reason) next.set(device.device_id, reason);
    }
    onApplyAutomatic(next, thresholds);
  }

  function clearAll() {
    onChange(new Map());
  }

  return (
    <section className="panel" aria-labelledby="exclusions-title">
      <div className="panel__heading">
        <h2 className="panel__title" id="exclusions-title">Device exclusions</h2>
        <span className="record-count">{exclusions.size} manual · {automaticExclusions.size} threshold matches</span>
      </div>
      <p className="run-sheet-muted">
        Automatic exclusion requires both forward and reverse representative scans to fall below
        at least one enabled threshold. Each metric uses the same threshold in both directions;
        different metrics may trigger each direction. Devices with a missing direction need manual
        review. Threshold matches apply only to the current analysis view and are not saved.
        Manual reasons are saved and take priority. Exclusion never removes J–V curves or the underlying measurements.
      </p>
      <div className="exclusion-presets">
        <label className="form-field">
          <span className="form-field__label">Voc below (V)</span>
          <input
            className="text-input"
            type="number"
            step="0.05"
            min="0"
            value={vocThreshold}
            onChange={(event) => setVocThreshold(event.target.value)}
            aria-label="Flag devices with Voc below (V)"
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">PCE below (%)</span>
          <input
            className="text-input"
            type="number"
            step="0.5"
            min="0"
            value={pceThreshold}
            onChange={(event) => setPceThreshold(event.target.value)}
            aria-label="Flag devices with PCE below (%)"
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">FF below (%)</span>
          <input
            className="text-input"
            type="number"
            step="1"
            min="0"
            max="100"
            value={ffThreshold}
            onChange={(event) => setFfThreshold(event.target.value)}
            aria-label="Flag devices with FF below (%)"
          />
        </label>
        <div className="exclusion-presets__actions">
          <button type="button" className="button button--secondary" onClick={applyPreset}>
            Apply thresholds
          </button>
          <button type="button" className="button button--secondary" onClick={() => {
            setVocThreshold(DEFAULT_THRESHOLDS.voc);
            setPceThreshold(DEFAULT_THRESHOLDS.pce);
            setFfThreshold(DEFAULT_THRESHOLDS.ff);
            onApplyAutomatic(new Map(), { voc: null, pce: null, ff: null });
          }}
            disabled={!initialThresholds}>Clear threshold filter</button>
          <button
            type="button"
            className="button button--secondary"
            onClick={clearAll}
            disabled={exclusions.size === 0}
          >
            Clear manual exclusions
          </button>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Exclude</th>
              <th>Device</th>
              <th>Substrate</th>
              <th>Group</th>
              <th>Voc (V), F / R</th>
              <th>PCE (%), F / R</th>
              <th>FF (%), F / R</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => {
              const excluded = exclusions.has(device.device_id);
              const automaticReason = automaticExclusions.get(device.device_id);
              return (
                <tr
                  key={device.device_id}
                  className={excluded || automaticReason ? "exclusion-row--excluded" : undefined}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={excluded}
                      aria-label={`Exclude ${device.device_id}`}
                      onChange={() => toggle(device.device_id)}
                    />
                  </td>
                  <td>{device.device_id}{automaticReason ? <span className="status-badge">Threshold match</span> : null}</td>
                  <td>{device.substrate_id}</td>
                  <td>{groupNames.get(device.group_id) || "Unassigned"}</td>
                  <td>{formatNumber(device.metrics?.forward?.voc, 3)} / {formatNumber(device.metrics?.reverse?.voc, 3)}</td>
                  <td>{formatNumber(device.metrics?.forward?.pce, 2)} / {formatNumber(device.metrics?.reverse?.pce, 2)}</td>
                  <td>{formatNumber(scaleMetric("ff", device.metrics?.forward?.ff), 2)} / {formatNumber(scaleMetric("ff", device.metrics?.reverse?.ff), 2)}</td>
                  <td>
                    {excluded ? (
                      <input
                        className="text-input"
                        type="text"
                        value={exclusions.get(device.device_id) ?? ""}
                        maxLength={200}
                        aria-label={`Exclusion reason for ${device.device_id}`}
                        onChange={(event) => setReason(device.device_id, event.target.value)}
                      />
                    ) : (automaticReason ?? "—")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
