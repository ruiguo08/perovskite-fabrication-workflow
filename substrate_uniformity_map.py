"""Substrate uniformity map — square cells, one row per condition.

One mini-panel per substrate: a square substrate outline containing the 6
devices as a tight 2-cols x 3-rows grid of colored squares (left column
channels 1/2/3 top-to-bottom, right column 4/5/6). Rows of the figure are
conditions (Control1, Control2, T1, ... — one condition per figure row,
its substrates left-to-right in numeric order); the panel title is the
substrate number.

Metric values are read directly from the instrument's [Statistic] rows of
the CSV export — no curve re-analysis. Each device has Forward and Reverse
scan statistics, rendered in separate figures with a shared color scale.
No cross-direction averaging is performed. Device names are
kept verbatim from the CSV (e.g. 'Control1-1-1.CH_Ref').

Run with the vivid-figures-skill venv python (matplotlib+numpy):
  C:/Users/r-guo/.agents/skills/vivid-figures-skill/.venv/Scripts/python.exe substrate_uniformity_map.py [METRIC] [CMAP1,CMAP2]
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
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "docs/test-data/20260916.csv"
OUT = ROOT / "docs/test-data/viz-mockups"

STAT_LABELS = {
    "Voc (V)": "voc",
    "Efficiency (%)": "pce",
    "Fill Factor (%)": "ff",
    "Jsc (mA/cm^2)": "jsc",
}
NAME_RE = re.compile(r"^(?P<stem>.+)\.(?P<direction>Forward|Reverse)\(\d+\)$")


def read_device_stats(path: Path = None) -> list[dict]:
    """One record per device, straight from the CSV [Statistic] rows.

    The export is a wide table: each scan (device x direction) occupies a
    7-column block with a [Statistic] section (rows 'Name', 'Voc (V)',
    'Efficiency (%)', ...). Returns records with the verbatim device name
    stem from the CSV (e.g. 'Control1-1-1.CH_Ref') and raw per-direction
    values. Devices with only one direction are retained.
    """
    text = (path or RAW).read_bytes().decode("gb18030")
    rows = list(csv.reader(io.StringIO(text)))
    scans: dict[str, dict] = {}
    for base in range(0, len(rows[0]), 7):
        for i, row in enumerate(rows):
            if len(row) <= base + 1 or row[base] != "Name":
                continue
            # the [Statistic] name row sits two rows above 'Voc (V)'
            if (
                i + 2 >= len(rows)
                or len(rows[i + 2]) <= base
                or rows[i + 2][base] != "Voc (V)"
            ):
                continue
            m = NAME_RE.match(row[base + 1] or "")
            if not m:
                continue
            values: dict[str, float] = {}
            for j in range(i + 2, min(i + 13, len(rows))):
                label = rows[j][base] if len(rows[j]) > base else ""
                if label in STAT_LABELS and len(rows[j]) > base + 1:
                    try:
                        values[STAT_LABELS[label]] = float(rows[j][base + 1])
                    except ValueError:
                        pass
            if len(values) != len(STAT_LABELS):
                continue
            stem, direction = m.group("stem"), m.group("direction")
            parts = stem.split(".")[0].split("-")
            if len(parts) < 3 or not parts[-2].isdigit() or not parts[-1].isdigit():
                continue  # naming rule TBD; skip anything unparseable
            entry = scans.setdefault(
                stem,
                {"ident": ("-".join(parts[:-2]), int(parts[-2]), int(parts[-1]))},
            )
            entry[direction] = values

    records = []
    for stem, entry in scans.items():
        condition, substrate, pos = entry["ident"]
        rec: dict = {
            "name": stem,
            "group": condition,
            "substrate": substrate,
            "pos": pos,
            "forward": entry.get("Forward"),
            "reverse": entry.get("Reverse"),
        }
        records.append(rec)
    return records


METRICS = {
    "PCE": ("pce", "%", 1),
    "Voc": ("voc", "V", 3),
    "Jsc": ("jsc", "mA/cm²", 1),
    "FF": ("ff", "%", 1),
}
# channel -> (column 0/1, row-from-top 0..2); left col ch 1..3, right col ch 4..6
CELL = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}

# global color scale across ALL substrates (0.0 stays in the scale)
CMAPS = {
    "viridis": plt.get_cmap("viridis"),
    "nature_warm": matplotlib.colors.LinearSegmentedColormap.from_list(
        "nature_warm",
        ["#E64B35", "#E87A5D", "#F2A583", "#F7C6A3", "#E8D3C5", "#4D4D4D"],
    ),
    "rdylgn": plt.get_cmap("RdYlGn"),
    # rainbow, user-customized direction: red = bad (low), blue = good (high).
    # Built by reversing the builtin rainbow and capping the violet tail at
    # a clear deep blue so "good" always reads as blue, never purple.
    "rainbow": matplotlib.colors.LinearSegmentedColormap.from_list(
        "rainbow_rb",
        [plt.get_cmap("rainbow")(1.0 - f) for f in np.linspace(0.0, 0.82, 7)] + ["#0048E0"],
    ),
}


def _text_color(cmap_name: str, frac: float) -> str:
    if cmap_name == "viridis":
        return "white" if frac > 0.55 else "#222222"
    if cmap_name == "nature_warm":  # light middle, dark gray tail
        return "white" if (frac < 0.12 or frac > 0.92) else "#222222"
    # rdylgn: dark red / dark green ends, light yellow middle
    if cmap_name == "rdylgn":
        return "white" if (frac < 0.12 or frac > 0.85) else "#222222"
    # rainbow (red=low → blue=high): dark red low end, dark blue high end,
    # bright green-yellow middle
    return "white" if (frac < 0.10 or frac > 0.88) else "#222222"


def render(metric: str, cmap_name: str, records: list[dict], out_dir: Path = OUT,
           *, direction: str) -> Path:
    key, unit, digits = METRICS[metric]
    if direction not in ("forward", "reverse"):
        raise ValueError("Choose forward or reverse")
    # Use both directions for the scale only, never for the displayed values.
    vals = np.array([r[d][key] for r in records for d in ("forward", "reverse")
                     if r.get(d) is not None])
    if not vals.size:
        raise ValueError("No scan metrics available")
    vmin, vmax = float(vals.min()), float(vals.max())
    cmap = CMAPS[cmap_name]
    norm = matplotlib.colors.Normalize(vmin, vmax)

    by_cond: dict[str, dict[int, list[dict]]] = {}
    for r in records:
        by_cond.setdefault(r["group"], {}).setdefault(r["substrate"], []).append(r)
    conds = list(by_cond)  # CSV appearance order: Control1, Control2, T1, ...
    n_rows = len(conds)
    n_cols = max(len(subs) for subs in by_cond.values())

    # geometry: tight 2x3 cell grid centered in a square substrate outline
    S, G, M = 1.0, 0.22, 0.30  # cell side, gap, outline margin
    cluster_w, cluster_h = 2 * S + G, 3 * S + 2 * G
    L = cluster_h + 2 * M  # square outline side
    off_x = (L - cluster_w) / 2

    PW = 1.62  # inches per square panel
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(n_cols * PW + 1.7, n_rows * PW + 0.9), squeeze=False
    )
    fig.subplots_adjust(left=0.075, right=0.93, top=0.92, bottom=0.02, wspace=0.10, hspace=0.28)

    for ri, cond in enumerate(conds):
        subs = sorted(by_cond[cond])
        for ci in range(n_cols):
            ax = axes[ri][ci]
            if ci >= len(subs):
                ax.set_visible(False)
                continue
            ax.set_xlim(-0.18, L + 0.18)
            ax.set_ylim(-0.18, L + 0.18)
            ax.set_aspect("equal")
            ax.axis("off")
            ax.add_patch(
                Rectangle((0, 0), L, L, fill=False, edgecolor="#c8c8c8", linewidth=1.1)
            )
            cells = {r["pos"]: r for r in by_cond[cond][subs[ci]]}
            for ch, (c, t) in CELL.items():
                rec = cells.get(ch)
                if rec is None or rec.get(direction) is None:
                    continue
                v = rec[direction][key]
                x = off_x + c * (S + G)
                y = M + (2 - t) * (S + G)  # top row of the grid first
                ax.add_patch(
                    Rectangle(
                        (x, y), S, S,
                        facecolor=cmap(norm(v)), edgecolor="#444444", linewidth=0.8,
                    )
                )
                frac = (v - vmin) / max(vmax - vmin, 1e-12)
                ax.text(x + S / 2, y + S / 2, f"{v:.{digits}f}", ha="center",
                        va="center", fontsize=7.8, color=_text_color(cmap_name, frac))
            ax.set_title(str(subs[ci]), fontsize=10, pad=3)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes.ravel().tolist(), shrink=0.45, pad=0.03)
    cbar.set_label(f"{metric} ({unit})")

    # row labels (condition names) placed after the colorbar's final layout
    for ri, cond in enumerate(conds):
        pos = axes[ri][0].get_position()
        fig.text(0.025, (pos.y0 + pos.y1) / 2, cond, rotation=90, ha="center",
                 va="center", fontsize=11, fontweight="bold", color="#333333")

    fig.suptitle(f"Substrate uniformity — {direction.capitalize()} scan {metric}", fontsize=12)
    fig.text(
        0.5, 0.945,
        "rows = conditions · panel number = substrate · per substrate: 2 cols × 3 rows "
        "(left ch 1-3, right ch 4-6, top→bottom) · shared F/R color scale",
        ha="center", fontsize=8.5, color="#555555",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"substrate_uniformity_{metric.lower()}_{direction}_{cmap_name}.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print("saved", out, f"range=[{vmin:.3f}, {vmax:.3f}]")
    return out


if __name__ == "__main__":
    # usage: substrate_uniformity_map.py [csv-path] [METRIC] [CMAP1,CMAP2]
    args = [a for a in sys.argv[1:]]
    csv_path = RAW
    out_dir = OUT
    if args and (args[0].endswith(".csv") or "/" in args[0] or "\\" in args[0]):
        csv_path = ROOT / args[0] if not Path(args[0]).is_absolute() else Path(args[0])
        out_dir = OUT / f"uniformity-{csv_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        args = args[1:]
    records = read_device_stats(csv_path)
    n_subs = len({(r["group"], r["substrate"]) for r in records})
    print(f"file: {csv_path.name}  devices: {len(records)}  substrates: {n_subs}")
    metric = args[0] if args else "PCE"
    cmaps = args[1].split(",") if len(args) > 1 else ["rdylgn"]
    for cm in cmaps:
        for direction in ("forward", "reverse"):
            render(metric, cm, records, out_dir, direction=direction)
