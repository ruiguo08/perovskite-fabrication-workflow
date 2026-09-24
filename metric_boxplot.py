"""Metric box plots with bee-swarm overlay, grouped by condition.

Per CSV file: for each metric (Voc, Jsc, FF, PCE) one figure; the x-axis
holds one box-pair per condition (Control, T1, ...), the pair being the
forward-scan and reverse-scan distributions of that condition's devices.
Every individual scan is overlaid as a swarm dot (colored by direction,
grouped beside its box), so the raw data is always visible on top of the
summary statistics — the style of the user's reference figure.

Sample policy (schema 6): each scan direction is an independent sample,
exactly like the pooled statistics. Device-level values are never
pre-averaged.

Usage:
  C:/Users/r-guo/.agents/skills/vivid-figures-skill/.venv/Scripts/python.exe metric_boxplot.py [csv-path] [METRIC ...]
"""
import csv
import io
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "docs/test-data/20260916.csv"
OUT = ROOT / "docs/test-data/viz-mockups"

# direction colors match the J-V curve figures (and the web app's
# FORWARD_COLOR/REVERSE_COLOR convention) so every figure reads the same
# way: orange = forward scan, teal = reverse scan.
FORWARD_COLOR = "#F08228"   # forward scans
REVERSE_COLOR = "#00C8C8"   # reverse scans

STAT_LABELS = {
    "Voc (V)": "voc",
    "Efficiency (%)": "pce",
    "Fill Factor (%)": "ff",
    "Jsc (mA/cm^2)": "jsc",
}
NAME_RE = re.compile(r"^(?P<stem>.+)\.(?P<direction>Forward|Reverse)\(\d+\)$")

METRICS = {
    "Voc": ("voc", "V", 3),
    "Jsc": ("jsc", "mA/cm²", 1),
    "FF": ("ff", "%", 1),
    "PCE": ("pce", "%", 1),
}


def read_scan_stats(path: Path) -> list[dict]:
    """One record per SCAN (device x direction) from the summary table.

    The trailing per-scan table (No., Name, Isc (mA), Voc (V), ...) is
    located by header signature, never by row number. Each row yields
    {name, condition, substrate, pos, direction, voc, jsc, ff, pce}.
    """
    text = path.read_bytes().decode("gb18030")
    rows = list(csv.reader(io.StringIO(text)))
    hdr = next(
        i
        for i, r in enumerate(rows)
        if len(r) > 2 and r[0].strip() == "No." and r[1].strip() == "Name" and r[2] == "Isc (mA)"
    )
    cols = {c.strip(): i for i, c in enumerate(rows[hdr]) if c.strip()}
    records = []
    for r in rows[hdr + 1:]:
        if len(r) < len(cols):
            continue
        m = NAME_RE.match(r[cols["Name"]].strip())
        if not m:
            continue
        stem = m.group("stem")
        parts = stem.split(".")[0].split("-")
        if len(parts) < 3 or not parts[-2].isdigit() or not parts[-1].isdigit():
            continue  # naming rule TBD; skip anything unparseable
        values = {}
        for label, name in STAT_LABELS.items():
            try:
                values[name] = float(r[cols[label]])
            except (KeyError, ValueError):
                values = {}
                break
        if not values:
            continue
        rec = {
            "name": stem,
            "condition": "-".join(parts[:-2]),
            "substrate": int(parts[-2]),
            "pos": int(parts[-1]),
            "direction": m.group("direction").lower(),
        }
        rec.update(values)
        records.append(rec)
    return records


def swarm_offsets(values: list[float], width: float, *, y_spacing: float) -> list[float]:
    """Pack circles without changing y values; spacings are marker diameters.

    The renderer converts the marker diameter from display pixels into x/y
    data units after finalizing the axes. Tangent candidates therefore account
    for both horizontal and vertical separation, irrespective of metric units.
    """
    if width <= 0 or y_spacing <= 0:
        raise ValueError("Marker spacings must be positive")
    offsets = [0.0] * len(values)
    placed: list[tuple[float, float]] = []
    for idx in sorted(range(len(values)), key=lambda i: values[i]):
        value = values[idx]
        neighbors = [(x, y) for x, y in placed if abs(value - y) < y_spacing]
        candidates = [0.0]
        for x, y in neighbors:
            dx = width * np.sqrt(max(0.0, 1 - ((value - y) / y_spacing) ** 2))
            candidates.extend((x - dx, x + dx))
        for candidate in sorted(candidates, key=lambda x: (abs(x), x)):
            if all(((candidate - x) / width) ** 2 +
                   ((value - y) / y_spacing) ** 2 >= 1 - 1e-9
                   for x, y in neighbors):
                offsets[idx] = float(candidate)
                break
        placed.append((offsets[idx], value))
    return offsets


def render(metric: str, records: list[dict], out_dir: Path, source: str) -> Path | None:
    key, unit, digits = METRICS[metric]

    # conditions in first-appearance order (Control first, then T1, T2, ...)
    conds: list[str] = []
    for rec in records:
        if rec["condition"] not in conds:
            conds.append(rec["condition"])

    # per condition x positions: pair of boxes (forward, reverse)
    positions = {(cond, direction): i + offset
                 for i, cond in enumerate(conds)
                 for direction, offset in (("forward", -0.2), ("reverse", 0.2))}

    fig, ax = plt.subplots(figsize=(1.5 + 1.5 * len(conds), 3.8), dpi=200)

    swarms = []
    tick_centers = []
    tick_labels = []
    for cond in conds:
        for direction, color in (
            ("forward", FORWARD_COLOR),
            ("reverse", REVERSE_COLOR),
        ):
            values = [
                rec[key] for rec in records
                if rec["condition"] == cond and rec["direction"] == direction
            ]
            if not values:
                continue
            pos = positions[(cond, direction)]
            bp = ax.boxplot(
                [values],
                positions=[pos],
                widths=0.34,
                patch_artist=True,
                showfliers=False,  # swarm shows every point; box whiskers cover the rest
                medianprops=dict(color="#333333", linewidth=1.4),
                whiskerprops=dict(color="#555555", linewidth=1.0),
                capprops=dict(color="#555555", linewidth=1.0),
                boxprops=dict(facecolor=color, alpha=0.25, edgecolor=color, linewidth=1.2),
            )
            # mean marker: open diamond, like the reference
            ax.plot(
                [pos], [np.mean(values)], "D",
                markerfacecolor="white", markeredgecolor="#222222",
                markersize=4.5, zorder=5,
            )
            swarms.append((pos, values, color))
        tick_centers.append(sum(positions[(cond, d)] for d in ("forward", "reverse")) / 2)
        tick_labels.append(cond)

    ax.set_xticks(tick_centers)
    ax.set_xticklabels(tick_labels, fontsize=10)
    ax.set_ylabel(f"{metric} ({unit})", fontsize=11)
    ax.set_xlabel("Condition", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.margins(x=0.06)

    # direction legend (top-left, no frame)
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], color=FORWARD_COLOR, marker="o", markersize=4,
               markeredgecolor=FORWARD_COLOR, linewidth=0, label="Forward scan"),
        Line2D([], [], color=REVERSE_COLOR, marker="o", markersize=4,
               markeredgecolor=REVERSE_COLOR, linewidth=0, label="Reverse scan"),
        Line2D([], [], color="#222222", marker="D", markersize=4.5,
               markerfacecolor="white", markeredgecolor="#222222", linewidth=0,
               label="Mean"),
    ]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=3, frameon=False, fontsize=8.5,
              handletextpad=0.3, borderaxespad=0.3)
    n = len(records)
    ax.set_title(f"{metric} by condition — {source} ({n} scans)", fontsize=11, pad=36)

    fig.tight_layout()
    fig.canvas.draw()
    # Freeze limits before adding scatter so the pixel-to-data scale stays fixed.
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    diameter_px = (3.4 + 0.6) * fig.dpi / 72
    origin = ax.transData.inverted().transform((0, 0))
    delta = ax.transData.inverted().transform((diameter_px, diameter_px)) - origin
    for pos, values, color in swarms:
        offsets = swarm_offsets(values, abs(delta[0]), y_spacing=abs(delta[1]))
        ax.plot([pos + offset for offset in offsets], values, "o", color=color,
                markersize=3.4, markeredgewidth=0.4, alpha=0.85,
                linestyle="none", zorder=4)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"metric_boxplot_{metric.lower()}.png"
    fig.savefig(out, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    args = sys.argv[1:]
    csv_path = RAW
    if args and (args[0].endswith(".csv") or "/" in args[0] or "\\" in args[0]):
        csv_path = ROOT / args[0] if not Path(args[0]).is_absolute() else Path(args[0])
        args = args[1:]
    metrics = [m for m in (args or ["Voc", "Jsc", "FF", "PCE"]) if m in METRICS]
    out_dir = OUT / f"boxplots-{csv_path.stem}"
    out_dir.mkdir(parents=True, exist_ok=True)

    records = read_scan_stats(csv_path)
    n_conditions = len({r["condition"] for r in records})
    print(f"file: {csv_path.name}  scans: {len(records)}  conditions: {n_conditions}")
    for metric in metrics:
        out = render(metric, records, out_dir, csv_path.stem)
        if out:
            print("saved", out)


if __name__ == "__main__":
    main()
