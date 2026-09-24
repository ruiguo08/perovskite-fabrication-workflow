"""J-V curves for one device — forward and reverse scans overlaid.

Reads one device's Voltage / current-density columns straight from the
instrument CSV (the per-scan data columns, not the [Statistic] summary),
multiplies the current density by -1 (the instrument exports J with a
sign convention opposite to the plotting convention), and draws both scan
directions on shared axes.

Style follows the user's Nature reference figure: full (boxed) axes, a
solid circle marker on EVERY data point (scatter+line, not a bare line),
no metric table, and the legend at the lower-left corner inside the first
quadrant near the origin.

Device selection is by (possibly partial) CSV name stem, e.g.:
  C:/Users/r-guo/.agents/skills/vivid-figures-skill/.venv/Scripts/python.exe jv_curve.py Control1-1-2
Multiple devices can be given; each renders to its own PNG. The input
file defaults to docs/test-data/20260916.csv (--csv switches it); with
--all every device is rendered into a per-file subdirectory.
"""
import argparse
import csv
import io
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs/test-data/viz-mockups"

# colors sampled from the user's reference figure
FORWARD_COLOR = "#F08228"
REVERSE_COLOR = "#00C8C8"
AXIS_COLOR = "#000000"
NAME_RE = re.compile(r"^(?P<stem>.+)\.(?P<direction>Forward|Reverse)\(\d+\)$")


def read_scan_traces(path: Path) -> dict[str, dict[str, list[list[float]]]]:
    """Map device name stem -> direction -> [voltage, J] point list.

    J values are multiplied by -1 on read, per the plotting convention.
    """
    text = path.read_bytes().decode("gb18030")
    rows = list(csv.reader(io.StringIO(text)))
    # Structural boundary: the per-device summary table starts at its header
    # row ('No.', 'Name', 'Isc (mA)'...). Scan-point columns exist ONLY above
    # it; below, the same column positions hold summary metrics — and for
    # failed devices those values (Isc < 1.3) fall inside any physical
    # voltage window, so a value filter cannot replace this row cut.
    summary_header = next(
        (
            i
            for i, r in enumerate(rows)
            if len(r) > 2 and r[0] == "No." and r[1] == "Name" and r[2] == "Isc (mA)"
        ),
        len(rows),
    )
    data_rows = rows[:summary_header]
    traces: dict[str, dict[str, list[list[float]]]] = {}
    for base in range(0, len(rows[0]), 7):
        # Each block carries TWO 'Name' rows: the info block's (top) and the
        # [Statistic] section's. The device identity comes from the FIRST
        # one; the later one must not re-trigger collection.
        stem_dir = None
        for row in data_rows:
            if len(row) > base + 1 and row[base] == "Name":
                m = NAME_RE.match(row[base + 1] or "")
                if m:
                    stem_dir = (m.group("stem"), m.group("direction"))
                    break
        if stem_dir is None:
            continue
        stem, direction = stem_dir
        # Scan data occupies the block's V/J columns alongside the info rows
        # (parallel, not stacked): every row above the summary table holding
        # a float pair in [Volt (V)] (base+2) / [J (mA/cm^2)] (base+4) is a
        # real data point (~131 per scan, -0.1 → 1.2 V). The window check is
        # a backstop, not the boundary.
        points: list[list[float]] = []
        for row in data_rows:
            try:
                v = float(row[base + 2])
                jc = float(row[base + 4])
            except (ValueError, IndexError):
                continue
            if -0.3 <= v <= 1.3:
                points.append([v, -jc])
        if points:
            traces.setdefault(stem, {})[direction] = points
    return traces


def render(stem: str, traces: dict[str, list[list[float]]], out_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(4.3, 3.55), dpi=200)
    fig.patch.set_facecolor("white")

    # axes frame on all four sides, ticks outside, like the reference
    for side in ax.spines.values():
        side.set_linewidth(1.0)
        side.set_color(AXIS_COLOR)
    ax.tick_params(direction="out", length=4, width=1.0, colors=AXIS_COLOR,
                   labelsize=9)

    for direction, color in (("Forward", FORWARD_COLOR), ("Reverse", REVERSE_COLOR)):
        points = sorted(traces.get(direction, []))
        if not points:
            continue
        vs = [p[0] for p in points]
        js = [p[1] for p in points]
        # Nature-style beaded curve: thin connecting line + a solid circle
        # marker on EVERY data point (131 per scan for this instrument)
        ax.plot(vs, js, color=color, linewidth=1.0, zorder=2)
        ax.plot(vs, js, "o", color=color, markersize=2.6,
                markeredgecolor=color, linestyle="none", zorder=3)

    ymax = max(p[1] for pts in traces.values() for p in pts)
    ax.set_xlim(0.0, 1.25)
    ax.set_ylim(0.0, math.ceil(ymax / 5) * 5)
    ax.set_xlabel("Voltage (V)", fontsize=11)
    ax.set_ylabel(r"Current density (mA cm$^{-2}$)", fontsize=11)

    # legend inside lower-left, near the origin (first quadrant), no frame
    handles = [
        Line2D([], [], color=FORWARD_COLOR, marker="o", markersize=3.2,
               markeredgecolor=FORWARD_COLOR, linewidth=1.0, label="Forward"),
        Line2D([], [], color=REVERSE_COLOR, marker="o", markersize=3.2,
               markeredgecolor=REVERSE_COLOR, linewidth=1.0, label="Reverse"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=10,
              handletextpad=0.4, borderaxespad=0.4)

    fig.tight_layout()
    out = out_dir / f"jv_curve_{stem.replace('.', '_').replace('-', '_')}.png"
    fig.savefig(out, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("devices", nargs="*", help="device name stems (prefix match)")
    parser.add_argument("--csv", default="docs/test-data/20260916.csv",
                        help="instrument export CSV path")
    parser.add_argument("--all", action="store_true",
                        help="render every device in the file")
    parser.add_argument("--out", default=None,
                        help="output directory (default: per-file subdirectory)")
    args = parser.parse_args()

    path = ROOT / args.csv if not Path(args.csv).is_absolute() else Path(args.csv)
    all_traces = read_scan_traces(path)
    out_dir = (Path(args.out) if args.out else
               OUT / f"jv-curves-{path.stem}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"file: {path.name}  devices: {len(all_traces)}  out: {out_dir}")

    stems = list(all_traces) if args.all else (args.devices or ["Control1-1-2"])
    saved = 0
    for stem in stems:
        matches = [s for s in all_traces if s == stem] or [
            s for s in all_traces if s.startswith(stem)
        ]
        if not matches:
            print(f"device {stem!r} not found ({len(all_traces)} devices available)")
            continue
        for full in matches:
            render(full, all_traces[full], out_dir)
            saved += 1
    print(f"rendered {saved} J-V figures")


if __name__ == "__main__":
    main()
