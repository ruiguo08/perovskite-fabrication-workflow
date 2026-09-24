import { useMemo, useState } from "react";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";
import { formatNumber, scaleMetric } from "../lib/format";
import { hasMetrics, pooledMetric } from "../lib/deviceMetrics";

const DEFAULT_THRESHOLDS = { voc: "0.7", pce: "10", ff: "60" };

interface DeviceExclusionsPanelProps {
  devices: AnalysisDevice[];
  groups: ResultAssignmentGroup[];
  /** Pending exclusions (device id -> reason), including saved ones. */
  exclusions: Map<string, string>;
  onChange: (exclusions: Map<string, string>) => void;
}

/**
 * Flag outlier devices (dead/shorted cells) so group statistics and every
 * chart skip them. Exclusion never deletes data: the device keeps its traces,
 * metrics, and assignment, and the flag with its reason is stored in the
 * saved analysis for provenance.
 */
export function DeviceExclusionsPanel({
  devices,
  groups,
  exclusions,
  onChange,
}: DeviceExclusionsPanelProps) {
  const [vocThreshold, setVocThreshold] = useState(DEFAULT_THRESHOLDS.voc);
  const [pceThreshold, setPceThreshold] = useState(DEFAULT_THRESHOLDS.pce);
  const [ffThreshold, setFfThreshold] = useState(DEFAULT_THRESHOLDS.ff);

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
    const vocLimit = Number(vocThreshold);
    const pceLimit = Number(pceThreshold);
    const ffLimit = Number(ffThreshold);
    const next = new Map(exclusions);
    for (const device of devices) {
      if (!hasMetrics(device.metrics)) {
        continue;
      }
      const reasons: string[] = [];
      const voc = pooledMetric(device.metrics, "voc");
      const pce = pooledMetric(device.metrics, "pce");
      const ff = pooledMetric(device.metrics, "ff");
      if (voc !== null && Number.isFinite(vocLimit) && voc < vocLimit) {
        reasons.push(`Voc < ${vocThreshold} V`);
      }
      if (pce !== null && Number.isFinite(pceLimit) && pce < pceLimit) {
        reasons.push(`PCE < ${pceThreshold}%`);
      }
      if (ff !== null && Number.isFinite(ffLimit) && ff * 100 < ffLimit) {
        reasons.push(`FF < ${ffThreshold}%`);
      }
      if (reasons.length) {
        next.set(device.device_id, reasons.join("; "));
      }
    }
    onChange(next);
  }

  function clearAll() {
    onChange(new Map());
  }

  return (
    <section className="panel" aria-labelledby="exclusions-title">
      <div className="panel__heading">
        <h2 className="panel__title" id="exclusions-title">Device exclusions</h2>
        <span className="record-count">{exclusions.size} excluded</span>
      </div>
      <p className="run-sheet-muted">
        Dead or shorted devices can be excluded from statistics and charts. Exclusion keeps the
        device data and is stored with a reason when assignments are saved. A common rule flags
        Voc &lt; 0.7 V, PCE &lt; 10%, or FF &lt; 60%. Values below use the mean of the forward and
        reverse representative scans when both exist (or the combined value if supplied).
        Thresholds use the same values.
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
            Flag matching devices
          </button>
          <button
            type="button"
            className="button button--secondary"
            onClick={clearAll}
            disabled={exclusions.size === 0}
          >
            Clear exclusions
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
              <th>Voc (V), F/R mean</th>
              <th>PCE (%), F/R mean</th>
              <th>FF (%), F/R mean</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => {
              const excluded = exclusions.has(device.device_id);
              return (
                <tr
                  key={device.device_id}
                  className={excluded ? "exclusion-row--excluded" : undefined}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={excluded}
                      aria-label={`Exclude ${device.device_id}`}
                      onChange={() => toggle(device.device_id)}
                    />
                  </td>
                  <td>{device.device_id}</td>
                  <td>{device.substrate_id}</td>
                  <td>{groupNames.get(device.group_id) || "Unassigned"}</td>
                  <td>{formatNumber(pooledMetric(device.metrics, "voc"), 3)}</td>
                  <td>{formatNumber(pooledMetric(device.metrics, "pce"), 2)}</td>
                  <td>{formatNumber(scaleMetric("ff", pooledMetric(device.metrics, "ff")), 2)}</td>
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
                    ) : (
                      "—"
                    )}
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
