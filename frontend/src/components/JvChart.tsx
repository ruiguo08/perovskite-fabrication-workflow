import { useMemo, useState } from "react";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";
import { formatNumber, scaleMetric } from "../lib/format";
import { bestPce, hasMetrics, pooledMetric } from "../lib/deviceMetrics";
import { DeviceMultiSelect } from "./DeviceMultiSelect";
import { PublicationFigure } from "./PublicationFigure";

const MAX_PLOTTED_DEVICES = 12;
const JV_PALETTES = [
  ["standalone", "Standalone J–V (orange / teal)"],
  ["nature-classic", "Nature Classic"],
  ["science-tol", "Science / Paul Tol"],
  ["lancet-clinical", "Lancet Clinical"],
  ["nejm", "NEJM Palette"],
] as const;

export function JvChart({ resultId, devices, groups, figureRevision }: {
  resultId: number;
  devices: AnalysisDevice[];
  groups: ResultAssignmentGroup[];
  figureRevision?: number;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [plotted, setPlotted] = useState<string[]>([]);
  const [palette, setPalette] = useState("standalone");
  const groupNames = useMemo(() => new Map(groups.map((group) => [group.group_id, group.name])), [groups]);

  function applySelection(next: Set<string>) {
    setSelected(next);
    setPlotted([]);
  }
  function selectAll() {
    applySelection(new Set(devices.map((device) => device.device_id)));
  }
  function clearAll() {
    applySelection(new Set());
  }
  function plotSelected() {
    setPlotted(Array.from(selected).slice(0, MAX_PLOTTED_DEVICES));
  }
  function selectBestPerGroup() {
    const next = new Set<string>();
    for (const group of groups) {
      const best = devices
        .filter((device) => device.group_id === group.group_id && hasMetrics(device.metrics))
        .sort((left, right) => (bestPce(right) ?? -Infinity) - (bestPce(left) ?? -Infinity))[0];
      if (best) next.add(best.device_id);
    }
    applySelection(next);
  }

  const allSelected = devices.length > 0 && selected.size === devices.length;
  return <section className="panel" aria-labelledby="jv-chart-title">
    <div className="panel__heading">
      <h2 className="panel__title" id="jv-chart-title">Publication J–V curves</h2>
      <div className="button-row">
        <button type="button" className="button button--secondary button--small" onClick={selectAll}>Select all</button>
        <button type="button" className="button button--secondary button--small" onClick={selectBestPerGroup}>Select best per group</button>
        <button type="button" className="button button--secondary button--small" onClick={plotSelected} disabled={!selected.size}>Plot selected</button>
        <button type="button" className="button button--secondary button--small" onClick={clearAll}>Clear</button>
        <span className="run-sheet-muted">{selected.size} selected{allSelected ? " · all" : ""}</span>
      </div>
    </div>
    <label>Color palette <select className="text-input" value={palette}
      onChange={(event) => setPalette(event.target.value)}>
      {JV_PALETTES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>
    <DeviceMultiSelect devices={devices} selected={selected} onChange={applySelection} />
    {selected.size > MAX_PLOTTED_DEVICES && <p className="run-sheet-muted" role="status">
      The first {MAX_PLOTTED_DEVICES} selected devices will be plotted.
    </p>}
    <p className="run-sheet-muted">
      {plotted.length
        ? `${plotted.length} selected device${plotted.length === 1 ? "" : "s"} shown. Clear to return to all devices.`
        : "Showing every device by group. Select devices and choose Plot selected for individual curves."}
    </p>
    <PublicationFigure resultId={resultId} kind="jv" deviceIds={plotted} revision={figureRevision} palette={palette}
      alt={plotted.length ? `Publication J-V curves for ${plotted.join(", ")}` : "All-device J-V curves by group"} />
    <details className="result-inline-details">
      <summary>Device metrics <span>{devices.length} devices</span></summary>
    <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>Select</th><th>Device</th><th>Substrate</th><th>Group</th><th>Valid scans</th><th>Voc</th><th>Jsc</th><th>FF</th><th>PCE</th></tr></thead>
        <tbody>{devices.map((device) => <tr key={device.device_id}>
          <td><input type="checkbox" aria-label={`Select ${device.device_id}`} checked={selected.has(device.device_id)}
            value={device.device_id}
            onChange={(event) => {
              const next = new Set(selected);
              if (event.target.checked) next.add(device.device_id); else next.delete(device.device_id);
              applySelection(next);
            }} /></td>
          <td>{device.device_id}{device.excluded && <span className="status-badge status-badge--danger">excluded</span>}</td>
          <td>{device.substrate_id}</td><td>{groupNames.get(device.group_id) ?? "Unassigned"}</td>
          <td>{device.traces.filter((trace) => trace.valid).length}</td>
          <td>{formatNumber(pooledMetric(device.metrics, "voc"), 3)}</td>
          <td>{formatNumber(pooledMetric(device.metrics, "jsc"), 2)}</td>
          <td>{formatNumber(scaleMetric("ff", pooledMetric(device.metrics, "ff")), 2)}</td>
          <td>{formatNumber(pooledMetric(device.metrics, "pce"), 2)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    </details>
  </section>;
}
