"""Personal and Shared baseline visibility.

Adds owner isolation, an explicit personal/shared scope, and promotion
provenance to ``baselines``. Existing baselines were instructor/administrator
created before this migration, so they are backfilled as Shared with the
creator retained as provenance-owner (``created_by_id`` remains the event
provenance).

Revision ID: 0012_baseline_scope_owner
Revises: 0011_device_layout_versions
Create Date: 2026-08-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_baseline_scope_owner"
down_revision = "0011_device_layout_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Nullable columns first; the scope/owner checks are added only after
    #    the legacy backfill so "personal requires an owner" never applies to
    #    rows with a null owner_user_id.
    op.add_column("baselines", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.add_column(
        "baselines",
        sa.Column(
            "scope",
            sa.String(length=24),
            nullable=False,
            server_default="personal",
        ),
    )
    op.add_column(
        "baselines",
        sa.Column("promoted_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "baselines",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "baselines",
        sa.Column("promotion_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "baselines",
        sa.Column("promoted_version_id", sa.Integer(), nullable=True),
    )

    # 2. Backfill: every pre-existing baseline was created by an instructor or
    #    administrator, so it is lab-wide Shared with the creator as the
    #    provenance owner.
    op.execute(
        sa.text(
            "UPDATE baselines SET scope = 'shared', owner_user_id = created_by_id "
            "WHERE created_by_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE baselines SET scope = 'shared' WHERE owner_user_id IS NULL"
        )
    )

    # 3. Constraints and indexes after the backfill.
    op.create_foreign_key(
        op.f("fk_baselines_owner_user_id_users"),
        "baselines",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_baselines_promoted_by_user_id_users"),
        "baselines",
        "users",
        ["promoted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_baselines_valid_baseline_scope"),
        "baselines",
        "scope IN ('personal', 'shared')",
    )
    op.create_check_constraint(
        op.f("ck_baselines_valid_baseline_scope_owner"),
        "baselines",
        "(scope = 'personal' AND owner_user_id IS NOT NULL) OR scope = 'shared'",
    )
    # Drop the global name uniqueness so two students may both name a Personal
    # baseline identically; Shared names remain globally unique.
    op.drop_constraint("uq_baselines_name", "baselines", type_="unique")
    op.create_index(
        "uq_baselines_personal_owner_name",
        "baselines",
        ["owner_user_id", "name"],
        unique=True,
        postgresql_where=sa.text("scope = 'personal'"),
    )
    op.create_index(
        "uq_baselines_shared_name",
        "baselines",
        ["name"],
        unique=True,
        postgresql_where=sa.text("scope = 'shared'"),
    )
    op.create_index(
        "ix_baselines_scope_status",
        "baselines",
        ["scope", "status"],
        unique=False,
    )
    op.create_index(
        "ix_baselines_owner_user_id",
        "baselines",
        ["owner_user_id"],
        unique=False,
    )
    # Composite target for the promoted-version membership foreign key.
    op.create_unique_constraint(
        op.f("uq_baseline_versions_baseline_id"),
        "baseline_versions",
        ["baseline_id", "id"],
    )
    # The promoted version must belong to the same baseline: (baselines.id,
    # promoted_version_id) references baseline_versions(baseline_id, id).
    # RESTRICT (not SET NULL): with a composite foreign key, SET NULL would
    # apply to both local columns - including the non-nullable primary key
    # baselines.id - and a promoted baseline revision is an immutable audit
    # record that must not be deleted while referenced.
    op.create_foreign_key(
        "fk_baselines_promoted_version_belongs_to_baseline",
        "baselines",
        "baseline_versions",
        ["id", "promoted_version_id"],
        ["baseline_id", "id"],
        ondelete="RESTRICT",
        use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_baselines_promoted_version_belongs_to_baseline",
        "baselines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_baseline_versions_baseline_id"),
        "baseline_versions",
        type_="unique",
    )
    op.drop_index("ix_baselines_owner_user_id", table_name="baselines")
    op.drop_index("ix_baselines_scope_status", table_name="baselines")
    op.drop_index("uq_baselines_shared_name", table_name="baselines")
    op.drop_index("uq_baselines_personal_owner_name", table_name="baselines")
    op.create_unique_constraint("uq_baselines_name", "baselines", ["name"])
    op.drop_constraint(
        op.f("ck_baselines_valid_baseline_scope_owner"),
        "baselines",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_baselines_valid_baseline_scope"),
        "baselines",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_baselines_promoted_by_user_id_users"),
        "baselines",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_baselines_owner_user_id_users"),
        "baselines",
        type_="foreignkey",
    )
    op.drop_column("baselines", "promoted_version_id")
    op.drop_column("baselines", "promotion_note")
    op.drop_column("baselines", "promoted_at")
    op.drop_column("baselines", "promoted_by_user_id")
    op.drop_column("baselines", "scope")
    op.drop_column("baselines", "owner_user_id")