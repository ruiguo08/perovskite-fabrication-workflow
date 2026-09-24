"""Remove the legacy experiments.recipe JSON blob.

``experiments.recipe`` predates per-condition snapshots and was written only
at experiment creation; condition edits updated
``experiment_conditions.recipe_snapshot`` (hash-verified at every workflow
gate) without ever resyncing the parent blob, so exports and legacy readers
could see a recipe that no longer matched the approved snapshots.

The column is dropped. ``ExperimentRecord.recipe`` is derived at read
time from the experiment's control (or standalone) condition snapshot, so
every consumer sees exactly the hash-verified configuration.

The downgrade re-adds the column as nullable (schema rollback only): the
historical blob values are gone and are deliberately not fabricated — a
null recipe is unambiguous, whereas reconstructing per-condition data into
a parent-column copy would silently resurrect the divergence this migration
removes. Operators rolling back application code must restore the matching
database backup to recover usable recipe values.

Revision ID: 0015_drop_experiments_recipe_blob
Revises: 0014_deployment_integrity_repairs
Create Date: 2026-08-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_drop_experiments_recipe_blob"
down_revision = "0014_deployment_integrity_repairs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("experiments", "recipe")


def downgrade() -> None:
    # Nullable on purpose: the historical values cannot be reconstructed
    # from the condition snapshots without fabricating a divergent copy.
    # The column type matches the original 0007 definition.
    op.add_column(
        "experiments",
            sa.Column(
                "recipe",
                sa.JSON().with_variant(
                    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
                ),
                nullable=True,
            ),
    )
