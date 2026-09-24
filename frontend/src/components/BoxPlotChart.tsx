import { useRef } from "react";
import type { AnalysisDevice, AnalysisStatistics, AnalysisGroupStat } from "../types/api";
import { formatNumber } from "../lib/format";
import { groupColor } from "../lib/jvPlot";
import { descriptiveStatistics } from "../lib/stats";
import { ChartExportButtons } from "./ChartExportButtons";
import { extentOf } from "../lib/extent";
import { hasMetrics, pooledMetric } from "../lib/deviceMetrics";

const METRIC_META: Record<string, { label: string; scale: number; digits: number }> = {
  voc: { label: "Voc (V)", scale: 1, digits: 2 },
  jsc: { label: "Jsc (mA cm⁻²)", scale: 1, digits: 1 },
  ff: { label: "FF (%)", scale: 100, digits: 1 },
  pce: { label: "PCE (%)", scale: 1, digits: 1 },
};

interface BoxValues {
  n: number;
  mean: number | null;
  median: number | null;
  minimum: number | null;
  q1: number | null;
  q3: number | null;
  maximum: number | null;
}

interface PlotBox {
  key: string;
  label: string;
  color: string;
  /** Reverse-scan boxes get a dashed outline. */
  dashed: boolean;
  values: BoxValues;
  jitter: { device_id: string; value: number }[];
}

interface BoxPlotChartProps {
  metric: "voc" | "jsc" | "ff" | "pce";
  statistics: AnalysisStatistics;
  devices: AnalysisDevice[];
  /** Split every condition into forward/reverse boxes from trace metrics. */
  splitByDirection?: boolean;
}

function finiteScaled(value: number | null | undefined, scale: number): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return value * scale;
}

export function BoxPlotChart({
  metric,
  statistics,
  devices,
  splitByDirection = false,
}: BoxPlotChartProps) {
  const figureRef = useRef<HTMLDivElement | null>(null);
  const meta = METRIC_META[metric];

  const groups: AnalysisGroupStat[] = (statistics.groups ?? []).filter((group) =>
    splitByDirection
      ? devices.some(
          (device) =>
            device.group_id === group.group_id &&
            !device.excluded &&
            (device.traces ?? []).some((trace) => trace.valid && trace.metrics),
        )
      : (group.metrics?.[metric]?.n ?? 0) > 0,
  );

  if (!groups.length) {
    return <p className="run-sheet-muted">No valid assigned devices for this metric.</p>;
  }

  const boxes: PlotBox[] = [];
  for (const [groupIndex, group] of groups.entries()) {
    const color = groupColor(groupIndex);
    const groupDevices = devices.filter(
      (device) => device.group_id === group.group_id && hasMetrics(device.metrics) && !device.excluded,
    );
    if (splitByDirection) {
      for (const direction of ["forward", "reverse"] as const) {
        const values: number[] = [];
        const jitter: { device_id: string; value: number }[] = [];
        for (const device of groupDevices) {
          for (const trace of device.traces ?? []) {
            if (!trace.valid || !trace.metrics || trace.direction !== direction) {
              continue;
            }
            const value = finiteScaled(trace.metrics[metric], meta.scale);
            if (value === null) {
              continue;
            }
            values.push(value);
            jitter.push({ device_id: device.device_id, value });
          }
        }
        if (!values.length) {
          continue;
        }
        const stats = descriptiveStatistics(values);
        boxes.push({
          key: `${group.group_id}-${direction}`,
          label: `${group.name} ${direction === "forward" ? "F" : "R"}`,
          color,
          dashed: direction === "reverse",
          values: stats,
          jitter,
        });
      }
    } else {
      const stats = group.metrics[metric];
      if (!stats || stats.n === 0) {
        continue;
      }
      const jitter = groupDevices
        .map((device) => ({
          device_id: device.device_id,
          value: finiteScaled(pooledMetric(device.metrics, metric), meta.scale),
        }))
        .filter((point): point is { device_id: string; value: number } => point.value !== null);
      boxes.push({
        key: group.group_id,
        label: group.name,
        color,
        dashed: false,
        values: {
          n: stats.n,
          mean: finiteScaled(stats.mean, meta.scale),
          median: finiteScaled(stats.median, meta.scale),
          minimum: finiteScaled(stats.minimum, meta.scale),
          q1: finiteScaled(stats.q1, meta.scale),
          q3: finiteScaled(stats.q3, meta.scale),
          maximum: finiteScaled(stats.maximum, meta.scale),
        },
        jitter,
      });
    }
  }

  if (!boxes.length) {
    return <p className="run-sheet-muted">No valid assigned devices for this metric.</p>;
  }

  const scaledDeviceValues = devices
    .filter((device) => device.group_id && hasMetrics(device.metrics) && !device.excluded)
    .map((device) => finiteScaled(pooledMetric(device.metrics, metric), meta.scale))
    .filter((value): value is number => value !== null);
  // Fall back to finite plotted values (device metrics, split-mode trace
  // values, or server-provided bounds) so the axis never sees NaN/Infinity.
  const statBounds = boxes
    .flatMap((box) => [box.values.minimum, box.values.maximum])
    .filter((value): value is number => value !== null);
  const extent = extentOf(scaledDeviceValues, statBounds);
  let minimum = extent.minimum;
  let maximum = extent.maximum;
  if (!Number.isFinite(minimum) || !Number.isFinite(maximum)) {
    minimum = 0;
    maximum = 1;
  }
  const rawRange = maximum - minimum;
  const padding = rawRange > 0 ? rawRange * 0.12 : Math.max(Math.abs(maximum) * 0.1, 1);
  minimum -= padding;
  maximum += padding;

  const width = 560;
  const height = 310;
  const margin = { top: 22, right: 18, bottom: 62, left: 62 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const y = (value: number) => margin.top + ((maximum - value) / (maximum - minimum)) * plotHeight;
  const xStep = plotWidth / boxes.length;

  return (
    <div ref={figureRef}>
      <figure className="boxplot-figure">
        <figcaption className="boxplot-figure__caption">
          <strong>{meta.label}</strong>
          <ChartExportButtons
            getSvg={() => figureRef.current?.querySelector("svg") ?? null}
            filename={`boxplot-${metric}${splitByDirection ? "-by-direction" : ""}`}
          />
        </figcaption>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${meta.label} by group`}>
        <rect x={0} y={0} width={width} height={height} fill="#fff" />
        {Array.from({ length: 6 }, (_, tick) => tick).map((tick) => {
          const value = minimum + ((maximum - minimum) * tick) / 5;
          const tickY = y(value);
          return (
            <g key={tick}>
              <line x1={margin.left} y1={tickY} x2={width - margin.right} y2={tickY} stroke="#e5e7eb" />
              <text x={margin.left - 8} y={tickY + 4} textAnchor="end" fontSize={11} fill="#4b5563">
                {formatNumber(value, meta.digits)}
              </text>
            </g>
          );
        })}
        <line x1={margin.left} y1={margin.top} x2={margin.left} y2={height - margin.bottom} stroke="#374151" />
        <line x1={margin.left} y1={height - margin.bottom} x2={width - margin.right} y2={height - margin.bottom} stroke="#374151" />
        {boxes.map((box, boxIndex) => {
          const centerX = margin.left + xStep * (boxIndex + 0.5);
          const boxWidth = Math.min(54, xStep * 0.44);
          const { values } = box;
          const shortName = box.label.length > 18 ? box.label.slice(0, 17) + "…" : box.label;
          return (
            <g key={box.key}>
              {values.minimum !== null && values.maximum !== null && (
                <line
                  x1={centerX}
                  y1={y(values.minimum)}
                  x2={centerX}
                  y2={y(values.maximum)}
                  stroke={box.color}
                  strokeWidth={2}
                />
              )}
              {values.minimum !== null && (
                <line
                  x1={centerX - boxWidth / 3}
                  y1={y(values.minimum)}
                  x2={centerX + boxWidth / 3}
                  y2={y(values.minimum)}
                  stroke={box.color}
                  strokeWidth={2}
                />
              )}
              {values.maximum !== null && (
                <line
                  x1={centerX - boxWidth / 3}
                  y1={y(values.maximum)}
                  x2={centerX + boxWidth / 3}
                  y2={y(values.maximum)}
                  stroke={box.color}
                  strokeWidth={2}
                />
              )}
              {values.q1 !== null && values.q3 !== null && (
                <rect
                  x={centerX - boxWidth / 2}
                  y={y(values.q3)}
                  width={boxWidth}
                  height={Math.max(1, y(values.q1) - y(values.q3))}
                  fill={box.color}
                  fillOpacity={0.18}
                  stroke={box.color}
                  strokeWidth={2}
                  strokeDasharray={box.dashed ? "4 2" : undefined}
                />
              )}
              {values.median !== null && (
                <line
                  x1={centerX - boxWidth / 2}
                  y1={y(values.median)}
                  x2={centerX + boxWidth / 2}
                  y2={y(values.median)}
                  stroke={box.color}
                  strokeWidth={3}
                />
              )}
              {values.mean !== null && (
                <circle cx={centerX} cy={y(values.mean)} r={4} fill="#fff" stroke="#111827" strokeWidth={1.5}>
                  <title>Mean {formatNumber(values.mean, 3)}</title>
                </circle>
              )}
              {box.jitter.map((point, pointIndex) => {
                const jitter = ((pointIndex * 37) % 23 - 11) * Math.min(1.3, boxWidth / 35);
                return (
                  <circle
                    key={`${point.device_id}-${pointIndex}`}
                    cx={centerX + jitter}
                    cy={y(point.value)}
                    r={3.2}
                    fill={box.color}
                    fillOpacity={0.78}
                    stroke="#fff"
                  >
                    <title>{`${point.device_id}: ${formatNumber(point.value, 3)}`}</title>
                  </circle>
                );
              })}
              <text x={centerX} y={height - margin.bottom + 22} textAnchor="middle" fontSize={12} fontWeight={600} fill="#111827">
                {shortName}
              </text>
              <text x={centerX} y={height - margin.bottom + 39} textAnchor="middle" fontSize={11} fill="#6b7280">
                {`n=${box.values.n}`}
              </text>
            </g>
          );
        })}
        <text transform={`translate(15 ${margin.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill="#374151">
          {meta.label}
        </text>
        </svg>
        {splitByDirection ? (
          <p className="run-sheet-muted boxplot-figure__note">
            F = forward scan, R = reverse scan; boxes are computed from trace-level metrics.
          </p>
        ) : null}
      </figure>
    </div>
  );
}
