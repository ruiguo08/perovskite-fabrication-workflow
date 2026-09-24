"""Add reusable catalog scope, seed tracking, and preset integrity.

Revision ID: 0010_catalog_integrity
Revises: 0009_material_catalog
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_catalog_integrity"
down_revision = "0009_material_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "layer_presets",
        sa.Column("scope", sa.String(length=24), server_default="personal", nullable=False),
    )
    op.add_column(
        "layer_presets",
        sa.Column("catalog_key", sa.String(length=120), nullable=True),
    )
    op.alter_column("layer_presets", "owner_user_id", nullable=True)
    op.drop_constraint("uq_layer_presets_owner_name", "layer_presets", type_="unique")
    op.create_check_constraint(
        "valid_layer_preset_scope",
        "layer_presets",
        "scope IN ('personal', 'shared')",
    )
    op.create_check_constraint(
        "valid_layer_preset_scope_owner",
        "layer_presets",
        "(scope = 'personal' AND owner_user_id IS NOT NULL) OR "
        "(scope = 'shared' AND owner_user_id IS NULL)",
    )
    op.create_index(
        "uq_layer_presets_personal_owner_name",
        "layer_presets",
        ["owner_user_id", "name"],
        unique=True,
        postgresql_where=sa.text("scope = 'personal'"),
    )
    op.create_index(
        "uq_layer_presets_shared_name",
        "layer_presets",
        ["name"],
        unique=True,
        postgresql_where=sa.text("scope = 'shared'"),
    )
    op.create_index(
        "ix_layer_presets_current_version_id",
        "layer_presets",
        ["current_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_layer_presets_scope_status",
        "layer_presets",
        ["scope", "status"],
        unique=False,
    )
    op.create_index(
        "uq_layer_presets_catalog_key",
        "layer_presets",
        ["catalog_key"],
        unique=True,
        postgresql_where=sa.text("catalog_key IS NOT NULL"),
    )
    op.create_unique_constraint(
        "uq_layer_preset_versions_preset_id_id",
        "layer_preset_versions",
        ["layer_preset_id", "id"],
    )
    op.create_index(
        "ix_layer_preset_versions_created_by_id",
        "layer_preset_versions",
        ["created_by_id"],
        unique=False,
    )
    op.drop_constraint(
        "fk_layer_presets_current_version_id_layer_preset_versions",
        "layer_presets",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_layer_presets_current_version_belongs_to_preset",
        "layer_presets",
        "layer_preset_versions",
        ["id", "current_version_id"],
        ["layer_preset_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_materials_created_by_status",
        "materials",
        ["created_by_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_materials_reviewed_by_id", "materials", ["reviewed_by_id"], unique=False
    )
    op.create_index(
        "ix_material_products_created_by_status",
        "material_products",
        ["created_by_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_material_products_reviewed_by_id",
        "material_products",
        ["reviewed_by_id"],
        unique=False,
    )
    op.create_table(
        "catalog_seed_versions",
        sa.Column("seed_key", sa.String(length=120), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("seed_key", name=op.f("pk_catalog_seed_versions")),
    )
    op.execute(
        sa.text(
            "INSERT INTO catalog_seed_versions (seed_key, applied_at) "
            "SELECT 'materials-v1', CURRENT_TIMESTAMP "
            "WHERE EXISTS (SELECT 1 FROM materials)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO catalog_seed_versions (seed_key, applied_at) "
            "SELECT 'device-layouts-v1', CURRENT_TIMESTAMP "
            "WHERE EXISTS (SELECT 1 FROM device_layout_versions)"
        )
    )


def downgrade() -> None:
    op.drop_table("catalog_seed_versions")
    op.drop_index("ix_material_products_reviewed_by_id", table_name="material_products")
    op.drop_index("ix_material_products_created_by_status", table_name="material_products")
    op.drop_index("ix_materials_reviewed_by_id", table_name="materials")
    op.drop_index("ix_materials_created_by_status", table_name="materials")
    op.drop_constraint(
        "fk_layer_presets_current_version_belongs_to_preset",
        "layer_presets",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_layer_preset_versions_created_by_id", table_name="layer_preset_versions"
    )
    op.create_foreign_key(
        "fk_layer_presets_current_version_id_layer_preset_versions",
        "layer_presets",
        "layer_preset_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_layer_preset_versions_preset_id_id",
        "layer_preset_versions",
        type_="unique",
    )
    op.drop_index("ix_layer_presets_current_version_id", table_name="layer_presets")
    op.drop_index("ix_layer_presets_scope_status", table_name="layer_presets")
    op.drop_index("uq_layer_presets_catalog_key", table_name="layer_presets")
    op.drop_index("uq_layer_presets_shared_name", table_name="layer_presets")
    op.drop_index("uq_layer_presets_personal_owner_name", table_name="layer_presets")
    op.drop_constraint(
        "ck_layer_presets_valid_layer_preset_scope_owner",
        "layer_presets",
        type_="check",
    )
    op.drop_constraint(
        "ck_layer_presets_valid_layer_preset_scope",
        "layer_presets",
        type_="check",
    )
    op.create_unique_constraint(
        "uq_layer_presets_owner_name", "layer_presets", ["owner_user_id", "name"]
    )
    op.alter_column("layer_presets", "owner_user_id", nullable=False)
    op.drop_column("layer_presets", "catalog_key")
    op.drop_column("layer_presets", "scope")
