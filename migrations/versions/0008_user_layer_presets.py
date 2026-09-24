"""Add owner-isolated, versioned layer presets.

Revision ID: 0008_user_layer_presets
Revises: 0007_fabrication_batches
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_user_layer_presets"
down_revision: Union[str, None] = "0007_fabrication_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_document = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()),
        "postgresql",
    )
    op.create_table(
        "layer_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name=op.f("ck_layer_presets_valid_layer_preset_status"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_layer_presets_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_layer_presets")),
        sa.UniqueConstraint(
            "owner_user_id",
            "name",
            name="uq_layer_presets_owner_name",
        ),
    )
    op.create_index(
        "ix_layer_presets_owner_status",
        "layer_presets",
        ["owner_user_id", "status"],
        unique=False,
    )
    op.create_table(
        "layer_preset_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("layer_preset_id", sa.Integer(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "preset_schema_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("preset_snapshot", json_document, nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_number > 0",
            name=op.f("ck_layer_preset_versions_positive_revision_number"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_layer_preset_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["layer_preset_id"],
            ["layer_presets.id"],
            name=op.f("fk_layer_preset_versions_layer_preset_id_layer_presets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_layer_preset_versions")),
        sa.UniqueConstraint(
            "layer_preset_id",
            "revision_number",
            name="uq_layer_preset_versions_preset_revision",
        ),
    )
    op.create_index(
        "ix_layer_preset_versions_preset_id",
        "layer_preset_versions",
        ["layer_preset_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_layer_presets_current_version_id_layer_preset_versions",
        "layer_presets",
        "layer_preset_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_layer_presets_current_version_id_layer_preset_versions",
        "layer_presets",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_layer_preset_versions_preset_id",
        table_name="layer_preset_versions",
    )
    op.drop_table("layer_preset_versions")
    op.drop_index("ix_layer_presets_owner_status", table_name="layer_presets")
    op.drop_table("layer_presets")
