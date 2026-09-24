"""Publication-quality Matplotlib figures for persisted J-V analyses.

The renderers consume the normalized analysis JSON stored with a result file.
They never parse the source CSV again, so previews, downloads, assignments,
exclusions, and representative-scan selection all share one source of truth.
"""

from __future__ import annotations

import io
import json
import math
import os
import statistics
import tempfile
import threading
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any, Literal

# Server processes may run with a read-only home directory. Keep Matplotlib's
# font cache in the OS temporary area rather than making rendering depend on a
# writable user profile.
_MPL_CONFIG_DIR = os.path.join(tempfile.gettempdir(), "perovskite-matplotlib")
os.makedirs(_MPL_CONFIG_DIR, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", _MPL_CONFIG_DIR)
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    from matplotlib.colors import LinearSegmentedColormap, to_rgb
except ModuleNotFoundError:  # lets the app report a focused 503 before dependencies are synced
    matplotlib = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]

FigureKind = Literal["jv", "boxplot", "uniformity"]
FigureFormat = Literal["svg", "pdf", "tiff"]

FORWARD_COLOR = "#F08228"
REVERSE_COLOR = "#00C8C8"
# Tracked copies of the sets in docs/test-data/viz-palettes.md. That source
# document is intentionally ignored by Git, so rendering cannot read it.
CATEGORICAL_PALETTES = {
    "nature-classic": ("#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F"),
    "science-tol": ("#4477AA", "#66CCEE", "#228833", "#CCBB44", "#EE6677", "#AA3377", "#BBBBBB"),
    "lancet-clinical": ("#00468B", "#ED0000", "#42B540", "#0099B4", "#925E9F", "#FDAF91", "#AD002A", "#ADB6B6"),
    "nejm": ("#BC3C29", "#0072B5", "#E18727", "#20854E", "#7876B1", "#6F99AD", "#FFDC91", "#EE4C97"),
}
GRADIENT_PALETTES = {
    "nature-warm": ("#E64B35", "#E87A5D", "#F2A583", "#F7C6A3", "#E8D3C5", "#4D4D4D"),
    "science-purple": ("#332288", "#6A51A3", "#9E8AC4", "#CBC1E0", "#EAE6F2", "#4D4D4D"),
    "lancet-blue": ("#00468B", "#1C75BC", "#4DA3D9", "#8CC6E8", "#C9E2F2"),
    "nejm-red": ("#BC3C29", "#D9534F", "#E87A6C", "#F2A593", "#F7C6B8", "#FAE3D9"),
    "cell-blue": ("#1F77B4", "#4A9BD1", "#7FBDE3", "#B4D8EF", "#E1EEF7"),
    "wong-orange": ("#E69F00", "#F0B429", "#F5C95A", "#F9DE96", "#FCEFC4"),
    "viridis": ("#440154", "#3B528B", "#21918C", "#5DC863", "#B8DE29", "#FDE725"),
    "red-blue": ("#B2182B", "#EF8A62", "#FDDBC7", "#FFFFFF", "#D1E5F0", "#67A9CF", "#2166AC"),
    "medical-gray": ("#666666", "#999999", "#B3B3B3", "#CCCCCC", "#E6E6E6"),
    "rdylgn": ("#A50026", "#D73027", "#F46D43", "#FDAE61", "#FEE08B", "#D9EF8B", "#A6D96A", "#66BD63", "#1A9850", "#006837"),
    "rainbow": ("#E60000", "#FF6A38", "#F0C46E", "#8AF7AE", "#29D9DD", "#1B7DF2", "#0048E0"),
}
METRICS = {
    "voc": ("Voc", "V", 1.0, 3),
    "jsc": ("Jsc", r"mA cm$^{-2}$", 1.0, 2),
    "ff": ("FF", "%", 100.0, 1),
    "pce": ("PCE", "%", 1.0, 1),
}
MEDIA_TYPES = {
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "tiff": "image/tiff",
}
_FORMAT_SUFFIX = {"svg": "svg", "pdf": "pdf", "tiff": "tiff"}
_MATPLOTLIB_LOCK = threading.Lock()
_CELL_POSITION = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2)}

_RC = {
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.labelsize": 9,
    "axes.titlesize": 9,
    "axes.linewidth": 0.8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "legend.fontsize": 7.5,
    "lines.linewidth": 1.1,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.facecolor": "white",
    "figure.facecolor": "white",
}


class PlotInputError(ValueError):
    """The requested plot cannot be produced from the selected data."""


class PlotUnavailableError(RuntimeError):
    """The deployment does not have the declared plotting runtime installed."""


def figure_filename(kind: FigureKind, metric: str | None, figure_format: FigureFormat) -> str:
    qualifier = f"-{metric}" if metric else ""
    return f"{kind}{qualifier}.{_FORMAT_SUFFIX[figure_format]}"


def render_publication_figure(
    analysis: Mapping[str, Any],
    groups: Sequence[Mapping[str, Any]],
    *,
    kind: FigureKind,
    figure_format: FigureFormat = "svg",
    metric: str | None = None,
    device_ids: Sequence[str] = (),
    excluded_device_ids: Sequence[str] | None = None,
    direction: str = "forward",
    palette: str | None = None,
    scale_min: float | None = None,
    scale_max: float | None = None,
    threshold: float | None = None,
) -> bytes:
    """Render and cache one deterministic figure as SVG, PDF, or TIFF bytes."""

    if matplotlib is None or plt is None:
        raise PlotUnavailableError("Matplotlib is not installed; sync the project dependencies")
    analysis_json = json.dumps(analysis, sort_keys=True, separators=(",", ":"), allow_nan=False)
    groups_json = json.dumps(list(groups), sort_keys=True, separators=(",", ":"), allow_nan=False)
    exclusion_override = (
        None
        if excluded_device_ids is None
        else tuple(sorted(set(str(device_id) for device_id in excluded_device_ids)))
    )
    arguments = (
        analysis_json,
        groups_json,
        kind,
        figure_format,
        metric,
        tuple(device_ids),
        exclusion_override,
        direction,
        palette,
        scale_min,
        scale_max,
        threshold,
    )
    # SVG drives the interactive preview and benefits from caching.  PDF and
    # especially 600 dpi TIFF exports can be large, so render downloads on
    # demand instead of retaining their byte buffers in server memory.
    if figure_format == "svg":
        return _render_cached(*arguments)
    return _render_uncached(*arguments)


@lru_cache(maxsize=96)
def _render_cached(
    analysis_json: str,
    groups_json: str,
    kind: FigureKind,
    figure_format: FigureFormat,
    metric: str | None,
    device_ids: tuple[str, ...],
    excluded_device_ids: tuple[str, ...] | None,
    direction: str,
    palette: str | None,
    scale_min: float | None,
    scale_max: float | None,
    threshold: float | None,
) -> bytes:
    return _render_uncached(
        analysis_json,
        groups_json,
        kind,
        figure_format,
        metric,
        device_ids,
        excluded_device_ids,
        direction,
        palette,
        scale_min,
        scale_max,
        threshold,
    )


def _render_uncached(
    analysis_json: str,
    groups_json: str,
    kind: FigureKind,
    figure_format: FigureFormat,
    metric: str | None,
    device_ids: tuple[str, ...],
    excluded_device_ids: tuple[str, ...] | None,
    direction: str,
    palette: str | None,
    scale_min: float | None,
    scale_max: float | None,
    threshold: float | None,
) -> bytes:
    analysis = json.loads(analysis_json)
    groups = json.loads(groups_json)
    if excluded_device_ids is not None:
        if len(excluded_device_ids) > 200:
            raise PlotInputError("at most 200 devices can be excluded from a preview")
        excluded = set(excluded_device_ids)
        known = {str(device.get("device_id")) for device in analysis.get("devices") or []}
        unknown = excluded - known
        if unknown:
            raise PlotInputError(f"unknown device: {min(unknown)}")
        for device in analysis.get("devices") or []:
            device_id = str(device.get("device_id"))
            device["excluded"] = device_id in excluded
            device["exclusion_reason"] = (
                device.get("exclusion_reason") if device_id in excluded else None
            )
    if figure_format not in MEDIA_TYPES:
        raise PlotInputError("unsupported figure format")
    if kind in {"boxplot", "uniformity"} and metric not in METRICS:
        raise PlotInputError("metric must be one of voc, jsc, ff, or pce")
    if kind == "uniformity" and direction not in {"forward", "reverse"}:
        raise PlotInputError("direction must be forward or reverse")
    available_palettes = ({"standalone", *CATEGORICAL_PALETTES} if kind == "jv" else
                          CATEGORICAL_PALETTES if kind == "boxplot" else GRADIENT_PALETTES)
    if palette is not None and palette not in available_palettes:
        raise PlotInputError("palette is not available for this figure kind")
    scale_options = {"scale_min": scale_min, "scale_max": scale_max, "threshold": threshold}
    if kind != "uniformity" and any(value is not None for value in scale_options.values()):
        raise PlotInputError("color scale controls are only available for uniformity")
    if any(value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value))
           for value in scale_options.values()):
        raise PlotInputError("color scale values must be finite numbers")
    if scale_min is not None and scale_max is not None and scale_min >= scale_max:
        raise PlotInputError("color scale minimum must be lower than maximum")
    if (scale_min is None) != (scale_max is None):
        raise PlotInputError("color scale minimum and maximum must be set together")
    with _MATPLOTLIB_LOCK, plt.rc_context(_RC):
        if kind == "jv":
            figure = _render_jv(analysis, groups, device_ids, palette or "standalone")
        elif kind == "boxplot":
            figure = _render_boxplot(analysis, groups, metric or "pce", palette or "nature-classic")
        elif kind == "uniformity":
            figure = _render_uniformity(
                analysis, groups, metric or "pce", direction, palette or "rdylgn",
                scale_min=scale_min, scale_max=scale_max, threshold=threshold,
            )
        else:
            raise PlotInputError("unsupported figure kind")
        try:
            return _save_figure(figure, figure_format)
        finally:
            plt.close(figure)


def _save_figure(figure: Figure, figure_format: FigureFormat) -> bytes:
    buffer = io.BytesIO()
    options: dict[str, Any] = {
        "format": figure_format,
        "bbox_inches": "tight",
        "pad_inches": 0.04,
    }
    if figure_format == "tiff":
        options.update(dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    elif figure_format == "svg":
        options["metadata"] = {"Date": None, "Creator": "perovskite-deposition-bo"}
    elif figure_format == "pdf":
        options["metadata"] = {"CreationDate": None, "ModDate": None, "Creator": "perovskite-deposition-bo"}
    figure.savefig(buffer, **options)
    return buffer.getvalue()


def _group_names(groups: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {str(group["group_id"]): str(group["name"]) for group in groups}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _representative_trace(device: Mapping[str, Any], direction: str) -> Mapping[str, Any] | None:
    candidates = [
        trace
        for trace in device.get("traces") or []
        if trace.get("valid") and trace.get("direction") == direction and trace.get("points")
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda trace: (
            value
            if (value := _finite_number((trace.get("metrics") or {}).get("pce"))) is not None
            else -math.inf
        ),
    )


def _trace_points(trace: Mapping[str, Any]) -> tuple[list[float], list[float]]:
    raw = [
        (float(point[0]), float(point[1]))
        for point in trace.get("points") or []
        if len(point) >= 2 and all(_finite_number(value) is not None for value in point[:2])
    ]
    if not raw:
        return [], []
    at_zero = min(raw, key=lambda point: abs(point[0]))
    sign = -1.0 if at_zero[1] < 0 else 1.0
    normalized = sorted((voltage, current * sign) for voltage, current in raw if voltage >= 0)
    return [point[0] for point in normalized], [point[1] for point in normalized]


def _render_jv(
    analysis: Mapping[str, Any],
    groups: Sequence[Mapping[str, Any]],
    selected_ids: Sequence[str],
    palette: str = "standalone",
) -> Figure:
    devices = list(analysis.get("devices") or [])
    by_id = {str(device.get("device_id")): device for device in devices}
    ids = list(dict.fromkeys(str(value) for value in selected_ids))
    if not ids:
        return _render_jv_overview(devices, groups, palette)
    if len(ids) > 12:
        raise PlotInputError("at most 12 devices can be plotted together")
    missing = [device_id for device_id in ids if device_id not in by_id]
    if missing:
        raise PlotInputError(f"unknown device: {missing[0]}")
    names = _group_names(groups)
    forward_color, reverse_color = _jv_colors(palette)
    cols = min(2, len(ids))
    rows = math.ceil(len(ids) / cols)
    figure, axes = plt.subplots(rows, cols, figsize=(3.35 * cols, 2.75 * rows), squeeze=False)
    any_curve = False
    for index, device_id in enumerate(ids):
        device = by_id[device_id]
        axis = axes[index // cols][index % cols]
        panel_has_curve = False
        for direction, color, linestyle in (
            ("forward", forward_color, "-"),
            ("reverse", reverse_color, "--"),
        ):
            trace = _representative_trace(device, direction)
            if trace is None:
                continue
            voltage, current = _trace_points(trace)
            if not voltage:
                continue
            axis.plot(
                voltage,
                current,
                color=color,
                linestyle=linestyle,
                marker="o",
                markersize=2.5,
                markerfacecolor=color,
                markeredgewidth=0,
                label=direction.capitalize(),
            )
            panel_has_curve = True
            any_curve = True
        axis.set_xlabel("Voltage (V)")
        axis.set_ylabel(r"Current density (mA cm$^{-2}$)")
        axis.grid(color="#E5E7EB", linewidth=0.55)
        axis.set_axisbelow(True)
        axis.set_xlim(left=0)
        axis.set_ylim(bottom=0)
        group_name = names.get(str(device.get("group_id")), "Unassigned")
        channel = device.get("device_ordinal")
        channel_text = f" · CH {channel}" if channel else ""
        axis.set_title(f"{device.get('substrate_id', '')}{channel_text}\n{group_name}", loc="left")
        if panel_has_curve:
            axis.legend(frameon=False, loc="best")
        else:
            axis.text(0.5, 0.5, "No valid F/R trace", ha="center", va="center", transform=axis.transAxes)
    for index in range(len(ids), rows * cols):
        axes[index // cols][index % cols].set_visible(False)
    if not any_curve:
        plt.close(figure)
        raise PlotInputError("selected devices have no valid J-V traces")
    figure.suptitle("Device J–V characteristics", y=0.995, fontsize=10)
    figure.tight_layout()
    return figure


def _render_jv_overview(
    devices: Sequence[Mapping[str, Any]], groups: Sequence[Mapping[str, Any]],
    palette: str = "standalone",
) -> Figure:
    """Show every device's representative forward and reverse curves by group."""

    panels: list[tuple[str | None, str]] = [
        (str(group["group_id"]), str(group["name"]))
        for group in groups
        if any(str(device.get("group_id")) == str(group["group_id"]) for device in devices)
    ]
    known_group_ids = {group_id for group_id, _ in panels}
    if any(str(device.get("group_id")) not in known_group_ids for device in devices):
        panels.append((None, "Unassigned"))
    if not panels:
        raise PlotInputError("no devices are available")
    forward_color, reverse_color = _jv_colors(palette)
    cols = min(2, len(panels))
    rows = math.ceil(len(panels) / cols)
    figure, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.0 * rows), squeeze=False)
    any_curve = False
    for index, (group_id, name) in enumerate(panels):
        axis = axes[index // cols][index % cols]
        members = [device for device in devices if (
            str(device.get("group_id")) not in known_group_ids if group_id is None
            else str(device.get("group_id")) == group_id
        )]
        for device in members:
            for direction, color, linestyle in (
                ("forward", forward_color, "-"),
                ("reverse", reverse_color, "--"),
            ):
                trace = _representative_trace(device, direction)
                if trace is None:
                    continue
                voltage, current = _trace_points(trace)
                if not voltage:
                    continue
                axis.plot(voltage, current, color=color, linestyle=linestyle,
                          marker="o", markersize=1.15, markeredgewidth=0,
                          linewidth=0.75, alpha=0.4)
                any_curve = True
        axis.set_title(f"{name} · {len(members)} devices", loc="left")
        axis.set_xlabel("Voltage (V)")
        axis.set_ylabel(r"Current density (mA cm$^{-2}$)")
        axis.grid(color="#E5E7EB", linewidth=0.55)
        axis.set_axisbelow(True)
        axis.set_xlim(left=0)
        axis.set_ylim(bottom=0)
    for index in range(len(panels), rows * cols):
        axes[index // cols][index % cols].set_visible(False)
    if not any_curve:
        plt.close(figure)
        raise PlotInputError("devices have no valid J-V traces")
    figure.legend(
        handles=[Line2D([], [], color=forward_color, label="Forward"),
                 Line2D([], [], color=reverse_color, linestyle="--", label="Reverse")],
        frameon=False, ncol=2, loc="upper right",
    )
    figure.suptitle("All-device J–V curves", y=0.995, fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    return figure


def _jv_colors(palette: str) -> tuple[str, str]:
    if palette == "standalone":
        return FORWARD_COLOR, REVERSE_COLOR
    colors = CATEGORICAL_PALETTES[palette]
    return colors[0], colors[1]


def _metric_value(device: Mapping[str, Any], direction: str, metric: str) -> float | None:
    metrics = device.get("metrics") or {}
    directional = metrics.get(direction) or {}
    value = _finite_number(directional.get(metric))
    return None if value is None else value * METRICS[metric][2]


def _scope_label(devices: Sequence[Mapping[str, Any]]) -> str:
    return "After exclusions" if any(device.get("excluded") for device in devices) else "All devices"


def _render_boxplot(
    analysis: Mapping[str, Any], groups: Sequence[Mapping[str, Any]], metric: str,
    palette: str = "nature-classic",
) -> Figure:
    devices = list(analysis.get("devices") or [])
    plotted_groups = [
        group
        for group in groups
        if any(str(device.get("group_id")) == str(group["group_id"]) for device in devices)
    ]
    datasets: list[tuple[str, str, list[float], str]] = []
    for group_index, group in enumerate(plotted_groups):
        group_devices = [
            device
            for device in devices
            if str(device.get("group_id")) == str(group["group_id"]) and not device.get("excluded")
        ]
        for direction in ("forward", "reverse"):
            values = [
                value
                for device in group_devices
                for value in [_metric_value(device, direction, metric)]
                if value is not None
            ]
            if values:
                colors = CATEGORICAL_PALETTES[palette]
                datasets.append((str(group["name"]), direction, values, colors[group_index % len(colors)]))
    if not datasets:
        raise PlotInputError("no valid assigned devices for this metric")
    width = max(4.1, 0.72 * len(datasets) + 1.1)
    figure, axis = plt.subplots(figsize=(width, 3.45))
    positions = list(range(1, len(datasets) + 1))
    boxplot = axis.boxplot(
        [dataset[2] for dataset in datasets],
        positions=positions,
        widths=0.52,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#111827", "linewidth": 1.25},
        whiskerprops={"color": "#4B5563", "linewidth": 0.9},
        capprops={"color": "#4B5563", "linewidth": 0.9},
    )
    for patch, (_, direction, _, color) in zip(boxplot["boxes"], datasets, strict=True):
        patch.set(facecolor=color, alpha=0.18, edgecolor=color, linewidth=1.15)
        if direction == "reverse":
            patch.set_linestyle("--")
    for position, (_, direction, values, color) in zip(positions, datasets, strict=True):
        offsets = _symmetric_offsets(len(values), 0.22)
        marker = "o" if direction == "forward" else "s"
        axis.scatter(
            [position + offset for offset in offsets],
            values,
            s=15,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            alpha=0.9,
            zorder=4,
        )
        axis.scatter(
            [position],
            [sum(values) / len(values)],
            s=23,
            marker="D",
            facecolor="white",
            edgecolor="#111827",
            linewidth=0.8,
            zorder=5,
        )
        axis.text(position, 0.015, f"n={len(values)}", ha="center", va="bottom", transform=axis.get_xaxis_transform(), fontsize=6.8)
    metric_label, unit, _, _ = METRICS[metric]
    axis.set_ylabel(f"{metric_label} ({unit})")
    axis.set_xlabel(_scope_label(devices), labelpad=12)
    axis.set_xticks(positions)
    axis.set_xticklabels([
        f"{name}\n{'F' if direction == 'forward' else 'R'}" for name, direction, _, _ in datasets
    ])
    axis.grid(axis="y", color="#E5E7EB", linewidth=0.55)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    lower, upper = axis.get_ylim()
    highest_point = max(max(values) for _, _, values, _ in datasets)
    ticks = [float(tick) for tick in axis.get_yticks()]
    tick_step = ticks[-1] - ticks[-2] if len(ticks) > 1 else max(abs(highest_point) * 0.1, 0.1)
    top_tick = next((tick for tick in ticks if tick >= highest_point), None)
    if top_tick is None:
        top_tick = math.ceil(highest_point / tick_step) * tick_step
    bottom = lower - (upper - lower) * 0.12
    axis.set_ylim(bottom, top_tick + tick_step * 0.08)
    axis.set_yticks(sorted({tick for tick in ticks if bottom <= tick <= top_tick} | {top_tick}))
    axis.set_title(f"{metric_label} distribution by condition and scan direction", pad=43)
    axis.legend(
        handles=[
            Line2D([], [], marker="o", color="none", markerfacecolor="#4B5563", markeredgecolor="white", label="Forward (F)"),
            Line2D([], [], marker="s", color="none", markerfacecolor="#4B5563", markeredgecolor="white", label="Reverse (R)"),
            Line2D([], [], marker="D", color="none", markerfacecolor="white", markeredgecolor="#111827", label="Mean"),
        ],
        frameon=False,
        ncol=3,
        loc="lower left",
        bbox_to_anchor=(0, 1.01),
    )
    figure.tight_layout()
    return figure


def _symmetric_offsets(count: int, width: float) -> list[float]:
    if count <= 1:
        return [0.0] * count
    return [(-width / 2) + width * index / (count - 1) for index in range(count)]


def _device_position(device: Mapping[str, Any]) -> int | None:
    value = device.get("device_ordinal")
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 6 else None


def _render_uniformity(
    analysis: Mapping[str, Any], groups: Sequence[Mapping[str, Any]], metric: str,
    direction: str = "forward", palette: str = "rdylgn",
    *, scale_min: float | None = None, scale_max: float | None = None,
    threshold: float | None = None,
) -> Figure:
    devices = list(analysis.get("devices") or [])
    by_substrate: dict[str, list[Mapping[str, Any]]] = {}
    for device in devices:
        by_substrate.setdefault(str(device.get("substrate_id")), []).append(device)
    if not by_substrate:
        raise PlotInputError("no substrates are available")
    if len(by_substrate) > 60:
        raise PlotInputError("uniformity figures support at most 60 substrates")
    all_values = [
        value
        for device in devices
        if _device_position(device) is not None
        for direction in ("forward", "reverse")
        for value in [_metric_value(device, direction, metric)]
        if value is not None
    ]
    visible_values = [
        value for device in devices if not device.get("excluded")
        for direction in ("forward", "reverse")
        for value in [_metric_value(device, direction, metric)]
        if _device_position(device) is not None and value is not None
    ]
    if not visible_values:
        raise PlotInputError("no mapped valid measurements for this metric")
    neutral_label = "all-device median"
    if palette == "red-blue":
        center = threshold if threshold is not None else statistics.median(all_values)
        radius = max(abs(value - center) for value in all_values)
        radius = radius if radius > 0 else max(abs(center) * 0.05, 0.5)
        automatic_min, automatic_max = center - radius, center + radius
    else:
        center = 0.0
        automatic_min, automatic_max = min(all_values), max(all_values)
        if math.isclose(automatic_min, automatic_max):
            padding = max(abs(automatic_min) * 0.05, 0.5)
            automatic_min -= padding
            automatic_max += padding
    minimum = scale_min if scale_min is not None else automatic_min
    maximum = scale_max if scale_max is not None else automatic_max
    if threshold is not None and palette != "red-blue":
        padding = max((automatic_max - automatic_min) * 0.05, 0.001)
        if scale_min is None and threshold <= minimum:
            minimum = threshold - padding
        if scale_max is None and threshold >= maximum:
            maximum = threshold + padding
    if minimum >= maximum:
        raise PlotInputError("color scale minimum must be lower than maximum")
    if palette == "red-blue":
        if not minimum < center < maximum:
            if threshold is not None:
                raise PlotInputError("problem threshold must be inside the color scale range")
            center = (minimum + maximum) / 2
            neutral_label = "selected range midpoint"
        norm = matplotlib.colors.TwoSlopeNorm(vmin=minimum, vcenter=center, vmax=maximum)
    elif threshold is not None:
        if not minimum < threshold < maximum:
            raise PlotInputError("problem threshold must be inside the color scale range")
        norm = matplotlib.colors.TwoSlopeNorm(vmin=minimum, vcenter=threshold, vmax=maximum)
    else:
        norm = matplotlib.colors.Normalize(minimum, maximum)
    names = _group_names(groups)
    group_order = [str(group["group_id"]) for group in groups]
    by_group: dict[str, list[str]] = {}
    for substrate, entries in by_substrate.items():
        group_id = str(entries[0].get("group_id"))
        by_group.setdefault(group_id, []).append(substrate)
    grouped_substrates: list[tuple[str, list[str]]] = []
    for group_id in group_order:
        if group_id in by_group:
            grouped_substrates.append((group_id, sorted(by_group.pop(group_id), key=_natural_key)))
    for group_id in sorted(by_group, key=lambda value: _natural_key(names.get(value, value))):
        grouped_substrates.append((group_id, sorted(by_group[group_id], key=_natural_key)))
    rows = len(grouped_substrates)
    cols = max(len(substrates) for _, substrates in grouped_substrates)
    figure_height = 3.3 if rows == 1 else 2.55 * rows + 0.5
    figure, axes = plt.subplots(
        rows,
        cols,
        figsize=(2.25 * cols + 1.2, figure_height),
        squeeze=False,
    )
    cmap = LinearSegmentedColormap.from_list(palette, GRADIENT_PALETTES[palette])
    label, unit, _, digits = METRICS[metric]
    visible_axes: set[tuple[int, int]] = set()
    for row_index, (_, substrates) in enumerate(grouped_substrates):
        for column_index, substrate in enumerate(substrates):
            visible_axes.add((row_index, column_index))
            axis = axes[row_index][column_index]
            entries = by_substrate[substrate]
            positions: dict[int, list[Mapping[str, Any]]] = {}
            for device in entries:
                position = _device_position(device)
                if position is not None:
                    positions.setdefault(position, []).append(device)
            for channel, (column, top_row) in _CELL_POSITION.items():
                matches = positions.get(channel) or []
                device = matches[0] if len(matches) == 1 else None
                value = None if device is None or device.get("excluded") else _metric_value(device, direction, metric)
                x = 0.68 + column * 0.9
                y = 0.33 + (2 - top_row) * 0.78
                if value is None:
                    facecolor = "#F3F4F6"
                    hatch = "///" if device and device.get("excluded") else None
                    text = "—"
                    text_color = "#6B7280"
                else:
                    facecolor = cmap(norm(value))
                    hatch = None
                    text = f"{value:.{digits}f}"
                    red, green, blue = to_rgb(facecolor)
                    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
                    text_color = "white" if luminance < 0.48 else "#111827"
                axis.add_patch(Rectangle((x, y), 0.72, 0.72, facecolor=facecolor, edgecolor="#6B7280", linewidth=0.6, hatch=hatch))
                axis.text(x + 0.36, y + 0.36, text, ha="center", va="center",
                          fontsize=8.0, color=text_color, clip_on=True)
            axis.add_patch(Rectangle((0.15, 0.15), 2.65, 2.65, fill=False, edgecolor="#374151", linewidth=1.1))
            axis.set_title(substrate, loc="center", pad=4)
            axis.set_xlim(0, 2.95)
            axis.set_ylim(0, 3.1)
            axis.set_aspect("equal")
            axis.axis("off")
    for row_index in range(rows):
        for column_index in range(cols):
            if (row_index, column_index) not in visible_axes:
                axes[row_index][column_index].set_visible(False)
    scalar = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    colorbar_axis = figure.add_axes([0.92, 0.16, 0.018, 0.68])
    clipped_low = min(all_values) < minimum
    clipped_high = max(all_values) > maximum
    extend = "both" if clipped_low and clipped_high else "min" if clipped_low else "max" if clipped_high else "neither"
    colorbar = figure.colorbar(scalar, cax=colorbar_axis, orientation="vertical", extend=extend)
    if threshold is not None:
        colorbar_label = f"{label} ({unit}) · Problem threshold: {threshold:.{digits}f} {unit}"
    elif palette == "red-blue":
        colorbar_label = f"{label} ({unit}); white = {neutral_label}; shared across substrates, scopes and F/R"
    else:
        colorbar_label = f"{label} ({unit}); shared across substrates, scopes and F/R"
    colorbar.set_label(colorbar_label)
    if scale_min is not None or scale_max is not None or threshold is not None:
        middle_tick = threshold if threshold is not None else center if palette == "red-blue" else (minimum + maximum) / 2
        colorbar.set_ticks([norm.vmin, middle_tick, norm.vmax])
    if threshold is not None:
        colorbar.ax.axhline(threshold, color="#111827", linewidth=1.4)
    figure.suptitle(
        f"Substrate uniformity · {label} · {direction.title()} · {_scope_label(devices)}",
        fontsize=10, y=0.985,
    )
    top = 0.82 if rows == 1 else 0.92
    bottom = 0.08 if rows == 1 else 0.04
    figure.subplots_adjust(left=0.12, right=0.89, top=top, bottom=bottom, wspace=0.14, hspace=0.24)
    for row_index, (group_id, _) in enumerate(grouped_substrates):
        bounds = axes[row_index][0].get_position()
        figure.text(0.055, (bounds.y0 + bounds.y1) / 2, names.get(group_id, "Unassigned"),
                    ha="center", va="center", rotation=90, fontsize=9, fontweight="bold")
    return figure


def _natural_key(value: str) -> tuple[Any, ...]:
    import re

    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value))
