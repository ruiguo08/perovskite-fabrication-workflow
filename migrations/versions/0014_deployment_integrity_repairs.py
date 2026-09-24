"""Deployment integrity repairs: typed condition deviations.

Gives execution deviations an explicit semantic type so workflow gates can
require the matching declaration instead of accepting any deviation row:

- ``general``: operator-recorded process/material/equipment/... notes.
- ``fabrication_shortfall``: fewer substrates were made than planned
  (recorded atomically with batch completion).
- ``measurement_shortfall``: substrates were made but not measured
  (required when a result CSV covers fewer substrates than the actual count).

Also corrects the single-target check so ``condition_id`` participates in
the at-most-one-target sum: previously a deviation could combine a condition
with another execution entity at the database level.

Forward data repairs (both idempotent):

- Batches completed before 0013 existed never recorded actual substrate
  counts; those conditions backfill ``planned_substrate_count`` as the
  documented conservative historical value. Draft/ready/in-progress batches
  are left null (no count is fabricated for them).
- Legacy result analyses written by the pre-0013 parser carried a truncated
  3-character substrate id (e.g. ``A01``) while their devices held the full
  factory mark (``A011``). Where every device of a substrate agrees on one
  valid full mark whose 3-character prefix is exactly the stored id, the
  substrate collection, the device references, and the persisted
  ``result_device_assignments.analysis_substrate_id`` are rewritten to the
  full mark without losing group/condition assignment fields. Ambiguous or
  unmatched rows are left unchanged (see DEPLOYMENT.md for the operator
  query that counts them).

Revision ID: 0014_deployment_integrity_repairs
Revises: 0013_substrate_laser_marks
Create Date: 2026-08-22
"""

from __future__ import annotations

import json
import re

from alembic import op
import sqlalchemy as sa

revision = "0014_deployment_integrity_repairs"
down_revision = "0013_substrate_laser_marks"
branch_labels = None
depends_on = None

_FULL_MARK = re.compile(r"^[A-Z][0-9]{3,8}$")
_CHANNEL = re.compile(r"\bchannel\s*#?\s*([0-9]+)", re.IGNORECASE)


def _repair_legacy_analysis(document: object) -> tuple[object, bool, dict[str, str]]:
    """Rewrite unambiguous legacy analyses to schema 3.

    Returns ``(document, changed, mapping)`` where mapping is
    ``{old_substrate_id: full_mark}``.  Only when **every** device carries
    an unambiguous full laser mark **and** an explicit channel ordinal, and
    the old→new substrate ID mapping is **1-to-1** (no two old IDs map to
    the same full mark, no old ID maps to multiple marks), do we:
    - write ``device_ordinal`` on each device,
    - rebuild the substrate grouping by full mark,
    - bump ``schema_version`` to 3.

    Otherwise the analysis is left at schema 2 and ``mapping`` is empty.
    """

    if not isinstance(document, dict):
        return document, False, {}
    devices = document.get("devices")
    if not isinstance(devices, list) or not devices:
        return document, False, {}

    repaired_devices: list[dict[str, Any]] = []
    for device in devices:
        if not isinstance(device, dict):
            return document, False, {}
        label = str(device.get("label", ""))
        mark = str(device.get("device_mark", "")).strip().upper()
        if not _FULL_MARK.match(mark):
            return document, False, {}
        channel_matches = _CHANNEL.findall(label)
        if len(channel_matches) != 1:
            return document, False, {}
        ordinal = int(channel_matches[0])
        if ordinal < 1:
            return document, False, {}
        repaired = dict(device)
        repaired["device_ordinal"] = ordinal
        repaired["substrate_id"] = mark
        repaired_devices.append(repaired)

    # Rebuild substrates grouped by full mark.
    grouped: dict[str, dict[str, Any]] = {}
    for device in repaired_devices:
        sid = device["substrate_id"]
        row = grouped.setdefault(
            sid,
            {
                "substrate_id": sid,
                "device_ids": [],
                "instrument_labels": [],
                "group_id": "",
            },
        )
        row["device_ids"].append(str(device.get("device_id", "")))
        row["instrument_labels"].append(str(device.get("label", "")))

    # Build old→new substrate ID mapping and preserve group fields.
    # The mapping must be 1-to-1: if any old_id maps to multiple full marks
    # (e.g. "A01" prefix of both "A011" and "A012"), the analysis is
    # ambiguous and must stay at schema 2.
    mapping: dict[str, str] = {}
    old_substrates = document.get("substrates")
    if isinstance(old_substrates, list):
        for old_substrate in old_substrates:
            if not isinstance(old_substrate, dict):
                continue
            old_id = str(old_substrate.get("substrate_id", ""))
            matches = [
                fm for fm in grouped
                if fm[:3] == old_id or fm == old_id
            ]
            if len(matches) != 1:
                return document, False, {}
            full_mark = matches[0]
            if old_id in mapping and mapping[old_id] != full_mark:
                return document, False, {}
            mapping[old_id] = full_mark
            new_substrate = grouped[full_mark]
            if "group_id" in old_substrate:
                new_substrate["group_id"] = old_substrate["group_id"]
            for key in ("batch_condition_id", "condition_code", "condition_name"):
                if key in old_substrate:
                    new_substrate[key] = old_substrate[key]

    document = dict(document)
    document["devices"] = repaired_devices
    document["substrates"] = list(grouped.values())
    document["schema_version"] = 3
    return document, True, mapping


def upgrade() -> None:
    # 0. Widen alembic_version.version_num (VARCHAR(32) by default) so this
    #    revision id fits; the column is deliberately left wide on downgrade
    #    because shortening it would fail while a longer id is stamped.
    op.execute(
        sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    )

    # 1. deviation_type with a temporary server default so existing rows
    #    backfill as general deviations, then NOT NULL without a default:
    #    application code must provide the type explicitly from now on.
    op.add_column(
        "execution_deviations",
        sa.Column(
            "deviation_type",
            sa.String(length=32),
            nullable=False,
            server_default="general",
        ),
    )
    op.create_check_constraint(
        op.f("ck_execution_deviations_valid_deviation_type"),
        "execution_deviations",
        "deviation_type IN ('general', 'fabrication_shortfall', "
        "'measurement_shortfall')",
    )
    op.alter_column(
        "execution_deviations",
        "deviation_type",
        existing_type=sa.String(length=32),
        server_default=None,
    )

    # 2. Recreate the single-target check with condition_id in the sum so the
    #    database rejects a condition combined with any other target even when
    #    application validation is bypassed.
    op.drop_constraint(
        op.f("ck_execution_deviations_at_most_one_deviation_target"),
        "execution_deviations",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_execution_deviations_at_most_one_deviation_target"),
        "execution_deviations",
        "(CASE WHEN solution_preparation_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN process_execution_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN substrate_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN device_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN condition_id IS NULL THEN 0 ELSE 1 END) <= 1",
    )

    # 2b. Index for the qualifying-deviation gate queries.
    op.create_index(
        "ix_execution_deviations_condition_type",
        "execution_deviations",
        ["condition_id", "deviation_type"],
    )

    # 3. Backfill actual substrate counts for batches completed before the
    #    column existed; planned is the documented conservative value.
    op.execute(
        sa.text(
            "UPDATE fabrication_batch_conditions SET actual_substrate_count = "
            "planned_substrate_count "
            "WHERE actual_substrate_count IS NULL AND id IN ("
            "SELECT bc.id FROM fabrication_batch_conditions bc "
            "JOIN fabrication_batches b ON b.id = bc.fabrication_batch_id "
            "WHERE b.status = 'completed')"
        )
    )

    # 4. Repair unambiguous legacy analyses to schema 3 (device_ordinal,
    #    rebuilt substrate grouping, schema_version=3, analysis_schema_version=3).
    #    Ambiguous records are left at schema 2 (see DEPLOYMENT.md for review SQL).
    connection = op.get_bind()
    result_files = connection.execute(
        sa.text("SELECT id, analysis FROM result_files WHERE analysis IS NOT NULL")
    ).fetchall()
    for file_id, analysis in result_files:
        if isinstance(analysis, str):
            parsed = json.loads(analysis)
        else:
            parsed = analysis
        repaired, changed, mapping = _repair_legacy_analysis(parsed)
        if not changed or not mapping:
            continue
        # Verify every assignment row's analysis_substrate_id is in the
        # mapping; if any is not, the 1-to-1 correspondence is broken and
        # this file must stay at schema 2.
        assignment_ids = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT DISTINCT analysis_substrate_id "
                    "FROM result_device_assignments "
                    "WHERE result_file_id = :fid"
                ),
                {"fid": file_id},
            ).fetchall()
        ]
        unmapped = [aid for aid in assignment_ids if aid not in mapping]
        if unmapped:
            continue
        connection.execute(
            sa.text(
                "UPDATE result_files SET analysis = :analysis, "
                "analysis_schema_version = 3 WHERE id = :id"
            ),
            {"analysis": json.dumps(repaired), "id": file_id},
        )
        for old_id, full_mark in mapping.items():
            connection.execute(
                sa.text(
                    "UPDATE result_device_assignments "
                    "SET analysis_substrate_id = :full "
                    "WHERE result_file_id = :file_id "
                    "AND analysis_substrate_id = :legacy"
                ),
                {"full": full_mark, "file_id": file_id, "legacy": old_id},
            )


def downgrade() -> None:
    op.drop_index(
        "ix_execution_deviations_condition_type",
        table_name="execution_deviations",
    )
    op.drop_constraint(
        op.f("ck_execution_deviations_at_most_one_deviation_target"),
        "execution_deviations",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_execution_deviations_at_most_one_deviation_target"),
        "execution_deviations",
        "(CASE WHEN solution_preparation_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN process_execution_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN substrate_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN device_id IS NULL THEN 0 ELSE 1 END) <= 1",
    )
    op.drop_constraint(
        op.f("ck_execution_deviations_valid_deviation_type"),
        "execution_deviations",
        type_="check",
    )
    op.drop_column("execution_deviations", "deviation_type")
