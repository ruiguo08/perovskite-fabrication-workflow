import { useState } from "react";
import { exportChart, type ChartExportFormat } from "../lib/chartExport";

const FORMATS: { format: ChartExportFormat; label: string }[] = [
  { format: "svg", label: "SVG" },
  { format: "png", label: "PNG" },
  { format: "tiff", label: "TIFF" },
];

interface ChartExportButtonsProps {
  /** Resolve the chart SVG at click time (charts may render conditionally). */
  getSvg: () => SVGSVGElement | null;
  filename: string;
  /** Raster scale factor: exported pixels = SVG size x scale. */
  scale?: number;
  /** DPI metadata written into PNG (pHYs) and TIFF (resolution tags). */
  dpi?: number;
}

export function ChartExportButtons({
  getSvg,
  filename,
  scale = 3,
  dpi = 300,
}: ChartExportButtonsProps) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleExport(format: ChartExportFormat) {
    const svg = getSvg();
    if (!svg) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await exportChart(svg, format, { filename, scale, dpi });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Export failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="chart-export">
      <span className="chart-export__label">Export</span>
      {FORMATS.map(({ format, label }) => (
        <button
          key={format}
          type="button"
          className="button button--secondary button--small"
          disabled={busy}
          aria-label={`Export chart as ${label}`}
          onClick={() => void handleExport(format)}
        >
          {label}
        </button>
      ))}
      {error ? (
        <span className="chart-export__error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}
