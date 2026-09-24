"""Per-device directional scan stats cache and representative-scan choice.

Schema v7 stops storing aggregate summaries in ``result_files.analysis``:
every scan stays an individual trace, and the per-device forward/reverse
representatives become a dedicated write-time cache instead of an
untracked corner of the analysis JSON.

Two tables:

- ``device_scan_stats`` — one row per (physical device, direction) holding
  the representative scan (highest-PCE valid scan across all uploads, or
  the user's explicit choice), its provenance (result file, trace id,
  measured time, verbatim instrument metrics), and the direction's scan
  count. Fully re-derivable from the stored traces; rewritten in the
  assignment transaction, so reads never re-aggregate.
- ``device_representative_scans`` — the user's explicit representative
  choice per (device, direction), which overrides the highest-PCE rule.

The downgrade drops both tables: they are caches and explicit choices, not
measurements, and the underlying per-scan records are untouched.

Revision ID: 0016_device_scan_stats
Revises: 0015_drop_experiments_recipe_blob
Create Date: 2026-09-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_device_scan_stats"
down_revision = "0015_drop_experiments_recipe_blob"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "device_scan_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fabrication_device_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column(
            "best_result_file_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column("best_trace_id", sa.String(length=80), nullable=True),
        sa.Column("best_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("best_metrics", _JSON, nullable=True),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fabrication_device_id"],
            ["fabrication_devices.id"],
            name=op.f("fk_device_scan_stats_fabrication_device_id_fabrication_devices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["best_result_file_id"],
            ["result_files.id"],
            name=op.f("fk_device_scan_stats_best_result_file_id_result_files"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "direction IN ('forward', 'reverse')",
            name=op.f("ck_device_scan_stats_valid_scan_direction"),
        ),
        sa.CheckConstraint(
            "scan_count >= 0",
            name=op.f("ck_device_scan_stats_non_negative_scan_count"),
        ),
        sa.UniqueConstraint(
            "fabrication_device_id",
            "direction",
            name="uq_device_scan_stats_device_direction",
        ),
    )
    op.create_index(
        "ix_device_scan_stats_fabrication_device_id",
        "device_scan_stats",
        ["fabrication_device_id"],
    )
    op.create_table(
        "device_representative_scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fabrication_device_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column(
            "result_file_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(length=80), nullable=False),
        sa.Column("selected_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["fabrication_device_id"],
            ["fabrication_devices.id"],
            name="fk_device_representative_scans_fabrication_device_id_fa_6022",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["result_file_id"],
            ["result_files.id"],
            name=op.f("fk_device_representative_scans_result_file_id_result_files"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["selected_by_id"],
            ["users.id"],
            name=op.f("fk_device_representative_scans_selected_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "direction IN ('forward', 'reverse')",
            name=op.f("ck_device_representative_scans_valid_scan_direction"),
        ),
        sa.UniqueConstraint(
            "fabrication_device_id",
            "direction",
            name="uq_device_representative_device_direction",
        ),
    )
    op.create_index(
        "ix_device_representative_scans_fabrication_device_id",
        "device_representative_scans",
        ["fabrication_device_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_device_representative_scans_fabrication_device_id",
        table_name="device_representative_scans",
    )
    op.drop_table("device_representative_scans")
    op.drop_index(
        "ix_device_scan_stats_fabrication_device_id",
        table_name="device_scan_stats",
    )
    op.drop_table("device_scan_stats")
