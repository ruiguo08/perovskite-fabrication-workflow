"""Substrate laser marks and actual substrate counts.

The glass laser mark (e.g. ``A001``) is a factory-etched physical fact that
students enter when saving J-V data, so it cannot be generated at batch
creation. This migration:

- Relaxes ``fabrication_substrates.substrate_mark`` to nullable and widens it
  to hold the full 4-character laser mark (previously a generated 3-char
  internal code). The mark is written back when a result CSV is uploaded and
  the substrate is associated with a condition.
- Widens ``fabrication_devices.device_mark`` to hold a device mark derived
  from the substrate laser mark plus a device ordinal.
- Adds ``fabrication_batch_conditions.actual_substrate_count``, recorded at
  the ``in_progress -> completed`` batch transition, so the planned versus
  actual substrate counts stay distinct and deviation rules can be enforced.
- Adds a batch-local uniqueness guard on the physical laser mark so a student
  cannot associate two database substrates with the same glass mark.

Revision ID: 0013_substrate_laser_marks
Revises: 0012_baseline_scope_owner
Create Date: 2026-08-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_substrate_laser_marks"
down_revision = "0012_baseline_scope_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. substrate_mark becomes nullable (a batch-created substrate has no
    #    laser mark until a CSV is uploaded) and widens to 9 characters to
    #    hold the physical mark.
    op.alter_column(
        "fabrication_substrates",
        "substrate_mark",
        existing_type=sa.String(length=3),
        type_=sa.String(length=9),
        nullable=True,
    )
    # Drop the strict length-3 check; the laser mark may be A001 (4 chars)
    # once written. Non-null marks keep a cross-dialect length range check.
    op.drop_constraint(
        op.f("ck_fabrication_substrates_valid_substrate_mark_length"),
        "fabrication_substrates",
        type_="check",
    )
    # Legacy substrate marks (generated internal codes such as A12) are not
    # physical laser marks and are obsolete under the new model; null them so
    # the new 4-9 length check holds for pre-existing rows.
    op.execute(
        sa.text("UPDATE fabrication_substrates SET substrate_mark = NULL")
    )
    op.create_check_constraint(
        op.f("ck_fabrication_substrates_valid_substrate_mark"),
        "fabrication_substrates",
        "substrate_mark IS NULL OR "
        "(length(substrate_mark) BETWEEN 4 AND 9)",
    )

    # 2. device_mark widens to 9 characters (laser mark + device ordinal,
    #    e.g. A001-1) and becomes nullable (it follows the substrate laser
    #    mark, which is blank until a CSV upload associates the substrate).
    op.alter_column(
        "fabrication_devices",
        "device_mark",
        existing_type=sa.String(length=4),
        type_=sa.String(length=9),
        nullable=True,
    )
    op.drop_constraint(
        op.f("ck_fabrication_devices_valid_device_mark_length"),
        "fabrication_devices",
        type_="check",
    )
    # Legacy device marks are likewise obsolete and nulled.
    op.execute(
        sa.text("UPDATE fabrication_devices SET device_mark = NULL")
    )
    op.create_check_constraint(
        op.f("ck_fabrication_devices_valid_device_mark"),
        "fabrication_devices",
        "device_mark IS NULL OR (length(device_mark) BETWEEN 5 AND 9)",
    )

    # 3. actual_substrate_count on batch conditions (nullable; defaults to the
    #    planned count in code when not yet recorded).
    op.add_column(
        "fabrication_batch_conditions",
        sa.Column("actual_substrate_count", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_fabrication_batch_conditions_non_negative_actual_count"),
        "fabrication_batch_conditions",
        "actual_substrate_count IS NULL OR actual_substrate_count >= 0",
    )

    # 4. (Batch-local uniqueness on the physical laser mark is enforced in
    #    Python during result-CSV association, because the batch id is not a
    #    column on fabrication_substrates and a partial unique index across
    #    the batch_condition join is not portable across SQLite/PostgreSQL.)

    # 5. Deviations may target a whole batch condition (e.g. "made N but only
    #    M measured" or "whole group abandoned"), independent of a specific
    #    substrate/device/preparation/execution.
    op.add_column(
        "execution_deviations",
        sa.Column("condition_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_execution_deviations_condition_id_fabrication_batch_conditions"),
        "execution_deviations",
        "fabrication_batch_conditions",
        ["condition_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade from 0013 is intentionally irreversible.

    The pre-0013 narrow mark model (3/4-character substrate/device marks)
    cannot hold physical laser marks (4-9 characters).  Generating fake
    base36 marks would destroy provenance data silently.  Instead, this
    downgrade fails immediately with an explicit message so operators
    restore from a verified backup rather than lose physical identity.
    """

    raise RuntimeError(
        "downgrade from 0013 is intentionally blocked: the pre-0013 narrow "
        "mark model cannot hold physical laser marks without destroying "
        "provenance.  Restore from a verified backup instead."
    )
