"""Preserve canonical device-layout versions.

Revision ID: 0011_device_layout_versions
Revises: 0010_catalog_integrity
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_device_layout_versions"
down_revision = "0010_catalog_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Correct the canonical 25 mm single-device layout from v1 to v2."""

    op.execute(
        sa.text(
            "UPDATE device_layout_versions SET version = 2 "
            "WHERE code = '25x25_single_1cm2' AND version = 1 "
            "AND NOT EXISTS ("
            "SELECT 1 FROM device_layout_versions AS existing "
            "WHERE existing.code = '25x25_single_1cm2' AND existing.version = 2"
            ")"
        )
    )


def downgrade() -> None:
    """Restore the prior catalog version value when no v1 row exists."""

    op.execute(
        sa.text(
            "UPDATE device_layout_versions SET version = 1 "
            "WHERE code = '25x25_single_1cm2' AND version = 2 "
            "AND NOT EXISTS ("
            "SELECT 1 FROM device_layout_versions AS existing "
            "WHERE existing.code = '25x25_single_1cm2' AND existing.version = 1"
            ")"
        )
    )
