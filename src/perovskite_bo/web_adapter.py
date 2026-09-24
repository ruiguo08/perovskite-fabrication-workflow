"""Read-only extraction of BO training rows from web PostgreSQL data.

The web app stores, per batch condition, a frozen recipe snapshot (including the
spin/VCD/anneal deposition process) and, once result CSVs are associated, the
measured per-device J-V metrics. This adapter maps a condition onto the shared
BO search space (:func:`default_search_space`) and aggregates the device
metrics into a ``(X, y)`` training row per condition.

``web`` imports ``perovskite_bo`` and never the reverse, so this module only uses
the core package and stdlib. Callers fetch raw rows from the web database and hand
them in; nothing here fabricates missing values.
"""

from __future__ import annotations

from statistics import fmean, median
from typing import Any, Mapping, Sequence

from .search_space import (
    ChoiceParameter,
    IntegerParameter,
    SearchSpace,
)

DEFAULT_WEB_CAMPAIGN_ID = "usual_v1"


def default_search_space() -> SearchSpace:
    """Return the deposition-only Bayesian search space.

    VCD pressure uses integer Pa so laboratory setpoints such as 150 Pa are
    representable without duplicating a differently scaled mbar field.
    """

    return SearchSpace(
        [
            IntegerParameter("spin_cast_rpm", 500, 1_000),
            IntegerParameter("spin_cast_seconds", 60, 60),
            IntegerParameter("spin_cast_acceleration_rpm_per_s", 100, 1_000),
            IntegerParameter("spin_spread_rpm", 1_000, 3_000),
            IntegerParameter("spin_spread_seconds", 5, 20),
            IntegerParameter("spin_spread_acceleration_rpm_per_s", 100, 2_000),
            IntegerParameter("spin_thin_rpm", 3_000, 6_000),
            IntegerParameter("spin_thin_seconds", 10, 40),
            IntegerParameter("spin_thin_acceleration_rpm_per_s", 100, 3_000),
            ChoiceParameter("vcd_stage1_valve", ["VV02", "VV03", "VV06"]),
            IntegerParameter("vcd_stage1_pressure_pa", 1, 1_000),
            IntegerParameter("vcd_stage1_seconds", 5, 60),
            ChoiceParameter("vcd_stage2_valve", ["VV02", "VV03", "VV06"]),
            IntegerParameter("vcd_stage2_pressure_pa", 1, 1_000),
            IntegerParameter("vcd_stage2_seconds", 5, 60),
            ChoiceParameter("vcd_stage3_valve", ["VV02", "VV03", "VV06"]),
            IntegerParameter("vcd_stage3_pressure_pa", 1, 1_000),
            IntegerParameter("vcd_stage3_seconds", 5, 60),
            IntegerParameter("anneal_stage1_temperature_c", 90, 150),
            IntegerParameter("anneal_stage1_seconds", 300, 1_800),
        ]
    )


def bo_parameter_names() -> frozenset[str]:
    """Return the fields changed by BO; all other recipe data is campaign-fixed."""

    return frozenset(parameter.name for parameter in default_search_space().parameters)

# (search-space name, process container, step index, process field name).
# Mirrors default_search_space(): a 3-step spin coat, a 3-stage VCD, and a
# 2-step anneal (only the first anneal step is tuned).
_FEATURE_SPECS: tuple[tuple[str, str, int, str], ...] = (
    ("spin_cast_rpm", "spin_steps", 0, "rpm"),
    ("spin_cast_seconds", "spin_steps", 0, "seconds"),
    ("spin_cast_acceleration_rpm_per_s", "spin_steps", 0, "acceleration_rpm_per_s"),
    ("spin_spread_rpm", "spin_steps", 1, "rpm"),
    ("spin_spread_seconds", "spin_steps", 1, "seconds"),
    ("spin_spread_acceleration_rpm_per_s", "spin_steps", 1, "acceleration_rpm_per_s"),
    ("spin_thin_rpm", "spin_steps", 2, "rpm"),
    ("spin_thin_seconds", "spin_steps", 2, "seconds"),
    ("spin_thin_acceleration_rpm_per_s", "spin_steps", 2, "acceleration_rpm_per_s"),
    ("vcd_stage1_valve", "vcd_stages", 0, "valve"),
    ("vcd_stage1_pressure_pa", "vcd_stages", 0, "pressure_pa"),
    ("vcd_stage1_seconds", "vcd_stages", 0, "seconds"),
    ("vcd_stage2_valve", "vcd_stages", 1, "valve"),
    ("vcd_stage2_pressure_pa", "vcd_stages", 1, "pressure_pa"),
    ("vcd_stage2_seconds", "vcd_stages", 1, "seconds"),
    ("vcd_stage3_valve", "vcd_stages", 2, "valve"),
    ("vcd_stage3_pressure_pa", "vcd_stages", 2, "pressure_pa"),
    ("vcd_stage3_seconds", "vcd_stages", 2, "seconds"),
    ("anneal_stage1_temperature_c", "anneal_steps", 0, "temperature_c"),
    ("anneal_stage1_seconds", "anneal_steps", 0, "seconds"),
)
_PARAMETER_NAMES = tuple(spec[0] for spec in _FEATURE_SPECS)
_METRIC_NAMES = ("voc", "jsc", "ff", "pce")


def search_space_parameter_names() -> tuple[str, ...]:
    """Return the BO parameter names, in default_search_space order.

    Used by callers to verify a features dict lines up with the web search
    space without importing ``web`` from the core package.
    """

    return _PARAMETER_NAMES


def extract_condition_features(
    recipe_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Map a condition recipe snapshot onto the web BO search space.

    Returns one key per search-space parameter. A step that is absent from the
    stored recipe (e.g. a 2-spin recipe has no ``spin_thin_*``) maps to ``None``
    rather than an invented value; a present field is returned unchanged.
    """

    process = (
        recipe_snapshot.get("deposition_process")
        if isinstance(recipe_snapshot, Mapping)
        else None
    )
    if not isinstance(process, Mapping):
        return {name: None for name in _PARAMETER_NAMES}
    features: dict[str, Any] = {}
    for name, container_key, index, field in _FEATURE_SPECS:
        container = process.get(container_key)
        if isinstance(container, Sequence) and not isinstance(container, (str, bytes)):
            step = container[index] if index < len(container) else None
            value = step.get(field) if isinstance(step, Mapping) else None
        else:
            value = None
        features[name] = value
    return features


# Which execution method supplies which search-space container.
_METHOD_BY_CONTAINER = {
    "spin_steps": "spin_coating",
    "vcd_stages": "vcd",
    "anneal_steps": "annealing",
}


def recorded_actual_methods(actual_snapshots_by_method: Mapping[str, Any]) -> frozenset[str]:
    """Methods whose actual process snapshot was recorded for a condition."""

    return frozenset(
        method
        for method in ("spin_coating", "vcd", "annealing")
        if isinstance(actual_snapshots_by_method.get(method), Mapping)
    )


def training_parameter_methods() -> dict[str, str]:
    """Map each search-space parameter to the execution method supplying it."""

    return {
        spec[0]: _METHOD_BY_CONTAINER[spec[1]] for spec in _FEATURE_SPECS
    }


def extract_actual_process_features(
    actual_snapshots_by_method: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Map recorded *actual* perovskite process snapshots onto the search space.

    ``actual_snapshots_by_method`` maps execution method (``spin_coating``,
    ``vcd``, ``annealing``) to the recorded actual process snapshot of the
    perovskite-layer execution. Returns ``None`` when no recognized method is
    present; parameters the recorded snapshots do not supply map to ``None``,
    mirroring :func:`extract_condition_features`.
    """

    combined: dict[str, Any] = {}
    for method, container_key in (
        ("spin_coating", "spin_steps"),
        ("vcd", "vcd_stages"),
        ("annealing", "anneal_steps"),
    ):
        snapshot = actual_snapshots_by_method.get(method)
        if isinstance(snapshot, Mapping):
            combined[container_key] = snapshot.get(container_key)
    if not combined:
        return None
    features: dict[str, Any] = {}
    for name, container_key, index, field in _FEATURE_SPECS:
        container = combined.get(container_key)
        if isinstance(container, Sequence) and not isinstance(container, (str, bytes)):
            step = container[index] if index < len(container) else None
            value = step.get(field) if isinstance(step, Mapping) else None
        else:
            value = None
        features[name] = value
    return features


def extract_result_metrics(
    device_metrics: Sequence[Mapping[str, Any] | None],
) -> dict[str, Any] | None:
    """Aggregate per-device J-V metrics into one condition-level summary.

    Each entry is a parsed device metric dict with ``voc``/``jsc``/``ff``/``pce``
    (the values are taken as-is; no conversion is applied) and optionally a
    ``hysteresis_index``. Returns ``None`` when no device carries usable
    metrics, so an unmeasured condition is distinguishable from a fabricated
    zero. Summary keys mirror the metric set used elsewhere in the tooling:
    medians per metric plus ``pce_mean``, ``pce_best``, and the median
    ``hysteresis_index`` (``None`` when no device reports one).
    """

    usable = [
        entry
        for entry in device_metrics
        if isinstance(entry, Mapping)
        and any(
            isinstance(entry.get(name), (int, float))
            for name in _METRIC_NAMES
        )
    ]
    if not usable:
        return None
    summary: dict[str, Any] = {"device_count": len(usable)}
    for name in _METRIC_NAMES:
        values = [
            entry[name] for entry in usable if isinstance(entry.get(name), (int, float))
        ]
        summary[name] = median(values) if values else None
    pce_values = [
        entry["pce"] for entry in usable if isinstance(entry.get("pce"), (int, float))
    ]
    if pce_values:
        summary["pce_mean"] = fmean(pce_values)
        summary["pce_best"] = max(pce_values)
    else:
        summary["pce_mean"] = None
        summary["pce_best"] = None
    hysteresis_values = [
        float(entry["hysteresis_index"])
        for entry in usable
        if isinstance(entry.get("hysteresis_index"), (int, float))
    ]
    summary["hysteresis_index"] = (
        median(hysteresis_values) if hysteresis_values else None
    )
    return summary


def build_training_rows(
    condition_rows: Sequence[Mapping[str, Any]],
    *,
    device_metrics_by_condition: Mapping[int, Sequence[Mapping[str, Any] | None]],
) -> list[dict[str, Any]]:
    """Assemble one ``(X, y)`` training row per batch condition.

    ``condition_rows`` are web ``fabrication_batch_conditions`` mappings carrying
    at least ``id``, ``condition_code``, ``condition_name`` and ``recipe_snapshot``.
    ``device_metrics_by_condition`` maps a condition id to the metric dicts of the
    devices measured for it. Rows keep the web condition ids so a caller can join
    back to batches and experiments.
    """

    rows: list[dict[str, Any]] = []
    for condition in condition_rows:
        condition_id = int(condition["id"])
        rows.append(
            {
                "batch_condition_id": condition_id,
                "condition_code": str(condition.get("condition_code", "")),
                "condition_name": str(condition.get("condition_name", "")),
                "features": extract_condition_features(condition.get("recipe_snapshot")),
                "metrics": extract_result_metrics(
                    device_metrics_by_condition.get(condition_id, [])
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Training-export self-description
# ---------------------------------------------------------------------------

TRAINING_EXPORT_SCHEMA_VERSION = 2

# The 1-sun assumption is a property of the metric computation (PCE equals the
# maximum power density in mW/cm2), not of the data, so it is declared here
# instead of being silently baked in.
_TRAINING_METRIC_UNITS: dict[str, str] = {
    "device_count": "count",
    "voc": "V",
    "jsc": "mA/cm2",
    "ff": "fraction (0-1)",
    "pce": "percent of 1 sun (mW/cm2 at 1 sun)",
    "pce_mean": "percent of 1 sun (mW/cm2 at 1 sun)",
    "pce_best": "percent of 1 sun (mW/cm2 at 1 sun)",
    "hysteresis_index": "dimensionless, (PCE_reverse - PCE_forward) / PCE_reverse",
}


def _feature_units() -> dict[str, str]:
    units: dict[str, str] = {}
    for name in _PARAMETER_NAMES:
        if name.endswith("_acceleration_rpm_per_s"):
            units[name] = "rpm/s"
        elif name.endswith("_rpm"):
            units[name] = "rpm"
        elif name.endswith("_seconds"):
            units[name] = "s"
        elif name.endswith("_pressure_pa"):
            units[name] = "Pa"
        elif name.endswith("_temperature_c"):
            units[name] = "degC"
        elif name.endswith("_valve"):
            units[name] = "nominal valve identifier"
        else:
            units[name] = "unspecified"
    return units


def training_export_header() -> dict[str, Any]:
    """Return the self-description block that leads every training export.

    Declares the export schema version, the field lists, the units of every
    feature and metric, and the measurement assumptions a downstream consumer
    (Bayesian optimization or any other analysis) must know about.
    """

    metric_fields = [
        "device_count",
        *_METRIC_NAMES,
        "pce_mean",
        "pce_best",
        "hysteresis_index",
    ]
    return {
        "record_type": "header",
        "export_schema_version": TRAINING_EXPORT_SCHEMA_VERSION,
        "feature_fields": list(_PARAMETER_NAMES),
        "metric_fields": metric_fields,
        "units": {**_feature_units(), **_TRAINING_METRIC_UNITS},
        "notes": [
            "Metrics are computed from raw J-V curves assuming 1 sun "
            "(100 mW/cm2) AM1.5G illumination; uploads whose instrument-"
            "reported illumination deviates from 1 sun carry analysis-level "
            "warnings and the metrics are not rescaled.",
            "Devices flagged excluded with a recorded reason are filtered "
            "from the metrics; excluded_device_count reports how many per row.",
            "Feature values are None where the frozen recipe snapshot has no "
            "such step (e.g. a two-spin recipe has no spin_thin_* fields); "
            "impute or drop rows downstream.",
            "feature_source marks where X values come from: 'actual' when "
            "every parameter is taken from recorded per-substrate execution "
            "snapshots, 'mixed' when missing actual parameters were filled "
            "from the frozen plan, and 'planned' when no actual snapshots "
            "were recorded. Rows whose conditions were executed under more "
            "than one actual parameter variant are split per variant and "
            "carry the substrate_ids measured under that variant.",
        ],
    }