"""Add shared materials and supplier product catalog.

Revision ID: 0009_material_catalog
Revises: 0008_user_layer_presets
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0009_material_catalog"
down_revision: Union[str, None] = "0008_user_layer_presets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_document = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()),
        "postgresql",
    )
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("formula", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("cas_number", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("specification", json_document, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('substrate', 'chemical', 'solvent', 'gas', 'other')",
            name=op.f("ck_materials_valid_material_category"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive')",
            name=op.f("ck_materials_valid_material_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_materials_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"], name=op.f("fk_materials_reviewed_by_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
        sa.UniqueConstraint("category", "name", name="uq_materials_category_name"),
    )
    op.create_index(
        "ix_materials_category_status",
        "materials",
        ["category", "status"],
        unique=False,
    )
    op.create_table(
        "material_products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("vendor", sa.String(length=160), nullable=False),
        sa.Column("catalog_number", sa.String(length=160), nullable=False),
        sa.Column("specification", json_document, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'inactive')",
            name=op.f("ck_material_products_valid_material_product_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_material_products_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name=op.f("fk_material_products_material_id_materials"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"], ["users.id"], name=op.f("fk_material_products_reviewed_by_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_products")),
        sa.UniqueConstraint(
            "material_id",
            "vendor",
            "catalog_number",
            name="uq_material_products_material_vendor_catalog_number",
        ),
    )
    op.create_index(
        "ix_material_products_material_status",
        "material_products",
        ["material_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_material_products_material_status", table_name="material_products")
    op.drop_table("material_products")
    op.drop_index("ix_materials_category_status", table_name="materials")
    op.drop_table("materials")
