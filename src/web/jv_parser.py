"""CSV parser for JV characterization files.

The parser expects a CSV file with voltage and current-density columns. It uses
standard photovoltaic conventions to derive Voc, Jsc, FF, and PCE without adding
heavy data-analysis dependencies.

For multi-device instrument exports the parser also preserves each trace
block's info rows verbatim and scans them for the instrument software's own
summary metrics (Voc, Jsc, FF, and PCE/Eff). The instrument-reported values are
stored alongside the computed metrics so the two can be compared in the
analysis view; the computed metrics remain the statistical source of truth.
"""

from __future__ import annotations

import csv
import io
import itertools
import math
import random
import re
import statistics
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

VOLTAGE_NAMES = {"voltage", "voltage_v", "v", "bias", "bias_v"}
# Columns that are already current density (mA/cm2). Total current is a
# different physical quantity (J = I / A) and is handled separately below.
CURRENT_DENSITY_NAMES = {
    "current_density",
    "current_density_ma_cm2",
    "current density",
    "current density (ma/cm2)",
    "j",
    "j_ma_cm2",
}
# Total-current columns mapped to their factor converting to mA. They are
# only accepted together with the device active area, and any conversion is
# recorded in the analysis for provenance. A bare "jsc" column is a single
# number, not a curve, and is deliberately not accepted here.
RAW_CURRENT_NAMES: Mapping[str, float] = {
    "current": 1.0,
    "current_ma": 1.0,
    "current_(ma)": 1.0,
    "i": 1.0,
    "i_ma": 1.0,
    "current_a": 1000.0,
    "current_(a)": 1000.0,
}
DEVICE_MARK_PATTERN = re.compile(
    r"(?<![A-Z0-9])([A-Z][0-9]{3,8})(?![A-Z0-9])", re.IGNORECASE
)

ANALYSIS_SCHEMA_VERSION = 7
# Canonical physical shape of a factory-etched substrate laser mark: one
# letter followed by 3-8 digits (4-9 characters, matching the storage limit
# enforced by the database check constraints).  The bounded token pattern
# rejects marks embedded in longer alphanumeric runs and marks exceeding 9
# characters.
LASER_MARK_PATTERN = re.compile(r"[A-Z][0-9]{3,8}")
LASER_MARK_TOKEN = re.compile(
    r"(?<![A-Z0-9])([A-Z][0-9]{3,8})(?![A-Z0-9])", re.IGNORECASE
)
# An instrument label is only unambiguous when it carries exactly one
# explicit "Channel N" token naming the physical device on the substrate.
CHANNEL_PATTERN = re.compile(r"\bchannel\s*#?\s*([0-9]+)", re.IGNORECASE)
# Some instrument exports name a device as <substrate>-<channel> inside a
# parenthesized scan label, e.g. "18-1 3 (Control-1-2.CH_Ref.Forward(1))".
# The prefix is acquisition metadata; Control-1 is the instrument's substrate
# name, not a condition assignment. Only the final number identifies a cell.
INSTRUMENT_DEVICE_SUFFIX = re.compile(r"\(([^()]+)-(\d+)\)$")
INSTRUMENT_TIMESTAMP_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M")
# Instrument-reported summary metrics are recognized in trace info rows whose
# label names the metric ("Voc (V)", "Jsc (mA/cm2)", "FF (%)", "Eff (%)",
# "PCE (%)", "Fill Factor"). The label must start with the metric keyword and
# the numeric value is parsed from the adjacent cell. FF reported above 1 is
# interpreted as a percentage and normalized to the 0-1 fraction used by the
# computed metrics. Labels and raw values are preserved verbatim so future
# extraction rules can be refined without re-uploading the file.
INSTRUMENT_METRIC_PATTERNS = {
    "voc": re.compile(r"^voc\b", re.IGNORECASE),
    "jsc": re.compile(r"^jsc\b", re.IGNORECASE),
    "ff": re.compile(r"^(?:ff\b|fill\s*factor\b)", re.IGNORECASE),
    "pce": re.compile(r"^(?:pce\b|eff\b|efficiency\b)", re.IGNORECASE),
}

# Column names of the trailing per-scan summary table that map onto the
# four core metrics. FF arrives in percent and is normalized to a 0-1
# fraction, matching the recomputed fallback's convention.
SUMMARY_COLUMN_METRICS = {
    "voc": "Voc (V)",
    "jsc": "Jsc (mA/cm^2)",
    "ff": "Fill Factor (%)",
    "pce": "Efficiency (%)",
}
_SUMMARY_HEADER_SIGNATURE = ("No.", "Name", "Isc (mA)")
_SUMMARY_NAME_RE = re.compile(
    r"^(?P<stem>.+?)[._ -]*(?P<direction>Forward|Reverse)(?:\(\s*(?P<scan_number>\d+)\s*\))?$",
    re.IGNORECASE,
)
# Trace labels may wrap the device stem in a date/prefix (e.g.
# '20260915 (B001-Control1-1-1.Channel1.CH_Ref.Forward(1))'); the
# summary table repeats the bare stem ('Control1-1-1.CH_Ref.Forward(1)').
# Matching uses the last parenthesized/last-dot segment that carries the
# direction keyword so both forms map to the same key.
_TRACE_DIRECTION_RE = re.compile(
    r"(?P<direction>Forward|Reverse)\s*(?:\(\s*(?P<scan_number>\d+)\s*\))?\s*\)?\s*$",
    re.IGNORECASE,
)


def _summary_scan_key(label: str) -> tuple[str, str, str | None] | None:
    """Map a trace label to its (stem, direction, scan number) summary-table key.

    The summary table's Name column repeats the device stem, with or
    without the trailing scan-index suffix ('A001 Channel 1.Forward(1)'
    vs 'A001 Channel 1.Forward'). Trace labels may additionally wrap that
    stem in a date/prefix parenthesis ('20260915 (B001-...Channel1...)
    …Forward(1))') or carry extra suffixes after the direction keyword, so
    the stem is normalized to the last '(' -wrapped segment when present
    before falling back to the leading text. Returns ``None`` for labels
    that do not carry a direction keyword.
    """

    text = label.strip()
    match = _TRACE_DIRECTION_RE.search(text)
    if not match:
        return None
    direction = match.group("direction").lower()
    stem = text[: match.start()].rstrip(" .-_(")
    # unwrap 'prefix (stem' -> 'stem' (date/mark wrapper around the device)
    if "(" in stem:
        stem = stem.rsplit("(", 1)[-1]
    if not stem:
        return None
    return stem, direction, match.group("scan_number")
# Rows of the in-block [Statistic] section that carry the four core
# metrics; the label/value pair sits in the block's first two columns.
_STATISTIC_METRIC_ROWS = {
    "voc": "Voc (V)",
    "jsc": "Jsc (mA/cm^2)",
    "ff": "Fill Factor (%)",
    "pce": "Efficiency (%)",
}
_INFO_ROW_LIMIT = 24
_INFO_VALUE_LIMIT = 64
_NUMBER_IN_VALUE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

def normalize_laser_mark(value: str) -> str:
    """Validate and normalize a physical substrate laser mark (e.g. ``A001``).

    This is the single canonical validator shared by parser normalization and
    repository assignment: a non-empty value is not enough — the mark must
    have the agreed physical shape (letter + digits, 4-9 characters).
    """

    mark = str(value).strip().upper()
    if not LASER_MARK_PATTERN.fullmatch(mark):
        raise ValueError(f"substrate laser mark {value!r} must look like A001")
    return mark


def channel_ordinal_from_label(label: str) -> int | None:
    """Return the explicit physical channel number in an instrument label.

    Returns ``None`` when the label carries zero or multiple channel tokens
    (or a non-positive number): such labels are ambiguous and physical
    assignment must reject them instead of guessing from trace order.
    """

    matches = CHANNEL_PATTERN.findall(label)
    if len(matches) != 1:
        return None
    ordinal = int(matches[0])
    return ordinal if ordinal >= 1 else None


def _instrument_named_identity(label: str) -> tuple[str, int] | None:
    """Read an instrument substrate name and channel without inferring a group."""

    match = INSTRUMENT_DEVICE_SUFFIX.search(label.strip())
    if not match:
        return None
    substrate = match.group(1).strip()
    ordinal = int(match.group(2))
    if not substrate or ordinal < 1:
        return None
    return substrate, ordinal


def _parse_numeric_value(value: str) -> float | None:
    """Return the first finite number embedded in an info-row value cell."""

    match = _NUMBER_IN_VALUE.search(value)
    if match is None:
        return None
    number = float(match.group(0))
    return number if math.isfinite(number) else None


# Illumination reported by the instrument (e.g. an "Int. (sun)" info row).
# Computed PCE assumes 1 sun (100 mW/cm2); a deviating reported intensity is
# surfaced as an analysis warning instead of being silently ignored.
IRRADIANCE_LABEL_PATTERN = re.compile(r"(?:int\.?|intensity)\s*\(sun\)", re.IGNORECASE)
IRRADIANCE_TOLERANCE = 0.05


def _irradiance_from_info(info: Mapping[str, str]) -> float | None:
    for label, raw_value in info.items():
        if IRRADIANCE_LABEL_PATTERN.search(label):
            return _parse_numeric_value(raw_value)
    return None


def _irradiance_warnings(
    label: str, irradiance: float | None
) -> list[str]:
    if irradiance is None or abs(irradiance - 1.0) <= IRRADIANCE_TOLERANCE:
        return []
    return [
        f"Trace {label!r} reports illumination {irradiance:g} sun; computed "
        "metrics assume 1 sun (100 mW/cm2) and are not rescaled."
    ]


def _instrument_metrics_from_info(
    info: Mapping[str, str],
) -> tuple[dict[str, float], dict[str, str]] | None:
    """Extract instrument-reported summary metrics from trace info rows.

    Returns ``(metrics, labels)`` — ``labels`` records which info-row label
    each value came from — or ``None`` when no known metric label is present.
    """

    metrics: dict[str, float] = {}
    labels: dict[str, str] = {}
    for label, raw_value in info.items():
        for name, pattern in INSTRUMENT_METRIC_PATTERNS.items():
            if name in metrics or not pattern.match(label):
                continue
            value = _parse_numeric_value(raw_value)
            if value is None:
                continue
            if name == "ff" and value > 1:
                value = value / 100.0
            metrics[name] = value
            labels[name] = label
    if not metrics:
        return None
    return metrics, labels


def _locate_summary_table(rows: list[list[str]]) -> int | None:
    """Locate the per-scan summary table's header row by structural signature.

    The export ends with a table whose header is ``No., Name, Isc (mA),
    Voc (V), Pmax (mW), ...`` — its position in the file varies with the
    number of scans, so it must be found by content, never by row number.
    An all-'=' separator row typically (not always) precedes it.
    """

    for index, row in enumerate(rows):
        if len(row) < len(_SUMMARY_HEADER_SIGNATURE):
            continue
        cells = [cell.strip() for cell in row[: len(_SUMMARY_HEADER_SIGNATURE)]]
        if tuple(cells) == _SUMMARY_HEADER_SIGNATURE:
            return index
    return None


def _summary_table_metrics(
    rows: list[list[str]],
    header_index: int,
) -> dict[tuple[str, str, str | None], tuple[dict[str, float], dict[str, str]]]:
    """Grab per-scan metrics from the trailing summary table.

    Returns ``{(device stem, direction, scan number): (metrics, extra_columns)}`` where
    ``metrics`` holds the four core metrics (FF normalized to a fraction)
    and ``extra_columns`` keeps every other named column verbatim for the
    trace's ``info`` record (Rs, Rsh, Pmax, ... are valuable and must not
    be discarded). Values that fail to parse as numbers are skipped.
    """

    header = rows[header_index]
    column_of = {cell.strip(): index for index, cell in enumerate(header) if cell.strip()}
    metric_columns = {
        name: column_of[label] for name, label in SUMMARY_COLUMN_METRICS.items()
        if label in column_of
    }
    extra_labels = [
        label for label in column_of
        if label not in ("No.", "Name") and label not in SUMMARY_COLUMN_METRICS.values()
    ]
    scans: dict[tuple[str, str, str | None], tuple[dict[str, float], dict[str, str]]] = {}
    ambiguous: set[tuple[str, str, str | None]] = set()
    for row in rows[header_index + 1:]:
        if len(row) < len(column_of):
            continue
        name_cell = row[column_of["Name"]].strip() if "Name" in column_of else ""
        match = _SUMMARY_NAME_RE.match(name_cell)
        if not match:
            continue
        stem = match.group("stem")
        direction = match.group("direction").lower()
        scan_number = match.group("scan_number")
        metrics: dict[str, float] = {}
        for name, column in metric_columns.items():
            value = _parse_numeric_value(row[column].strip())
            if value is None:
                continue
            if name == "ff" and value > 1:
                value = value / 100.0
            metrics[name] = value
        extra = {label: row[column_of[label]].strip() for label in extra_labels}
        if not metrics:
            continue
        key = (stem, direction, scan_number)
        if key in ambiguous:
            continue
        if key in scans:
            # No scan number means duplicate names cannot be paired safely
            # with individual traces; let their in-block metrics take over.
            del scans[key]
            ambiguous.add(key)
            continue
        scans[key] = (metrics, extra)
    return scans


def _canonical_stem(stem: str) -> str:
    """Normalize a trace/summary stem to its shared device identity.

    Trace labels wrap the device in identity layers the summary table's
    Name column omits: a laser-mark prefix ('B001-Control1-1-1…') and a
    'Channel1' segment. Stripping both leaves the common device stem
    ('Control1-1-1.CH_Ref'), which is what the summary table repeats.
    """

    parts = stem.split(".")
    # drop 'Channel N' interlayers (trace labels carry them, tables don't)
    parts = [p for p in parts if not re.fullmatch(r"Channel\s*\d+", p.strip(), re.IGNORECASE)]
    if parts:
        head = parts[0].strip()
        # drop a leading laser-mark prefix ('B001-…') from the head segment.
        # The mark must match the repo's LASER_MARK_PATTERN shape (letter +
        # at least 3 digits), so condition prefixes like 'T1-' or 'Control-'
        # are never mistaken for marks.
        head = re.sub(r"^[A-Z][0-9]{3,8}-", "", head)
        parts[0] = head
    return ".".join(part.strip() for part in parts if part.strip())


def _match_summary_scan(
    key: tuple[str, str, str | None] | None,
    scans: dict[tuple[str, str, str | None], tuple[dict[str, float], dict[str, str]]],
) -> tuple[dict[str, float], dict[str, str]] | None:
    """Match a trace's stem, direction and scan number against summary rows.

    Both sides are canonicalized first (the trace label's stem may carry
    identity layers the summary table's Name column omits — laser-mark
    prefix, Channel segment). Exact canonical key, then a same-direction
    suffix match as a safety net for yet-unseen label conventions.
    """

    if key is None:
        return None
    stem, direction, scan_number = _canonical_stem(key[0]), key[1], key[2]
    exact = [
        entry
        for (table_stem, table_direction, table_scan_number), entry in scans.items()
        if table_direction == direction
        and table_scan_number == scan_number
        and _canonical_stem(table_stem) == stem
    ]
    if len(exact) == 1:
        return exact[0]
    candidates = [
        (table_stem, table_scan_number, entry)
        for (table_stem, table_direction, table_scan_number), entry in scans.items()
        if table_direction == direction and (
            stem.endswith(_canonical_stem(table_stem))
            or _canonical_stem(table_stem).endswith(stem)
        )
    ]
    if scan_number is not None:
        numbered = [item for item in candidates if item[1] == scan_number]
        candidates = numbered or [item for item in candidates if item[1] is None]
    if not candidates:
        return None
    candidates.sort(key=lambda item: -len(item[0]))
    if len(candidates) > 1 and len(candidates[0][0]) == len(candidates[1][0]):
        return None
    return candidates[0][2]


def _statistic_section_metrics(
    rows: list[list[str]],
    start: int,
    end: int,
) -> tuple[dict[str, float], dict[str, str]] | None:
    """Grab metrics from a scan block's [Statistic] section.

    Some exports carry a ``[Statistic]`` section inside each scan block:
    label/value pairs in the block's first two columns ('Name', 'Isc (mA)',
    'Voc (V)', ...). Used as the fallback when the file has no trailing
    summary table. Returns ``(metrics, labels)`` or ``None``.
    """

    metrics: dict[str, float] = {}
    labels: dict[str, str] = {}
    statistic_row = next(
        (
            index
            for index in range(2, len(rows))
            if len(rows[index]) > start and rows[index][start].strip() == "[Statistic]"
        ),
        None,
    )
    if statistic_row is None:
        return None
    for row in rows[statistic_row + 1:]:
        if len(row) <= start + 1:
            continue
        label = row[start].strip()
        if not label:
            continue
        if label == "Name":
            continue
        for name, row_label in _STATISTIC_METRIC_ROWS.items():
            if name in metrics or label.casefold() != row_label.casefold():
                continue
            value = _parse_numeric_value(row[start + 1].strip())
            if value is None:
                continue
            if name == "ff" and value > 1:
                value = value / 100.0
            metrics[name] = value
            labels[name] = label
        if len(metrics) == len(_STATISTIC_METRIC_ROWS):
            break
    if not metrics:
        return None
    return metrics, labels


def _block_info_rows(rows: list[list[str]], start: int, end: int) -> dict[str, str]:
    """Collect the label/value info rows of one trace block verbatim.

    Data rows leave the block's label column empty, so any row carrying a
    non-empty label is informational (Name, Time stamp, Voc, Jsc, ...).
    """

    info: dict[str, str] = {}
    for row in rows[2:]:
        padded = row + [""] * max(0, end - len(row))
        label = padded[start].strip()
        if not label:
            continue
        key = next(
            (existing for existing in info if existing.casefold() == label.casefold()),
            None,
        )
        if key is None:
            value = padded[start + 1].strip() if start + 1 < len(padded) else ""
            info[label[:_INFO_VALUE_LIMIT]] = value[:_INFO_VALUE_LIMIT]
        if len(info) >= _INFO_ROW_LIMIT:
            break
    return info


def _block_metadata_rows(rows: list[list[str]], start: int, end: int) -> list[dict[str, Any]]:
    """Lossless label/value rows, including duplicate labels and empty values.

    Keep strings such as NaN and ######## as reported by the instrument.
    Section and source row distinguish Information.Name from Statistic.Name.
    The legacy ``info`` dictionary remains a compact compatibility view.
    """
    entries = []
    section = None
    for row_number, row in enumerate(rows[1:], start=2):
        if start >= len(row):
            continue
        label = row[start]
        stripped = label.strip()
        if not stripped or set(stripped) == {"="}:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
        entries.append({
            "section": section,
            "row_number": row_number,
            "label": label,
            "value": row[start + 1] if start + 1 < min(end, len(row)) else "",
        })
    return entries


@dataclass(frozen=True)
class JVPoint:
    voltage: float
    current_density: float


def _decode_text(content: bytes) -> str:
    """Decode an instrument CSV payload to text.

    UTF-8 (with optional BOM) is the canonical encoding. Instrument software
    running on Chinese Windows exports GBK-encoded files instead (full-width
    punctuation such as （）in channel labels), so undecodable payloads fall
    back to GB18030 — the standards-track superset of GBK/GB2312 that every
    such export can decode under. A payload that is neither UTF-8 nor GB18030
    still raises UnicodeDecodeError, which the upload route maps to a 400.
    """

    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("gb18030")


def parse_jv_metrics(
    content: bytes | str,
    *,
    device_active_area_cm2: float | None = None,
) -> dict[str, float]:
    """Extract Voc, Jsc, FF, and PCE from a JV CSV file.

    The returned metric names match the existing experiment-store convention:
    ``pce`` is required when the repository completes an experiment, with supporting
    ``voc``, ``jsc``, and ``ff`` metrics stored alongside it.

    This function extracts summary metrics only and does not require a
    source filename: physical identity is established by ``parse_jv_analysis``
    when the full analysis (devices, substrates, statistics) is needed.
    """

    text = _decode_text(content) if isinstance(content, bytes) else content
    if _looks_like_multi_device_export(text):
        return _flat_metrics_from_analysis(_parse_multi_device_analysis(text))
    points, _ = _read_points(text, device_active_area_cm2)
    return _metrics_from_points(points)


def _flat_metrics_from_analysis(analysis: Mapping[str, Any]) -> dict[str, float]:
    """Pooled flat metric record over every non-excluded valid trace.

    The ``result_files.metrics`` column is a write-time cache for list rows
    and the completion transition: it pools the per-trace instrument-reported
    values the same way the retired v6 combined tier did (medians, mean,
    best). The analysis JSON itself stores no aggregates — every scan stays
    an individual trace and this record is always re-derivable from them.
    """

    devices = analysis.get("devices") or []
    traces = [
        trace
        for device in devices
        if isinstance(device, Mapping) and not device.get("excluded")
        for trace in (device.get("traces") or [])
        if isinstance(trace, Mapping) and trace.get("valid") and isinstance(trace.get("metrics"), Mapping)
    ]

    def values(name: str) -> list[float]:
        return [
            float(trace["metrics"][name])
            for trace in traces
            if isinstance(trace["metrics"].get(name), (int, float))
            and not isinstance(trace["metrics"].get(name), bool)
        ]

    pces = values("pce")
    flat: dict[str, float] = {}
    if values("voc"):
        flat["voc"] = statistics.median(values("voc"))
    if values("jsc"):
        flat["jsc"] = statistics.median(values("jsc"))
    if values("ff"):
        flat["ff"] = statistics.median(values("ff"))
    if pces:
        flat["pce"] = statistics.median(pces)
        flat["pce_mean"] = statistics.fmean(pces)
        flat["pce_best"] = max(pces)
    flat["trace_count"] = float(
        sum(
            1
            for device in devices
            if isinstance(device, Mapping) and not device.get("excluded")
            for trace in (device.get("traces") or [])
            if isinstance(trace, Mapping)
        )
    )
    flat["valid_trace_count"] = float(len(traces))
    flat["device_count"] = float(
        sum(1 for device in devices if isinstance(device, Mapping) and not device.get("excluded"))
    )
    return flat


def _identity_from_filename(source_filename: str | None) -> tuple[str, int]:
    """Extract exactly one laser mark and one channel ordinal from the
    source filename of a simple (single-trace) CSV.

    The filename must carry the physical identity because the CSV content
    itself has no instrument labels.  Raises ``ValueError`` when the
    filename is absent or carries zero/multiple marks or channels.
    """

    if not source_filename:
        raise ValueError(
            "a simple JV CSV requires a source filename that identifies the "
            "physical substrate and device channel"
        )
    name = source_filename
    marks = LASER_MARK_TOKEN.findall(name)
    channels = CHANNEL_PATTERN.findall(name)
    if len(marks) != 1:
        raise ValueError(
            f"source filename {source_filename!r} must contain exactly one "
            "substrate laser mark (e.g. A001)"
        )
    if len(channels) != 1:
        raise ValueError(
            f"source filename {source_filename!r} must contain exactly one "
            "device channel (e.g. Channel 1)"
        )
    ordinal = int(channels[0])
    if ordinal < 1:
        raise ValueError(
            f"source filename {source_filename!r} has a non-positive channel "
            f"ordinal {ordinal}"
        )
    return normalize_laser_mark(marks[0]), ordinal


def parse_jv_analysis(
    content: bytes | str,
    *,
    source_filename: str | None = None,
    device_active_area_cm2: float | None = None,
) -> dict[str, Any]:
    """Parse every device and trace needed for assignment, statistics, and plotting.

    For a multi-device instrument export, physical identity comes from the
    trace labels (each must carry exactly one substrate mark + one channel).
    For a simple (single-trace) CSV, ``source_filename`` must supply the
    substrate mark and channel ordinal. ``device_active_area_cm2`` is only
    needed when the CSV reports total current instead of current density.
    """

    text = _decode_text(content) if isinstance(content, bytes) else content
    if _looks_like_multi_device_export(text):
        return _parse_multi_device_analysis(text)
    # Simple CSV: the filename is the only source of physical identity.
    mark, ordinal = _identity_from_filename(source_filename)
    points, unit_conversion = _read_points(text, device_active_area_cm2)
    metrics = _metrics_from_points(points)
    label = f"{mark} Channel {ordinal}"
    trace = _trace_record(
        trace_id="trace-001",
        label=f"{label}.Forward",
        direction="forward",
        points=points,
        metrics=metrics,
        measured_at=None,
    )
    device = _device_record(1, label, [trace])
    analysis = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "devices": [device],
        "substrates": _substrate_records([device]),
        # v7 stores no aggregate summaries; the only statistics live in
        # "statistics", recomputed by assign_substrates_to_groups when
        # substrates are grouped and devices excluded.
        "statistics": {},
        "warnings": [],
    }
    if unit_conversion is not None:
        analysis["unit_conversion"] = unit_conversion
    return analysis


def _metrics_from_points(points: list[JVPoint]) -> dict[str, float]:
    if len(points) < 2:
        raise ValueError("JV CSV must contain at least two numeric rows")

    voc = _interpolate_x_at_y_zero(points)
    jsc = _interpolate_y_at_x_zero(points)
    if voc is None:
        raise ValueError("JV CSV must cross zero current to calculate Voc")
    if jsc is None:
        raise ValueError("JV CSV must include or bracket 0 V to calculate Jsc")

    voltage_min, voltage_max = sorted((0.0, voc))
    generating_powers = [
        abs(point.voltage * point.current_density)
        for point in points
        if voltage_min <= point.voltage <= voltage_max
        and point.current_density * jsc >= 0
    ]
    if not generating_powers:
        raise ValueError("JV CSV contains no points in the power-generating quadrant")
    pmax = max(generating_powers)
    denominator = abs(voc * jsc)
    if denominator <= 0:
        raise ValueError("JV CSV produced zero Voc or Jsc, so FF cannot be calculated")

    return {
        "voc": voc,
        "jsc": abs(jsc),
        "ff": pmax / denominator,
        "pce": pmax,
    }


def _looks_like_multi_device_export(text: str) -> bool:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return False
    return (
        any(cell.strip().lower() == "no." for cell in rows[0])
        and any("volt" in cell.strip().lower() for cell in rows[1])
        and any("ma/cm" in cell.strip().lower() for cell in rows[1])
    )


def _parse_multi_device_analysis(text: str) -> dict[str, Any]:
    rows = list(csv.reader(io.StringIO(text)))
    starts = [
        index
        for index, value in enumerate(rows[0])
        if value.strip().lower() == "no."
    ]
    # The per-scan summary table (No., Name, Isc (mA), ...) closes the trace
    # data area. Its numeric columns sit at the same positions as the first
    # blocks' scan-point columns, and failed devices report Isc/Pmax values
    # inside the physical voltage window — only a structural cut at the
    # located header row keeps those numbers out of the curves.
    summary_header = _locate_summary_table(rows)
    data_rows = rows[: summary_header if summary_header is not None else len(rows)]
    summary_scans = (
        _summary_table_metrics(rows, summary_header)
        if summary_header is not None
        else {}
    )
    traces: list[dict[str, Any]] = []
    warnings: list[str] = []
    for block_index, start in enumerate(starts):
        end = starts[block_index + 1] if block_index + 1 < len(starts) else len(rows[0])
        header = rows[1][start:end]
        voltage_offset = next(
            (index for index, value in enumerate(header) if "volt" in value.strip().lower()),
            None,
        )
        current_offset = next(
            (index for index, value in enumerate(header) if "ma/cm" in value.strip().lower()),
            None,
        )
        if voltage_offset is None or current_offset is None:
            continue
        raw_current_offset = next(
            (index for index, value in enumerate(header)
             if value.strip().casefold() == "[current (ma)]"),
            None,
        )
        trace_number = (
            rows[0][start + 1].strip()
            if start + 1 < len(rows[0]) and rows[0][start + 1].strip()
            else str(block_index + 1)
        )
        label = _trace_label(data_rows, start, end, trace_number)
        info = _block_info_rows(data_rows, start, end)
        instrument = _instrument_metrics_from_info(info)
        points: list[JVPoint] = []
        raw_points: list[list[float | None]] = []
        for row in data_rows[2:]:
            padded = row + [""] * max(0, end - len(row))
            try:
                voltage = float(padded[start + voltage_offset].strip())
                current_density = float(padded[start + current_offset].strip())
            except (ValueError, IndexError):
                continue
            if math.isfinite(voltage) and math.isfinite(current_density):
                points.append(JVPoint(voltage=voltage, current_density=current_density))
                # Keep measured current, never infer it from density or area.
                raw_current = None
                if raw_current_offset is not None:
                    try:
                        value = float(padded[start + raw_current_offset].strip())
                        if math.isfinite(value):
                            raw_current = value
                    except (ValueError, IndexError):
                        pass
                raw_points.append([voltage, raw_current, current_density])
        # Metric priority: instrument-reported values are the primary source
        # (the instrument is the calculator; the parser only locates, grabs,
        # and files the values). The trailing summary table wins; the block's
        # [Statistic] section is the fallback; curve recomputation is the
        # last resort for exports without either.
        metric_source: str | None = None
        extra_summary_info: dict[str, str] = {}
        metrics: dict[str, float] | None = None
        error: str | None = None
        summary_key = _summary_scan_key(label)
        summary_entry = _match_summary_scan(summary_key, summary_scans)
        if summary_entry is not None:
            metrics, extra_summary_info = summary_entry
            metric_source = "summary table"
        else:
            section = _statistic_section_metrics(data_rows, start, end)
            if section is not None:
                metrics = section[0]
                metric_source = "[Statistic] section"
            elif instrument is not None:
                metrics = instrument[0]
                metric_source = "info rows"
        if metrics is None:
            try:
                metrics = _metrics_from_points(points)
                metric_source = "recomputed from curve"
            except ValueError as exc:
                metrics = None
                metric_source = None
                error = str(exc)
        else:
            error = None
        if extra_summary_info:
            info = {**extra_summary_info, **info}
        warnings.extend(_irradiance_warnings(label, _irradiance_from_info(info)))
        traces.append(
            _trace_record(
                trace_id=f"trace-{block_index + 1:03d}",
                label=label,
                direction=_trace_direction(label, points),
                points=points,
                metrics=metrics,
                measured_at=_trace_timestamp(data_rows, start, end),
                error=error,
                info=info,
                metric_source=metric_source,
                raw_points=raw_points,
                metadata_rows=_block_metadata_rows(data_rows, start, end),
            )
        )

    valid_traces = [trace for trace in traces if trace["valid"]]
    if not valid_traces:
        raise ValueError("multi-device JV CSV contains no valid JV traces")

    traces_by_device: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        device_label = _device_label(trace["label"])
        traces_by_device.setdefault(device_label, []).append(trace)
    devices = [
        _device_record(index, label, device_traces)
        for index, (label, device_traces) in enumerate(traces_by_device.items(), start=1)
    ]

    # Every parsed device must carry an unambiguous substrate name and channel.
    # A physical laser mark is optional for instrument-named substrates; the
    # student assigns each substrate to a condition after upload.
    seen_keys: set[tuple[str, int]] = set()
    for device in devices:
        if len(LASER_MARK_TOKEN.findall(str(device.get("label", "")))) > 1:
            raise ValueError(
                f"instrument label {device.get('label', '')!r} contains "
                "multiple substrate laser marks"
            )
        mark = device.get("substrate_id")
        if not mark or not str(mark).strip():
            raise ValueError(
                f"instrument label {device.get('label', '')!r} does not "
                "identify a substrate name; use labels like "
                "'A001 Channel 2' or '(Sample-1-2.CH_Ref.Forward(1))'"
            )
        ordinal = device.get("device_ordinal")
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 1
        ):
            raise ValueError(
                f"instrument label {device.get('label', '')!r} for "
                f"substrate {device.get('substrate_id', '')} does not identify "
                "a physical device channel; use labels like "
                "'A001 Channel 2' or '(Sample-1-2.CH_Ref.Forward(1))'"
            )
        mark = device["substrate_id"]
        key = (mark, ordinal)
        if key in seen_keys:
            raise ValueError(
                f"substrate {mark} has duplicate parsed devices for "
                f"channel {ordinal}"
            )
        seen_keys.add(key)

    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "devices": devices,
        "substrates": _substrate_records(devices),
        # v7 stores no aggregate summaries; the only statistics live in
        # "statistics", recomputed by assign_substrates_to_groups when
        # substrates are grouped and devices excluded.
        "statistics": {},
        "warnings": warnings,
    }


def _normalize_legacy_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a stored v5/v6 analysis to the v7 shape (read/re-save time).

    v5 flattened every device to one median metric record and v6 kept the
    first scan per direction; both pre-date the representative-scan rule.
    The per-device directional metrics are rebuilt from the stored traces
    (highest-PCE valid scan per direction). Saved v6 directional values fill
    gaps when traces are unavailable; a v5 flat record remains combined.
    The stored aggregate summaries (``summary`` / ``acquisition_summary``) are v6-era
    derived caches and are dropped: v7 keeps only per-scan records, and any
    pooled view is recomputed from the traces. The database keeps whatever
    it stored; this runs on read and re-save only.
    """

    if analysis.get("schema_version") not in (5, 6):
        return analysis
    migrated = deepcopy(analysis)
    for device in migrated.get("devices", []):
        flat = device.get("metrics")
        directional: dict[str, Any] = {}
        rebuilt = False
        for direction in ("forward", "reverse"):
            best: dict[str, float] | None = None
            for trace in device.get("traces", []):
                if not (trace.get("valid") and trace.get("direction") == direction):
                    continue
                trace_metrics = trace.get("metrics")
                if not isinstance(trace_metrics, Mapping):
                    continue
                candidate = dict(trace_metrics)
                if best is None or _has_higher_pce(candidate, best):
                    best = candidate
            if best is not None:
                directional[direction] = best
                rebuilt = True
        if isinstance(flat, Mapping) and flat:
            if any(name in flat for name in ("forward", "reverse", "combined")):
                for direction in ("forward", "reverse", "combined"):
                    saved = flat.get(direction)
                    if direction not in directional and isinstance(saved, Mapping):
                        directional[direction] = dict(saved)
            else:
                directional["combined"] = dict(flat)
        device["metrics"] = directional if (rebuilt or flat) else None
        device.pop("instrument_metrics", None)
        device.pop("instrument_metric_labels", None)
        for trace in device.get("traces", []):
            trace.pop("instrument_metrics", None)
            trace.pop("instrument_metric_labels", None)
    # v6-era aggregate summaries are derived caches, not measurements.
    migrated.pop("summary", None)
    migrated.pop("acquisition_summary", None)
    migrated["schema_version"] = ANALYSIS_SCHEMA_VERSION
    return migrated


def assign_substrates_to_groups(
    analysis: Mapping[str, Any],
    assignments: Mapping[str, str],
    groups: list[Mapping[str, Any]],
    exclusions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assign every parsed substrate, keeping all of its devices in one group.

    ``exclusions`` optionally maps analysis device ids to a free-text exclusion
    reason. Excluded devices keep their assignment, metrics, and traces for
    provenance, but group statistics and comparisons skip them until the
    analysis is saved again without the exclusion.
    """

    updated = deepcopy(dict(_normalize_legacy_analysis(dict(analysis))))
    group_ids = {str(group["group_id"]) for group in groups}
    substrates = updated.get("substrates")
    if not isinstance(substrates, list) or not substrates:
        substrates = _substrate_records(updated.get("devices", []))
        updated["substrates"] = substrates
    assigned_groups: dict[str, str] = {}
    for substrate in substrates:
        substrate_id = str(substrate["substrate_id"])
        group_id = str(assignments.get(substrate_id, "")).strip()
        if group_id not in group_ids:
            raise ValueError(f"assign substrate {substrate_id} to a control or target group")
        substrate["group_id"] = group_id
        assigned_groups[substrate_id] = group_id
    excluded_reasons = _validated_exclusions(updated.get("devices", []), exclusions)
    for device in updated.get("devices", []):
        device["group_id"] = assigned_groups[str(device["substrate_id"])]
        device_id = str(device["device_id"])
        if device_id in excluded_reasons:
            device["excluded"] = True
            device["exclusion_reason"] = excluded_reasons[device_id]
        else:
            device.pop("excluded", None)
            device.pop("exclusion_reason", None)
    updated["statistics"] = _group_statistics(updated["devices"], groups)
    # v7 stores no aggregate summary rows: every scan stays an individual
    # trace, and any pooled view (including exclusion-aware ones) is
    # recomputed from the traces by whoever needs it.
    return updated


def _validated_exclusions(
    devices: list[Mapping[str, Any]],
    exclusions: Mapping[str, str] | None,
) -> dict[str, str]:
    """Normalize exclusion flags against the parsed devices.

    Every excluded device must exist in the analysis and carry a non-empty
    reason; reasons are bounded to 200 characters.
    """

    if not exclusions:
        return {}
    device_ids = {str(device["device_id"]) for device in devices}
    normalized: dict[str, str] = {}
    for device_id, reason in exclusions.items():
        key = str(device_id)
        if key not in device_ids:
            raise ValueError(f"cannot exclude unknown analysis device {key}")
        text = str(reason).strip()
        if not text:
            raise ValueError(f"excluded analysis device {key} requires a reason")
        normalized[key] = text[:200]
    return normalized


def _trace_label(
    rows: list[list[str]],
    start: int,
    end: int,
    fallback: str,
) -> str:
    for row in rows[2:]:
        padded = row + [""] * max(0, end - len(row))
        if padded[start].strip().lower() == "name" and start + 1 < len(padded):
            label = padded[start + 1].strip()
            if label:
                return label
    return f"Trace {fallback}"


def _trace_timestamp(rows: list[list[str]], start: int, end: int) -> str | None:
    for row in rows[2:]:
        padded = row + [""] * max(0, end - len(row))
        if padded[start].strip().lower() != "time stamp" or start + 1 >= len(padded):
            continue
        value = padded[start + 1].strip()
        for timestamp_format in INSTRUMENT_TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(value, timestamp_format).isoformat()
            except ValueError:
                pass
        return value or None
    return None


def _trace_direction(label: str, points: list[JVPoint]) -> str:
    """Classify the scan direction.

    An explicit Forward/Reverse keyword in the trace label wins. Otherwise
    the sweep direction of the measured voltages decides (rising voltage is
    a forward scan); block order is deliberately not used, because
    multiplexed instruments that sweep all channels forward and then all
    channels reverse would be mislabeled by an even/odd heuristic.
    """

    match = re.search(r"\b(forward|reverse)\b", label, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    if len(points) >= 2 and points[-1].voltage < points[0].voltage:
        return "reverse"
    return "forward"


def _device_label(trace_label: str) -> str:
    label = re.sub(
        r"\.CH_Ref\.(?:Forward|Reverse)\(\d+\)",
        "",
        trace_label,
        flags=re.IGNORECASE,
    )
    label = re.sub(
        r"[._ -](?:Forward|Reverse)(?:\(\d+\))?$",
        "",
        label,
        flags=re.IGNORECASE,
    )
    return label.strip() or trace_label


def _trace_record(
    *,
    trace_id: str,
    label: str,
    direction: str,
    points: list[JVPoint],
    metrics: Mapping[str, float] | None,
    measured_at: str | None,
    error: str | None = None,
    info: Mapping[str, str] | None = None,
    metric_source: str | None = None,
    raw_points: list[list[float | None]] | None = None,
    metadata_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "label": label,
        "direction": direction,
        "measured_at": measured_at,
        "valid": metrics is not None,
        "error": error,
        "metrics": None if metrics is None else dict(metrics),
        "points": [[point.voltage, point.current_density] for point in points],
        "info": dict(info or {}),
        "metadata_rows": metadata_rows or [],
        "raw_data": None if raw_points is None else {
            "columns": ["voltage", "current", "current_density"],
            "units": ["V", "mA", "mA/cm^2"],
            "points": raw_points,
        },
        # Where the metrics came from: "summary table" (instrument's
        # trailing per-scan table), "[Statistic] section" (in-block rows),
        # "info rows", or "recomputed from curve" (fallback only).
        "metric_source": metric_source,
    }


def _has_higher_pce(candidate: Mapping[str, float], current: Mapping[str, float]) -> bool:
    """Whether ``candidate`` beats ``current`` as a direction's representative.

    Strictly higher PCE wins; ties and scans without a comparable PCE keep
    the earlier scan (traces arrive in file order), so the choice is
    deterministic and never fabricates a value.
    """

    candidate_pce = candidate.get("pce")
    current_pce = current.get("pce")
    if not isinstance(candidate_pce, (int, float)) or isinstance(candidate_pce, bool):
        return False
    if not isinstance(current_pce, (int, float)) or isinstance(current_pce, bool):
        return True
    return candidate_pce > current_pce


def _device_record(index: int, label: str, traces: list[dict[str, Any]]) -> dict[str, Any]:
    # Directional metrics (v7): forward and reverse sweeps probe different
    # physics — their divergence (hysteresis) is itself the signal — so the
    # device record keeps, per direction, the instrument-reported metrics of
    # one representative scan and never averages across scans. The
    # representative is the highest-PCE valid scan of that direction — the
    # same scan the UI shows by default; every scan of the device stays in
    # ``traces`` and any future re-selection re-derives from there. A
    # missing direction stays None to keep the record shape stable.
    directional: dict[str, dict[str, float] | None] = {"forward": None, "reverse": None}
    for trace in traces:
        if trace["valid"] and trace["direction"] in directional:
            candidate = dict(trace["metrics"])
            current = directional[trace["direction"]]
            if current is None or _has_higher_pce(candidate, current):
                directional[trace["direction"]] = candidate
    metrics = directional if any(v is not None for v in directional.values()) else None
    # Hysteresis index: relative forward/reverse PCE divergence of the two
    # representative scans (the scans the device record shows), a primary
    # quality diagnostic for perovskites. None when either direction is
    # missing (or invalid) or the reverse PCE is too close to zero to
    # normalize against.
    forward_metrics = directional["forward"]
    reverse_metrics = directional["reverse"]
    hysteresis_index = None
    if forward_metrics and reverse_metrics:
        reverse_pce = reverse_metrics.get("pce")
        forward_pce = forward_metrics.get("pce")
        if (
            reverse_pce is not None
            and forward_pce is not None
            and abs(reverse_pce) > 1e-9
        ):
            hysteresis_index = (reverse_pce - forward_pce) / reverse_pce
    # Reported illumination per trace, when the instrument exported it.
    irradiance_values = [
        value
        for trace in traces
        for value in [_irradiance_from_info(trace.get("info") or {})]
        if value is not None
    ]
    marks = LASER_MARK_TOKEN.findall(label)
    explicit_channel = channel_ordinal_from_label(label)
    # A mark-shaped token inside a free-form instrument name is not by itself
    # proof of a laser mark. Physical association requires both the mark and
    # an explicit Channel N token; otherwise use the instrument suffix.
    physical_identity = len(marks) == 1 and explicit_channel is not None
    device_mark = normalize_laser_mark(marks[0]) if physical_identity else None
    named_identity = None if physical_identity else _instrument_named_identity(label)
    return {
        "device_id": f"device-{index:03d}",
        "label": label,
        "device_mark": device_mark,
        # The physical channel number from the instrument label (e.g. the 2
        # in "A001 Channel 2"); None when the label is ambiguous. Result
        # association binds this ordinal to fabrication_devices.device_ordinal
        # instead of the order traces appear in the file.
        "device_ordinal": explicit_channel if physical_identity else named_identity[1] if named_identity else None,
        # The laser mark is the substrate identity (e.g. A001). The old code
        # truncated to device_mark[:3] for the legacy 2-digit substrate marks;
        # the full mark is now the substrate-level laser mark.
        "substrate_id": device_mark if device_mark else named_identity[0] if named_identity else label,
        "group_id": "",
        "metrics": metrics,
        "hysteresis_index": hysteresis_index,
        "irradiance_sun": (
            statistics.median(irradiance_values) if irradiance_values else None
        ),
        "traces": traces,
    }


def _substrate_records(devices: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for device in devices:
        substrate_id = str(device["substrate_id"])
        row = grouped.setdefault(
            substrate_id,
            {
                "substrate_id": substrate_id,
                "device_ids": [],
                "instrument_labels": [],
                "group_id": "",
            },
        )
        row["device_ids"].append(str(device["device_id"]))
        row["instrument_labels"].append(str(device["label"]))
    return list(grouped.values())


def _device_metric_values(device: Mapping[str, Any], metric_name: str) -> list[float]:
    """Sample values a device contributes to cross-device statistics.

    v6 directional metrics: every valid scan is an independent sample
    (forward and reverse pooled). v5 flat device metrics (migrated
    analyses): the single flat value is the sample.
    """

    metrics = device.get("metrics")
    if not metrics:
        return []
    if "forward" in metrics or "reverse" in metrics or "combined" in metrics:
        values = []
        for direction in ("forward", "reverse"):
            directional = metrics.get(direction)
            if directional and metric_name in directional:
                values.append(float(directional[metric_name]))
        return values
    if metric_name in metrics:
        return [float(metrics[metric_name])]
    return []


def _group_statistics(
    devices: list[Mapping[str, Any]],
    groups: list[Mapping[str, Any]],
) -> dict[str, Any]:
    group_rows = []
    metric_names = ("voc", "jsc", "ff", "pce")
    for group in groups:
        group_id = str(group["group_id"])
        assigned = [device for device in devices if device.get("group_id") == group_id]
        # Excluded devices (flagged outliers with a recorded reason) keep
        # their assignment for provenance but never enter the statistics.
        valid = [
            device
            for device in assigned
            if device.get("metrics") and not device.get("excluded")
        ]
        metric_rows = {}
        for metric_name in metric_names:
            values = [
                value
                for device in valid
                for value in _device_metric_values(device, metric_name)
            ]
            metric_rows[metric_name] = _descriptive_statistics(values)
        group_rows.append(
            {
                "group_id": group_id,
                "name": str(group["name"]),
                "kind": str(group["kind"]),
                "device_count": len(assigned),
                "valid_device_count": len(valid),
                "excluded_device_count": sum(1 for device in assigned if device.get("excluded")),
                "metrics": metric_rows,
            }
        )

    def group_metric_values(group_row: Mapping[str, Any], metric_name: str) -> list[float]:
        return [
            value
            for device in devices
            if device.get("group_id") == group_row["group_id"]
            and device.get("metrics")
            and not device.get("excluded")
            for value in _device_metric_values(device, metric_name)
        ]

    control = next((group for group in group_rows if group["kind"] == "control"), None)
    comparisons = []
    if control is not None:
        for target in (group for group in group_rows if group["kind"] == "target"):
            metric_comparisons = {}
            for metric_name in metric_names:
                control_stats = control["metrics"][metric_name]
                target_stats = target["metrics"][metric_name]
                control_mean = control_stats["mean"]
                target_mean = target_stats["mean"]
                if control_mean is None or target_mean is None:
                    metric_comparisons[metric_name] = None
                    continue
                control_values = group_metric_values(control, metric_name)
                target_values = group_metric_values(target, metric_name)
                difference = target_mean - control_mean
                denominator = _pooled_standard_deviation(
                    control_values,
                    target_values,
                )
                p_value, test_method = _permutation_p_value(
                    control_values,
                    target_values,
                    seed=f"{target['group_id']}:{metric_name}",
                )
                metric_comparisons[metric_name] = {
                    "mean_difference": difference,
                    "percent_difference": (
                        None if control_mean == 0 else difference / abs(control_mean) * 100.0
                    ),
                    "effect_size": None if denominator == 0 else difference / denominator,
                    "p_value": p_value,
                    "adjusted_p_value": None,
                    "test_method": test_method,
                }
            _add_benjamini_hochberg_adjustment(metric_comparisons)
            comparisons.append(
                {
                    "target_group_id": target["group_id"],
                    "target_name": target["name"],
                    "control_name": control["name"],
                    "metrics": metric_comparisons,
                }
            )
    return {"groups": group_rows, "comparisons": comparisons}


def _pooled_standard_deviation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    numerator = (
        (len(left) - 1) * statistics.variance(left)
        + (len(right) - 1) * statistics.variance(right)
    )
    denominator = len(left) + len(right) - 2
    return math.sqrt(numerator / denominator) if numerator > 0 and denominator > 0 else 0.0


def _permutation_p_value(
    control: list[float],
    target: list[float],
    *,
    seed: str,
) -> tuple[float | None, str | None]:
    """Return a two-sided randomization p-value for the difference in means."""

    if len(control) < 2 or len(target) < 2:
        return None, None
    combined = control + target
    control_size = len(control)
    observed = abs(statistics.fmean(target) - statistics.fmean(control))
    total_sum = sum(combined)
    combination_count = math.comb(len(combined), control_size)

    def difference_for(indices: tuple[int, ...] | list[int]) -> float:
        control_sum = sum(combined[index] for index in indices)
        target_sum = total_sum - control_sum
        return abs(
            target_sum / len(target)
            - control_sum / control_size
        )

    tolerance = max(1e-12, observed * 1e-12)
    if combination_count <= 20_000:
        extreme = sum(
            difference_for(indices) >= observed - tolerance
            for indices in itertools.combinations(range(len(combined)), control_size)
        )
        return extreme / combination_count, "exact permutation"

    draw_count = 4_999
    generator = random.Random(seed)
    population = list(range(len(combined)))
    extreme = sum(
        difference_for(generator.sample(population, control_size)) >= observed - tolerance
        for _ in range(draw_count)
    )
    return (extreme + 1) / (draw_count + 1), "Monte Carlo permutation (5,000)"


def _add_benjamini_hochberg_adjustment(
    metric_comparisons: dict[str, dict[str, Any] | None],
) -> None:
    available = sorted(
        (
            (metric_name, values["p_value"])
            for metric_name, values in metric_comparisons.items()
            if values is not None and values.get("p_value") is not None
        ),
        key=lambda item: item[1],
    )
    adjusted: dict[str, float] = {}
    previous = 1.0
    test_count = len(available)
    for rank in range(test_count, 0, -1):
        metric_name, p_value = available[rank - 1]
        previous = min(previous, p_value * test_count / rank)
        adjusted[metric_name] = previous
    for metric_name, value in adjusted.items():
        comparison = metric_comparisons[metric_name]
        if comparison is not None:
            comparison["adjusted_p_value"] = min(1.0, value)


def _descriptive_statistics(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "sd": None,
            "minimum": None,
            "q1": None,
            "q3": None,
            "maximum": None,
        }
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "sd": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "minimum": ordered[0],
        "q1": _percentile(ordered, 0.25),
        "q3": _percentile(ordered, 0.75),
        "maximum": ordered[-1],
    }


def _percentile(ordered: list[float], fraction: float) -> float:
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _read_points(
    text: str, device_active_area_cm2: float | None = None
) -> tuple[list[JVPoint], dict[str, Any] | None]:
    """Read (voltage, current density) pairs from a simple row-based CSV.

    An explicit current-density column is used as-is. A total-current
    column is a different physical quantity: it is accepted only when the
    device active area is known, converted with J = I / A, and the
    conversion is returned for provenance.
    """

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("JV CSV must include a header row")

    voltage_column = _find_column(reader.fieldnames, VOLTAGE_NAMES)
    if voltage_column is None:
        raise ValueError("JV CSV must include a voltage column")
    density_column = _find_column(reader.fieldnames, CURRENT_DENSITY_NAMES)
    raw_current_column = _find_column(reader.fieldnames, set(RAW_CURRENT_NAMES))
    current_to_density_factor: float | None = None
    unit_conversion: dict[str, Any] | None = None
    if density_column is not None:
        current_column = density_column
    elif raw_current_column is not None:
        if device_active_area_cm2 is None or device_active_area_cm2 <= 0:
            raise ValueError(
                "the JV CSV column 'current' reports total current, not "
                "current density; upload a current-density column (mA/cm2) "
                "or select the device layout that supplies the active area "
                "needed to convert J = I / A"
            )
        current_column = raw_current_column
        current_to_density_factor = (
            RAW_CURRENT_NAMES[raw_current_column] / device_active_area_cm2
        )
        unit_conversion = {
            "source_column": raw_current_column,
            "source_unit": "mA" if RAW_CURRENT_NAMES[raw_current_column] == 1.0 else "A",
            "device_active_area_cm2": device_active_area_cm2,
            "converted_to": "mA/cm2",
        }
    else:
        raise ValueError(
            "JV CSV must include a current-density column (mA/cm2); a "
            "total-current column additionally requires the device active "
            "area"
        )

    points: list[JVPoint] = []
    for row_number, row in enumerate(reader, start=2):
        voltage_raw = row.get(voltage_column, "")
        current_raw = row.get(current_column, "")
        try:
            voltage = float(str(voltage_raw).strip())
            current = float(str(current_raw).strip())
        except ValueError as error:
            raise ValueError(f"JV CSV row {row_number} contains a nonnumeric value") from error
        if not math.isfinite(voltage) or not math.isfinite(current):
            raise ValueError(f"JV CSV row {row_number} contains a nonfinite value")
        current_density = (
            current
            if current_to_density_factor is None
            else current * current_to_density_factor
        )
        points.append(JVPoint(voltage=voltage, current_density=current_density))
    return points, unit_conversion


def _find_column(fieldnames: list[str], accepted: set[str]) -> str | None:
    for fieldname in fieldnames:
        normalized = fieldname.strip().lower().replace("/", "_").replace(" ", "_")
        if normalized in accepted or fieldname.strip().lower() in accepted:
            return fieldname
    return None


def _interpolate_y_at_x_zero(points: list[JVPoint]) -> float | None:
    ordered = sorted(points, key=lambda point: point.voltage)
    for point in ordered:
        if point.voltage == 0:
            return point.current_density
    for left, right in zip(ordered, ordered[1:]):
        if left.voltage <= 0 <= right.voltage or right.voltage <= 0 <= left.voltage:
            return _linear_interpolate(0.0, left.voltage, left.current_density, right.voltage, right.current_density)
    return None


def _interpolate_x_at_y_zero(points: list[JVPoint]) -> float | None:
    """Return the conventional Voc: the highest-voltage J = 0 crossing.

    S-kinks, scan overshoot near Voc, and shunt-induced low-voltage
    crossings can make a perovskite curve cross zero current more than
    once; picking the lowest-voltage crossing would understate Voc and
    truncate the power-quadrant search that follows.
    """

    ordered = sorted(points, key=lambda point: point.voltage)
    crossings: list[float] = [
        point.voltage for point in ordered if point.current_density == 0
    ]
    for left, right in zip(ordered, ordered[1:]):
        if left.current_density <= 0 <= right.current_density or right.current_density <= 0 <= left.current_density:
            crossings.append(
                _linear_interpolate(0.0, left.current_density, left.voltage, right.current_density, right.voltage)
            )
    if not crossings:
        return None
    return max(crossings)


def _linear_interpolate(target_x: float, x1: float, y1: float, x2: float, y2: float) -> float:
    if x1 == x2:
        return y1
    fraction = (target_x - x1) / (x2 - x1)
    return y1 + fraction * (y2 - y1)
