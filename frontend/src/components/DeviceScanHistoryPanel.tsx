import { useCallback, useMemo, useState } from "react";
import { apiFetch } from "../lib/api";
import { formatDateTime, formatNumber, scaleMetric } from "../lib/format";
import { useToast } from "./Toast";
import { useApiResource } from "../lib/useApiResource";
import type { DeviceJvScans, ResultAssignment } from "../types/api";

const METRIC_COLUMNS: { name: "voc" | "jsc" | "ff" | "pce"; label: string }[] = [
  { name: "voc", label: "Voc (V)" },
  { name: "jsc", label: "Jsc (mA cm⁻²)" },
  { name: "ff", label: "FF (%)" },
  { name: "pce", label: "PCE (%)" },
];

/**
 * Per-device scan history across all uploads (schema 7).
 *
 * A physical device may be scanned many times — repeat scans inside one
 * upload, and fresh uploads days later. Every scan is listed verbatim; the
 * UI defaults to each direction's highest-PCE scan, and the user can pin a
 * different scan as the representative (stored server-side, audited) until
 * cleared.
 */
export function DeviceScanHistoryPanel({ assignments }: { assignments: ResultAssignment[] }) {
  const devices = useMemo(() => {
    const labels = new Map<number, string>();
    for (const row of assignments) {
      if (row.fabrication_device_id !== null && row.fabrication_device_id !== undefined) {
        labels.set(row.fabrication_device_id, row.device_mark ? `${row.device_mark} · #${row.fabrication_device_id}` : row.device_code || `Device ${row.fabrication_device_id}`);
      }
    }
    return Array.from(labels, ([id, label]) => ({ id, label })).sort((a, b) => a.id - b.id);
  }, [assignments]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const activeId = devices.some((device) => device.id === selectedId) ? selectedId : devices[0]?.id;

  if (devices.length === 0 || activeId == null) {
    return null;
  }

  return (
    <section className="panel" aria-labelledby="device-scans-title">
      <div className="panel__heading">
        <h2 className="panel__title" id="device-scans-title">Device scan history</h2>
        <span className="record-count">{devices.length} device{devices.length === 1 ? "" : "s"}</span>
      </div>
      <label className="form-field device-scan-picker">
        <span className="form-field__label">Device</span>
        <select className="text-input" value={activeId} onChange={(event) => setSelectedId(Number(event.target.value))}>
          {devices.map((device) => <option key={device.id} value={device.id}>{device.label}</option>)}
        </select>
      </label>
      <DeviceScanCard key={activeId} fabricationDeviceId={activeId} />
    </section>
  );
}

function DeviceScanCard({ fabricationDeviceId }: { fabricationDeviceId: number }) {
  const loadScans = useCallback(
    () => apiFetch<DeviceJvScans>(`/api/fabrication-devices/${fabricationDeviceId}/jv-scans`),
    [fabricationDeviceId],
  );
  const resource = useApiResource<DeviceJvScans>(loadScans, { resetOnLoaderChange: true });
  const { show } = useToast();

  const mutate = useCallback(
    async (apply: () => Promise<unknown>) => {
      try {
        await apply();
        await resource.reload();
      } catch (error) {
        show(error instanceof Error ? error.message : "The request failed.");
      }
    },
    [resource, show],
  );

  const data = resource.data;
  if (resource.status === "error") {
    return (
      <div className="run-sheet-muted" role="alert">
        Unable to load scan history for device {fabricationDeviceId}: {resource.error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="run-sheet-muted" aria-busy="true">
        Loading scan history…
      </div>
    );
  }

  const setRepresentative = (direction: string, resultFileId: number, traceId: string) =>
    void mutate(() =>
      apiFetch(`/api/fabrication-devices/${fabricationDeviceId}/jv-scans/representative`, {
        method: "PUT",
        body: { direction, result_file_id: resultFileId, trace_id: traceId },
      }),
    );
  const clearRepresentative = (direction: string) =>
    void mutate(() =>
      apiFetch(
        `/api/fabrication-devices/${fabricationDeviceId}/jv-scans/representative?direction=${direction}`,
        { method: "DELETE" },
      ),
    );

  return (
    <div className="device-scan-card" data-device-scan-card={data.fabrication_device_id}>
      <h3 title={data.device_code}>{data.device_mark || data.device_code}</h3>
      {(["forward", "reverse"] as const).map((direction) => {
        const representative = data.representative[direction];
        if (!representative) {
          return (
            <p key={direction} className="run-sheet-muted">
              No valid {direction} scan on record.
            </p>
          );
        }
        return (
          <div key={direction} className="device-representative" data-representative={direction}>
            <h4>
              {direction === "forward" ? "Forward" : "Reverse"} best{" "}
              <span className="status-badge">
                {representative.from_user_selection ? "user choice" : "best PCE"}
              </span>
              {representative.from_user_selection ? (
                <button
                  type="button"
                  className="button button--secondary button--small"
                  onClick={() => clearRepresentative(direction)}
                >
                  Clear choice
                </button>
              ) : null}
            </h4>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    {METRIC_COLUMNS.map((column) => (
                      <th key={column.name} scope="col">{column.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {METRIC_COLUMNS.map((column) => (
                      <td key={column.name}>
                        {formatNumber(
                          scaleMetric(column.name, representative.metrics[column.name]),
                          2,
                        )}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="run-sheet-muted">
              From {representative.result_file_id} · {representative.trace_id}
              {representative.measured_at ? ` · measured ${formatDateTime(representative.measured_at)}` : ""}
              {representative.metric_source ? ` · ${representative.metric_source}` : ""}
            </p>
          </div>
        );
      })}
      <details className="device-scan-details">
        <summary>All scans ({data.scans.length})</summary>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Direction</th>
              <th scope="col">Measured</th>
              <th scope="col">PCE (%)</th>
              <th scope="col">Source</th>
              <th scope="col">File</th>
              <th scope="col">Representative</th>
            </tr>
          </thead>
          <tbody>
            {data.scans.map((scan) => {
              const isRepresentative =
                data.representative.forward?.result_file_id === scan.result_file_id &&
                data.representative.forward?.trace_id === scan.trace_id
                  ? "forward"
                  : data.representative.reverse?.result_file_id === scan.result_file_id &&
                      data.representative.reverse?.trace_id === scan.trace_id
                    ? "reverse"
                    : null;
              return (
                <tr key={`${scan.result_file_id}-${scan.trace_id}`}>
                  <td>
                    <span className="status-badge">
                      {scan.direction} {scan.valid ? "valid" : "invalid"}
                    </span>
                  </td>
                  <td>{formatDateTime(scan.measured_at ?? scan.uploaded_at)}</td>
                  <td>{formatNumber(scaleMetric("pce", scan.metrics?.pce), 2)}</td>
                  <td>{scan.metric_source ?? (scan.error ? `error: ${scan.error}` : "—")}</td>
                  <td>{scan.filename}</td>
                  <td>
                    {isRepresentative ? (
                      <strong>current</strong>
                    ) : scan.valid && scan.metrics ? (
                      <button
                        type="button"
                        className="button button--secondary button--small"
                        onClick={() =>
                          setRepresentative(scan.direction, scan.result_file_id, scan.trace_id)
                        }
                      >
                        Set as representative
                      </button>
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
      </details>
    </div>
  );
}
