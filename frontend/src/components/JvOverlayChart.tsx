import { useMemo, useState } from "react";
import type { AnalysisDevice, ResultAssignmentGroup } from "../types/api";
import { formatNumber } from "../lib/format";
import {
  FORWARD_COLOR,
  REVERSE_COLOR,
  groupColor,
  tracePath,
  tracePlotPoints,
} from "../lib/jvPlot";
import { ChartExportButtons } from "./ChartExportButtons";
import { extentOf } from "../lib/extent";
import { bestPce, hasMetrics } from "../lib/deviceMetrics";

const MAX_OVERLAY_CURVES = 24;
const WIDTH = 760;
const HEIGHT = 500;
const MARGIN = { top: 20, right: 24, bottom: 58, left: 68 };
const PLOT_WIDTH = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = HEIGHT - MARGIN.top - MARGIN.bottom;

interface OverlaySeries {
  device: AnalysisDevice;
  color: string;
  curves: { direction: string; dashed: boolean; path: string }[];
}

interface JvOverlayChartProps {
  devices: AnalysisDevice[];
  groups: ResultAssignmentGroup[];
}

/**
 * Multi-device J-V comparison: every assigned device's curves are drawn in one
 * coordinate system, colored by condition group (forward solid, reverse
 * dashed), so control and target conditions can be compared directly.
 */
export function JvOverlayChart({ devices, groups }: JvOverlayChartProps) {
  const [bestOnly, setBestOnly] = useState(true);
  const [hiddenGroups, setHiddenGroups] = useState<Set<string>>(new Set());

  const assigned = useMemo(
    () => devices.filter((device) => device.group_id && !device.excluded),
    [devices],
  );

  const plottedGroups = useMemo(
    () => groups.filter((group) => assigned.some((device) => device.group_id === group.group_id)),
    [groups, assigned],
  );

  const colorsByGroup = useMemo(
    () => new Map(plottedGroups.map((group, index) => [group.group_id, groupColor(index)])),
    [plottedGroups],
  );

  const bestPerGroup = useMemo(() => {
    const best = new Map<string, AnalysisDevice>();
    for (const device of assigned) {
      if (!hasMetrics(device.metrics)) {
        continue;
      }
      const current = best.get(device.group_id);
      if (
        !current ||
        (bestPce(device) ?? -Infinity) > (bestPce(current) ?? -Infinity)
      ) {
        best.set(device.group_id, device);
      }
    }
    return best;
  }, [assigned]);

  const toggleGroup = (groupId: string) => {
    setHiddenGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  const visibleGroups = plottedGroups.filter((group) => !hiddenGroups.has(group.group_id));
  const visibleIds = new Set(visibleGroups.map((group) => group.group_id));
  const selected = (
    bestOnly ? [...bestPerGroup.values()] : assigned.filter((device) => hasMetrics(device.metrics))
  ).filter((device) => visibleIds.has(device.group_id));
  const capped = selected.slice(0, MAX_OVERLAY_CURVES);
  const overCap = selected.length > MAX_OVERLAY_CURVES;

  const domainPoints = capped.flatMap((device) =>
    device.traces.filter((trace) => trace.valid).flatMap((trace) => tracePlotPoints(trace)),
  );
  const { maximum: rawXMax } = extentOf(domainPoints.map((point) => point.voltage), [0.1]);
  const { maximum: rawYMax } = extentOf(domainPoints.map((point) => point.current), [0.1]);
  const xMax = rawXMax * 1.04;
  const yMax = rawYMax * 1.08;
  const x = (value: number) => MARGIN.left + (value / xMax) * PLOT_WIDTH;
  const y = (value: number) => MARGIN.top + ((yMax - value) / yMax) * PLOT_HEIGHT;

  const series: OverlaySeries[] = capped
    .map((device) => {
      const color = colorsByGroup.get(device.group_id) ?? groupColor(0);
      const curves = device.traces
        .filter((trace) => trace.valid)
        .map((trace) => ({
          direction: trace.direction,
          dashed: trace.direction !== "forward",
          path: tracePath(tracePlotPoints(trace), x, y),
        }))
        .filter((curve) => curve.path);
      return { device, color, curves };
    })
    .filter((entry) => entry.curves.length);

  if (!assigned.length) {
    return (
      <section className="panel" aria-labelledby="jv-overlay-title">
        <div className="panel__heading">
          <h2 className="panel__title" id="jv-overlay-title">J–V comparison overlay</h2>
        </div>
        <p className="run-sheet-muted">
          Assign devices to conditions to compare their J–V curves in one chart.
        </p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="jv-overlay-title">
      <div className="panel__heading">
        <h2 className="panel__title" id="jv-overlay-title">J–V comparison overlay</h2>
        <div className="jv-overlay__controls">
          <label className="run-sheet-muted">
            <input
              type="checkbox"
              checked={bestOnly}
              onChange={(event) => setBestOnly(event.target.checked)}
            />{" "}
            Best device per group (by PCE)
          </label>
          <ChartExportButtons
            getSvg={() => document.querySelector<SVGSVGElement>("#jv-overlay-svg")}
            filename="jv-overlay"
          />
        </div>
      </div>
      <div className="jv-overlay__legend" role="list">
        {plottedGroups.map((group) => (
          <label key={group.group_id} role="listitem" className="jv-overlay__legend-item">
            <input
              type="checkbox"
              checked={!hiddenGroups.has(group.group_id)}
              onChange={() => toggleGroup(group.group_id)}
              aria-label={`Toggle group ${group.name}`}
            />
            <span
              aria-hidden="true"
              className="jv-overlay__swatch"
              style={{ backgroundColor: colorsByGroup.get(group.group_id) }}
            />
            {group.name}
          </label>
        ))}
        <span className="jv-overlay__legend-item">
          <span
            aria-hidden="true"
            className="jv-overlay__swatch jv-overlay__swatch--line"
            style={{ borderColor: FORWARD_COLOR }}
          />
          forward
        </span>
        <span className="jv-overlay__legend-item">
          <span
            aria-hidden="true"
            className="jv-overlay__swatch jv-overlay__swatch--line jv-overlay__swatch--dashed"
            style={{ borderColor: REVERSE_COLOR }}
          />
          reverse
        </span>
      </div>
      {overCap ? (
        <p className="run-sheet-muted" role="status">
          Showing the first {MAX_OVERLAY_CURVES} devices. Use “Best device per group” or hide
          groups for a clearer comparison.
        </p>
      ) : null}
      {series.length ? (
        <svg
          id="jv-overlay-svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="J-V curves of the assigned devices, colored by condition group"
        >
          <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="#fff" />
          {Array.from({ length: 6 }, (_, tick) => tick).map((tick) => {
            const xValue = (xMax * tick) / 5;
            const yValue = (yMax * tick) / 5;
            return (
              <g key={tick}>
                <line
                  x1={x(xValue)}
                  y1={MARGIN.top}
                  x2={x(xValue)}
                  y2={HEIGHT - MARGIN.bottom}
                  stroke="#f3f4f6"
                />
                <text
                  x={x(xValue)}
                  y={HEIGHT - MARGIN.bottom + 18}
                  textAnchor="middle"
                  fontSize={11}
                  fill="#4b5563"
                >
                  {formatNumber(xValue, 2)}
                </text>
                <line
                  x1={MARGIN.left}
                  y1={y(yValue)}
                  x2={WIDTH - MARGIN.right}
                  y2={y(yValue)}
                  stroke="#e5e7eb"
                />
                <text x={MARGIN.left - 8} y={y(yValue) + 4} textAnchor="end" fontSize={11} fill="#4b5563">
                  {formatNumber(yValue, 1)}
                </text>
              </g>
            );
          })}
          <line
            x1={MARGIN.left}
            y1={MARGIN.top}
            x2={MARGIN.left}
            y2={HEIGHT - MARGIN.bottom}
            stroke="#111827"
          />
          <line
            x1={MARGIN.left}
            y1={HEIGHT - MARGIN.bottom}
            x2={WIDTH - MARGIN.right}
            y2={HEIGHT - MARGIN.bottom}
            stroke="#111827"
          />
          {series.map((entry) =>
            entry.curves.map((curve) => (
              <path
                key={`${entry.device.device_id}-${curve.direction}`}
                d={curve.path}
                fill="none"
                stroke={entry.color}
                strokeWidth={2}
                strokeDasharray={curve.dashed ? "5 3" : undefined}
              >
                <title>{`${entry.device.device_id} (${entry.device.substrate_id}) ${curve.direction}`}</title>
              </path>
            )),
          )}
          <text
            x={MARGIN.left + PLOT_WIDTH / 2}
            y={HEIGHT - 10}
            textAnchor="middle"
            fontSize={13}
            fill="#111827"
          >
            Voltage (V)
          </text>
          <text
            transform={`translate(16 ${MARGIN.top + PLOT_HEIGHT / 2}) rotate(-90)`}
            textAnchor="middle"
            fontSize={13}
            fill="#111827"
          >
            Current density (mA cm⁻²)
          </text>
        </svg>
      ) : (
        <p className="run-sheet-muted">No valid traces among the selected devices.</p>
      )}
    </section>
  );
}
