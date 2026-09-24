"""Canonical JSON and human-readable PDF exports for fabrication plans."""

from __future__ import annotations

import json
import textwrap
from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any, Iterable, Mapping

from perovskite_bo import ExperimentRecord

from .repository import (
    ConditionRecord,
    SubstrateExceptionRecord,
    FabricationBatchRecord,
    FrozenBatchConditionRecord,
    FabricationSubstrateRecord,
    FabricationDeviceRecord,
    SolutionPreparationRecord,
    ProcessExecutionRecord,
    ExecutionDeviationRecord,
)

PLAN_EXPORT_SCHEMA_VERSION = 3


def build_plan_export(
    experiment: ExperimentRecord,
    conditions: Iterable[ConditionRecord],
    exceptions: Iterable[SubstrateExceptionRecord],
) -> dict[str, Any]:
    """Build the complete versioned payload used by both export formats."""

    condition_values = list(conditions)
    exception_values = list(exceptions)
    return {
        "schema_version": PLAN_EXPORT_SCHEMA_VERSION,
        "experiment": {
            "id": experiment.id,
            "experiment_code": experiment.experiment_code,
            "campaign_id": experiment.campaign_id,
            "series_version": experiment.series_version,
            "plan_type": experiment.plan_type,
            "plan_status": experiment.plan_status,
            "experiment_status": experiment.status.value,
            "created_at": experiment.created_at,
            "updated_at": experiment.updated_at,
            "recipe": experiment.recipe.to_dict(),
        },
        "conditions": [
            {
                "id": item.id,
                "role": item.role.value,
                "condition_code": item.condition_code,
                "condition_name": item.condition_name,
                "recipe_snapshot": item.recipe_snapshot,
                "recipe_schema_version": item.recipe_schema_version,
                "canonical_hash": item.canonical_hash,
                "source_baseline_version_id": item.source_baseline_version_id,
                "device_layout_code": item.device_layout_code,
                "device_layout_snapshot": item.device_layout_snapshot,
                "planned_substrate_count": item.planned_substrate_count,
                "expected_device_count": item.expected_device_count,
                "requires_manual_review": item.requires_manual_review,
                "created_at": _isoformat(item.created_at),
            }
            for item in condition_values
        ],
        "substrate_exceptions": [
            {
                "id": item.id,
                "condition_id": item.condition_id,
                "requested_count": item.requested_count,
                "reason": item.reason,
                "requested_by_id": item.requested_by_id,
                "requested_at": _isoformat(item.requested_at),
                "decision": item.decision.value,
                "decided_by_id": item.decided_by_id,
                "decided_at": _isoformat(item.decided_at),
                "decision_note": item.decision_note,
                "approved_condition_hash": item.approved_condition_hash,
            }
            for item in exception_values
        ],
    }


def canonical_plan_json(payload: Mapping[str, Any], *, pretty: bool = True) -> bytes:
    """Serialize without NaN or implementation-specific values."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def render_plan_pdf(payload: Mapping[str, Any]) -> bytes:
    """Render a concise plan plus a complete configuration appendix."""

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output = BytesIO()
    experiment = dict(payload.get("experiment", {}))
    conditions = list(payload.get("conditions", []))
    code = str(experiment.get("experiment_code") or f"experiment-{experiment.get('id')}")
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=_pdf_safe(f"Fabrication plan {code}"),
        author="Perovskite Solar Cell Fabrication Workflow",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="PlanTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="JsonAppendix",
        fontName="Courier",
        fontSize=5.7,
        leading=7,
    ))
    story: list[Any] = [
        Paragraph(_html(code), styles["PlanTitle"]),
        Paragraph(
            _html(
                f"Campaign: {experiment.get('campaign_id') or 'unassigned'} | "
                f"Plan type: {experiment.get('plan_type') or 'legacy'} | "
                f"Plan status: {experiment.get('plan_status') or 'legacy'}"
            ),
            styles["BodyText"],
        ),
        Spacer(1, 7 * mm),
        Paragraph("Conditions", styles["Heading2"]),
    ]
    condition_table = [[
        "Code", "Role", "Name", "Layout", "Substrates", "Devices"
    ]]
    for condition in conditions:
        condition_table.append([
            _pdf_safe(condition.get("condition_code")),
            _pdf_safe(condition.get("role")),
            _pdf_safe(condition.get("condition_name")),
            _pdf_safe(condition.get("device_layout_code")),
            str(condition.get("planned_substrate_count", "")),
            str(condition.get("expected_device_count", "")),
        ])
    table = Table(
        condition_table,
        repeatRows=1,
        colWidths=[29 * mm, 20 * mm, 43 * mm, 34 * mm, 23 * mm, 20 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([table, Spacer(1, 6 * mm)])

    for condition in conditions:
        snapshot = condition.get("recipe_snapshot", {})
        device = snapshot.get("device", {}) if isinstance(snapshot, Mapping) else {}
        layers = device.get("layers", []) if isinstance(device, Mapping) else []
        layer_text = " / ".join(
            str(layer.get("name") or layer.get("layer_type") or "?")
            for layer in layers
            if isinstance(layer, Mapping)
        )
        story.append(KeepTogether([
            Paragraph(
                _html(f"{condition.get('condition_code')} — {condition.get('condition_name')}"),
                styles["Heading3"],
            ),
            Paragraph(_html(f"Layer sequence: {layer_text or 'not recorded'}"), styles["BodyText"]),
            Paragraph(
                _html(f"Configuration hash: {condition.get('canonical_hash', '')}"),
                styles["BodyText"],
            ),
            Spacer(1, 3 * mm),
        ]))

    story.extend([
        PageBreak(),
        Paragraph("Complete configuration appendix", styles["Heading2"]),
        Paragraph(
            "The JSON export is the authoritative machine-readable record. "
            "This appendix mirrors that payload for inspection.",
            styles["BodyText"],
        ),
        Spacer(1, 3 * mm),
        Preformatted(_wrapped_ascii_json(payload), styles["JsonAppendix"]),
    ])
    document.build(story)
    return output.getvalue()


def _wrapped_ascii_json(payload: Mapping[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2)
    wrapped: list[str] = []
    for line in text.splitlines():
        wrapped.extend(textwrap.wrap(
            line,
            width=105,
            replace_whitespace=False,
            drop_whitespace=False,
            subsequent_indent="  ",
        ) or [""])
    return "\n".join(wrapped)


def _html(value: Any) -> str:
    return escape(_pdf_safe(value))


def _pdf_safe(value: Any) -> str:
    text = str("" if value is None else value)
    replacements = {
        "×": "x",
        "²": "2",
        "₂": "2",
        "°": " deg",
        "—": "-",
        "–": "-",
        "→": "->",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text.encode("latin-1", "replace").decode("latin-1")


def _isoformat(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


BATCH_EXPORT_SCHEMA_VERSION = 5


def build_batch_export(
    batch: FabricationBatchRecord,
    conditions: Iterable[FrozenBatchConditionRecord],
    substrates: Iterable[FabricationSubstrateRecord],
    devices: Iterable[FabricationDeviceRecord],
    preparations: Iterable[SolutionPreparationRecord],
    preparation_uses: Iterable[Mapping[str, Any]],
    executions: Iterable[ProcessExecutionRecord],
    execution_members: Iterable[Mapping[str, Any]],
    deviations: Iterable[ExecutionDeviationRecord],
    results: Iterable[Mapping[str, Any]],
    result_assignments: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the complete versioned batch execution export payload."""
    return {
        "schema_version": BATCH_EXPORT_SCHEMA_VERSION,
        "batch": {
            "id": batch.id,
            "experiment_id": batch.experiment_id,
            "batch_number": batch.batch_number,
            "batch_code": batch.batch_code,
            "status": batch.status.value,
            "condition_set_hash": batch.condition_set_hash,
            "notes": batch.notes,
            "created_by_id": batch.created_by_id,
            "created_at": _isoformat(batch.created_at),
            "updated_at": _isoformat(batch.updated_at),
            "started_at": _isoformat(batch.started_at),
            "completed_at": _isoformat(batch.completed_at),
            "cancelled_at": _isoformat(batch.cancelled_at),
        },
        "frozen_conditions": [
            {
                "id": c.id,
                "source_condition_id": c.source_condition_id,
                "condition_code": c.condition_code,
                "condition_name": c.condition_name,
                "role": c.role,
                "source_condition_hash": c.source_condition_hash,
                "recipe_snapshot": c.recipe_snapshot,
                "recipe_schema_version": c.recipe_schema_version,
                "device_layout_code": c.device_layout_code,
                "device_layout_snapshot": c.device_layout_snapshot,
                "planned_substrate_count": c.planned_substrate_count,
                "expected_device_count": c.expected_device_count,
            }
            for c in conditions
        ],
        "substrates": [
            {
                "id": s.id,
                "batch_condition_id": s.batch_condition_id,
                "substrate_ordinal": s.substrate_ordinal,
                "substrate_code": s.substrate_code,
                "substrate_mark": s.substrate_mark,
                "status": s.status.value,
                "notes": s.notes,
                "created_at": _isoformat(s.created_at),
                "updated_at": _isoformat(s.updated_at),
            }
            for s in substrates
        ],
        "devices": [
            {
                "id": d.id,
                "substrate_id": d.substrate_id,
                "device_ordinal": d.device_ordinal,
                "device_code": d.device_code,
                "device_mark": d.device_mark,
                "device_active_area_cm2": d.device_active_area_cm2,
                "status": d.status.value,
                "notes": d.notes,
                "created_at": _isoformat(d.created_at),
                "updated_at": _isoformat(d.updated_at),
            }
            for d in devices
        ],
        "characterization_results": [
            {
                "id": result["id"],
                "filename": result["filename"],
                "content_type": result["content_type"],
                "size_bytes": result["size_bytes"],
                "sha256": result["sha256"],
                "analysis_schema_version": result["analysis_schema_version"],
                "analysis": result["analysis"],
                "metrics": result["metrics"],
                "group_assignment": result["group_assignment"],
                "uploaded_at": result["created_at"],
            }
            for result in results
        ],
        "result_device_assignments": [
            {
                **dict(assignment),
                "created_at": _isoformat(assignment.get("created_at")),
            }
            for assignment in result_assignments
        ],
        "solution_preparations": [
            {
                "id": p.id,
                "fabrication_batch_id": p.fabrication_batch_id,
                "preparation_code": p.preparation_code,
                "status": p.status.value,
                "planned_solution_snapshot": p.planned_solution_snapshot,
                "planned_snapshot_schema_version": p.planned_snapshot_schema_version,
                "planned_canonical_hash": p.planned_canonical_hash,
                "actual_solution_snapshot": p.actual_solution_snapshot,
                "actual_snapshot_schema_version": p.actual_snapshot_schema_version,
                "actual_canonical_hash": p.actual_canonical_hash,
                "actual_recording_mode": p.actual_recording_mode,
                "prepared_by_id": p.prepared_by_id,
                "prepared_at": _isoformat(p.prepared_at),
                "completed_at": _isoformat(p.completed_at),
                "notes": p.notes,
                "created_at": _isoformat(p.created_at),
                "updated_at": _isoformat(p.updated_at),
            }
            for p in preparations
        ],
        "solution_preparation_uses": [
            {
                "id": int(item["id"]),
                "solution_preparation_id": int(item["solution_preparation_id"]),
                "batch_condition_id": int(item["batch_condition_id"]),
                "layer_ordinal": int(item["layer_ordinal"]),
                "layer_role": str(item["layer_role"]),
                "layer_type": str(item["layer_type"]),
                "layer_snapshot_hash": str(item["layer_snapshot_hash"]),
            }
            for item in preparation_uses
        ],
        "process_executions": [
            {
                "id": e.id,
                "fabrication_batch_id": e.fabrication_batch_id,
                "execution_code": e.execution_code,
                "method": e.method,
                "layer_role": e.layer_role,
                "layer_type": e.layer_type,
                "layer_name": e.layer_name,
                "status": e.status.value,
                "is_shared": e.is_shared,
                "planned_process_snapshot": e.planned_process_snapshot,
                "planned_snapshot_schema_version": e.planned_snapshot_schema_version,
                "planned_canonical_hash": e.planned_canonical_hash,
                "actual_process_snapshot": e.actual_process_snapshot,
                "actual_snapshot_schema_version": e.actual_snapshot_schema_version,
                "actual_canonical_hash": e.actual_canonical_hash,
                "actual_recording_mode": e.actual_recording_mode,
                "equipment_identifier": e.equipment_identifier,
                "executed_by_id": e.executed_by_id,
                "started_at": _isoformat(e.started_at),
                "completed_at": _isoformat(e.completed_at),
                "notes": e.notes,
                "created_at": _isoformat(e.created_at),
                "updated_at": _isoformat(e.updated_at),
            }
            for e in executions
        ],
        "process_execution_members": [
            {
                "id": int(item["id"]),
                "process_execution_id": int(item["process_execution_id"]),
                "substrate_id": int(item["substrate_id"]),
                "batch_condition_id": int(item["batch_condition_id"]),
                "layer_ordinal": int(item["layer_ordinal"]),
                "layer_snapshot_hash": str(item["layer_snapshot_hash"]),
            }
            for item in execution_members
        ],
        "deviations": [
            {
                "id": d.id,
                "category": d.category,
                "severity": d.severity,
                "description": d.description,
                "planned_value": d.planned_value,
                "actual_value": d.actual_value,
                "recorded_by_id": d.recorded_by_id,
                "recorded_at": _isoformat(d.recorded_at),
                "supersedes_deviation_id": d.supersedes_deviation_id,
                "solution_preparation_id": d.solution_preparation_id,
                "process_execution_id": d.process_execution_id,
                "substrate_id": d.substrate_id,
                "device_id": d.device_id,
                "created_at": _isoformat(d.created_at),
            }
            for d in deviations
        ],
    }


def canonical_batch_json(payload: Mapping[str, Any], *, pretty: bool = True) -> bytes:
    """Serialize without NaN or implementation-specific values."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ).encode("utf-8")


def render_batch_pdf(payload: Mapping[str, Any]) -> bytes:
    """Render a human-readable batch traveler with the complete JSON appendix."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output = BytesIO()
    batch = dict(payload.get("batch", {}))
    code = str(batch.get("batch_code") or f"batch-{batch.get('id')}")
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=_pdf_safe(f"Fabrication batch traveler {code}"),
        author="Perovskite Solar Cell Fabrication Workflow",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="BatchAppendix",
        fontName="Courier",
        fontSize=5.4,
        leading=6.6,
    ))
    story: list[Any] = [
        Paragraph(_html(f"Fabrication batch traveler — {code}"), styles["Title"]),
        Paragraph(
            _html(
                f"Status: {batch.get('status')} | "
                f"Condition-set hash: {batch.get('condition_set_hash')}"
            ),
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
    ]

    def add_table(title: str, headings: list[str], rows: list[list[Any]]) -> None:
        story.append(Paragraph(_html(title), styles["Heading2"]))
        values = [headings] + [[_pdf_safe(value) for value in row] for row in rows]
        table = Table(values, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ]))
        story.extend([table, Spacer(1, 4 * mm)])

    conditions = list(payload.get("frozen_conditions", []))
    add_table(
        "Frozen conditions",
        ["Code", "Role", "Layout", "Substrates", "Devices", "Source hash"],
        [
            [
                item.get("condition_code"),
                item.get("role"),
                item.get("device_layout_code"),
                item.get("planned_substrate_count"),
                item.get("expected_device_count"),
                str(item.get("source_condition_hash", ""))[:16],
            ]
            for item in conditions
        ],
    )
    add_table(
        "Solution preparations",
        ["Code", "Status", "Uses", "Actual recorded", "Planned hash"],
        [
            [
                item.get("preparation_code"),
                item.get("status"),
                sum(
                    use.get("solution_preparation_id") == item.get("id")
                    for use in payload.get("solution_preparation_uses", [])
                ),
                "yes" if item.get("actual_solution_snapshot") is not None else "no",
                str(item.get("planned_canonical_hash", ""))[:16],
            ]
            for item in payload.get("solution_preparations", [])
        ],
    )
    add_table(
        "Process executions",
        ["Code", "Method", "Layer", "Status", "Members", "Equipment"],
        [
            [
                item.get("execution_code"),
                item.get("method"),
                item.get("layer_name"),
                item.get("status"),
                sum(
                    member.get("process_execution_id") == item.get("id")
                    for member in payload.get("process_execution_members", [])
                ),
                item.get("equipment_identifier") or "",
            ]
            for item in payload.get("process_executions", [])
        ],
    )
    add_table(
        "Deviations",
        ["ID", "Category", "Severity", "Description", "Supersedes"],
        [
            [
                item.get("id"),
                item.get("category"),
                item.get("severity"),
                item.get("description"),
                item.get("supersedes_deviation_id") or "",
            ]
            for item in payload.get("deviations", [])
        ],
    )
    story.extend([
        PageBreak(),
        Paragraph("Complete execution configuration appendix", styles["Heading2"]),
        Paragraph(
            "The JSON export is authoritative; this appendix mirrors the same payload.",
            styles["BodyText"],
        ),
        Spacer(1, 3 * mm),
        Preformatted(_wrapped_ascii_json(payload), styles["BatchAppendix"]),
    ])
    document.build(story)
    return output.getvalue()
