"""Asynchronous database configuration and relational schema."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .condition_snapshot import CONDITION_RECIPE_SCHEMA_VERSION
from .execution_snapshots import (
    PROCESS_SNAPSHOT_SCHEMA_VERSION,
    SOLUTION_SNAPSHOT_SCHEMA_VERSION,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)
json_document = JSON().with_variant(JSONB(), "postgresql")

CAMPAIGN_ID_MAX_LENGTH = 160
CAMPAIGN_CODE_MAX_LENGTH = 80
DISPLAY_NAME_MAX_LENGTH = 120
EXPERIMENT_CODE_MAX_LENGTH = 200
LAYOUT_CODE_MAX_LENGTH = 40
BASELINE_NAME_MAX_LENGTH = 160
BASELINE_RECIPE_SCHEMA_VERSION = 1
LAYER_PRESET_NAME_MAX_LENGTH = 120
LAYER_PRESET_SCHEMA_VERSION = 1
MATERIAL_NAME_MAX_LENGTH = 160
MATERIAL_FORMULA_MAX_LENGTH = 120
MATERIAL_CAS_NUMBER_MAX_LENGTH = 64
MATERIAL_VENDOR_MAX_LENGTH = 160
MATERIAL_CATALOG_NUMBER_MAX_LENGTH = 160

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("display_name", String(DISPLAY_NAME_MAX_LENGTH), nullable=False),
    Column("password_hash", String(512), nullable=False),
    Column("role", String(24), nullable=False),
    Column("is_active", Boolean, nullable=False, default=True, server_default="true"),
    Column("failed_login_count", Integer, nullable=False, default=0, server_default="0"),
    Column("locked_until", DateTime(timezone=True)),
    Column("last_login_at", DateTime(timezone=True)),
    Column("password_changed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "role IN ('student', 'instructor', 'administrator')",
        name="valid_role",
    ),
    CheckConstraint("failed_login_count >= 0", name="nonnegative_login_failures"),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("csrf_token_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("client_ip", String(64)),
    Column("user_agent", String(512)),
)
Index("ix_sessions_user_id", sessions.c.user_id)
Index("ix_sessions_expires_at", sessions.c.expires_at)

experiments = Table(
    "experiments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("status", String(24), nullable=False),
    Column("metrics", json_document, nullable=False, default=dict),
    Column("failure_reason", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column(
        "campaign_id",
        ForeignKey("campaigns.code", ondelete="RESTRICT", use_alter=True),
    ),
    Column("experiment_code", String(EXPERIMENT_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("series_version", Integer, nullable=False),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    # Plan domain: type + approval-aware status (nullable for legacy rows).
    Column("plan_type", String(24)),
    Column("plan_status", String(24)),
    CheckConstraint(
        "status IN ('suggested', 'running', 'completed', 'failed')",
        name="valid_status",
    ),
    CheckConstraint(
        "plan_type IS NULL OR plan_type IN ('comparative', 'standalone')",
        name="valid_plan_type",
    ),
    CheckConstraint(
        "plan_status IS NULL OR plan_status IN "
        "('draft', 'pending_approval', 'approved', 'released', "
        "'in_progress', 'completed', 'cancelled')",
        name="valid_plan_status",
    ),
    CheckConstraint("series_version > 0", name="positive_series_version"),
    UniqueConstraint(
        "campaign_id",
        "series_version",
        name="uq_experiments_campaign_series_version",
    ),
)
Index("ix_experiments_campaign_id_id", experiments.c.campaign_id, experiments.c.id)

baselines = Table(
    "baselines",
    metadata,
    Column(
        "id",
        Integer,
        primary_key=True,
        # Part of the (id, promoted_version_id) membership foreign key; the
        # referenced-column role must not disable local autoincrement.
        autoincrement="ignore_fk",
    ),
    Column("name", String(BASELINE_NAME_MAX_LENGTH), nullable=False),
    Column("device_recipe", json_document, nullable=False),
    Column("deposition_process", json_document, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("updated_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    # Personal/shared visibility: a Personal baseline belongs to its owner;
    # a Shared baseline is lab-wide and keeps the original owner as provenance.
    Column(
        "owner_user_id",
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
            name="fk_baselines_owner_user_id_users",
        ),
        nullable=True,
    ),
    Column(
        "scope",
        String(24),
        nullable=False,
        default="personal",
        server_default="personal",
    ),
    # Promotion provenance (set once when a Personal baseline is promoted).
    Column(
        "promoted_by_user_id",
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_baselines_promoted_by_user_id_users",
        ),
        nullable=True,
    ),
    Column("promoted_at", DateTime(timezone=True), nullable=True),
    Column("promotion_note", Text, nullable=True),
    # The exact immutable revision captured at promotion time.
    Column("promoted_version_id", Integer, nullable=True),
    # Versioning: status + pointer to the current immutable revision.
    Column("status", String(24), nullable=False, default="active", server_default="active"),
    Column(
        "current_version_id",
        ForeignKey(
            "baseline_versions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_baselines_current_version_id_baseline_versions",
        ),
    ),
    CheckConstraint(
        "status IN ('active', 'archived')",
        name="valid_baseline_status",
    ),
    CheckConstraint(
        "scope IN ('personal', 'shared')",
        name="valid_baseline_scope",
    ),
    CheckConstraint(
        "(scope = 'personal' AND owner_user_id IS NOT NULL) OR "
        "scope = 'shared'",
        name="valid_baseline_scope_owner",
    ),
    # The promoted version must belong to the same baseline: (id,
    # promoted_version_id) references baseline_versions(baseline_id, id).
    # RESTRICT (not SET NULL): with a composite foreign key, SET NULL would
    # apply to both local columns - including the non-nullable primary key
    # baselines.id - and baseline revisions are immutable audit records that
    # must not be deleted while referenced as the promoted revision.
    ForeignKeyConstraint(
        ["id", "promoted_version_id"],
        ["baseline_versions.baseline_id", "baseline_versions.id"],
        name="fk_baselines_promoted_version_belongs_to_baseline",
        ondelete="RESTRICT",
        use_alter=True,
    ),
)
Index(
    "uq_baselines_personal_owner_name",
    baselines.c.owner_user_id,
    baselines.c.name,
    unique=True,
    sqlite_where=baselines.c.scope == "personal",
    postgresql_where=baselines.c.scope == "personal",
)
Index(
    "uq_baselines_shared_name",
    baselines.c.name,
    unique=True,
    sqlite_where=baselines.c.scope == "shared",
    postgresql_where=baselines.c.scope == "shared",
)
Index(
    "ix_baselines_scope_status",
    baselines.c.scope,
    baselines.c.status,
)
Index("ix_baselines_owner_user_id", baselines.c.owner_user_id)

baseline_versions = Table(
    "baseline_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "baseline_id",
        ForeignKey("baselines.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("revision_number", Integer, nullable=False),
    Column(
        "recipe_schema_version",
        Integer,
        nullable=False,
        default=BASELINE_RECIPE_SCHEMA_VERSION,
        server_default=str(BASELINE_RECIPE_SCHEMA_VERSION),
    ),
    Column("recipe_snapshot", json_document, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("change_note", Text, nullable=False, default=""),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("revision_number > 0", name="positive_revision_number"),
    UniqueConstraint(
        "baseline_id",
        "revision_number",
        name="uq_baseline_versions_baseline_revision",
    ),
    # Composite key target for the promoted-version membership foreign key.
    UniqueConstraint(
        "baseline_id",
        "id",
        name="uq_baseline_versions_baseline_id",
    ),
)
Index("ix_baseline_versions_baseline_id", baseline_versions.c.baseline_id)


layer_presets = Table(
    "layer_presets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement="ignore_fk"),
    Column(
        "owner_user_id",
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("scope", String(24), nullable=False, default="personal", server_default="personal"),
    Column("catalog_key", String(120), nullable=True),
    Column("name", String(LAYER_PRESET_NAME_MAX_LENGTH), nullable=False),
    Column("status", String(24), nullable=False, default="active", server_default="active"),
    Column("current_version_id", Integer),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('active', 'inactive')",
        name="valid_layer_preset_status",
    ),
    CheckConstraint(
        "(scope = 'personal' AND owner_user_id IS NOT NULL) OR "
        "(scope = 'shared' AND owner_user_id IS NULL)",
        name="valid_layer_preset_scope_owner",
    ),
    CheckConstraint(
        "scope IN ('personal', 'shared')",
        name="valid_layer_preset_scope",
    ),
    ForeignKeyConstraint(
        ["id", "current_version_id"],
        ["layer_preset_versions.layer_preset_id", "layer_preset_versions.id"],
        name="fk_layer_presets_current_version_belongs_to_preset",
        ondelete="RESTRICT",
        use_alter=True,
    ),
)
Index(
    "ix_layer_presets_owner_status",
    layer_presets.c.owner_user_id,
    layer_presets.c.status,
)
Index(
    "uq_layer_presets_personal_owner_name",
    layer_presets.c.owner_user_id,
    layer_presets.c.name,
    unique=True,
    sqlite_where=layer_presets.c.scope == "personal",
    postgresql_where=layer_presets.c.scope == "personal",
)
Index(
    "uq_layer_presets_shared_name",
    layer_presets.c.name,
    unique=True,
    sqlite_where=layer_presets.c.scope == "shared",
    postgresql_where=layer_presets.c.scope == "shared",
)
Index("ix_layer_presets_current_version_id", layer_presets.c.current_version_id)
Index("ix_layer_presets_scope_status", layer_presets.c.scope, layer_presets.c.status)
Index(
    "uq_layer_presets_catalog_key",
    layer_presets.c.catalog_key,
    unique=True,
    sqlite_where=layer_presets.c.catalog_key.is_not(None),
    postgresql_where=layer_presets.c.catalog_key.is_not(None),
)

layer_preset_versions = Table(
    "layer_preset_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "layer_preset_id",
        ForeignKey("layer_presets.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("revision_number", Integer, nullable=False),
    Column(
        "preset_schema_version",
        Integer,
        nullable=False,
        default=LAYER_PRESET_SCHEMA_VERSION,
        server_default=str(LAYER_PRESET_SCHEMA_VERSION),
    ),
    Column("preset_snapshot", json_document, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("revision_number > 0", name="positive_revision_number"),
    UniqueConstraint(
        "layer_preset_id",
        "revision_number",
        name="uq_layer_preset_versions_preset_revision",
    ),
    UniqueConstraint(
        "layer_preset_id",
        "id",
        name="uq_layer_preset_versions_preset_id_id",
    ),
)
Index(
    "ix_layer_preset_versions_preset_id",
    layer_preset_versions.c.layer_preset_id,
)
Index("ix_layer_preset_versions_created_by_id", layer_preset_versions.c.created_by_id)


materials = Table(
    "materials",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("category", String(24), nullable=False),
    Column("name", String(MATERIAL_NAME_MAX_LENGTH), nullable=False),
    Column("formula", String(MATERIAL_FORMULA_MAX_LENGTH), nullable=False, default=""),
    Column(
        "cas_number",
        String(MATERIAL_CAS_NUMBER_MAX_LENGTH),
        nullable=False,
        default="",
    ),
    Column("specification", json_document, nullable=False, default=dict),
    Column("status", String(24), nullable=False, default="pending", server_default="pending"),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("reviewed_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "category IN ('substrate', 'chemical', 'solvent', 'gas', 'other')",
        name="valid_material_category",
    ),
    CheckConstraint(
        "status IN ('pending', 'active', 'inactive')",
        name="valid_material_status",
    ),
    UniqueConstraint("category", "name", name="uq_materials_category_name"),
)
Index("ix_materials_category_status", materials.c.category, materials.c.status)
Index("ix_materials_created_by_status", materials.c.created_by_id, materials.c.status)
Index("ix_materials_reviewed_by_id", materials.c.reviewed_by_id)

material_products = Table(
    "material_products",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "material_id",
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("vendor", String(MATERIAL_VENDOR_MAX_LENGTH), nullable=False),
    Column("catalog_number", String(MATERIAL_CATALOG_NUMBER_MAX_LENGTH), nullable=False),
    Column("specification", json_document, nullable=False, default=dict),
    Column("status", String(24), nullable=False, default="pending", server_default="pending"),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("reviewed_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'active', 'inactive')",
        name="valid_material_product_status",
    ),
    UniqueConstraint(
        "material_id",
        "vendor",
        "catalog_number",
        name="uq_material_products_material_vendor_catalog_number",
    ),
)
Index("ix_material_products_material_status", material_products.c.material_id, material_products.c.status)
Index(
    "ix_material_products_created_by_status",
    material_products.c.created_by_id,
    material_products.c.status,
)
Index("ix_material_products_reviewed_by_id", material_products.c.reviewed_by_id)


catalog_seed_versions = Table(
    "catalog_seed_versions",
    metadata,
    Column("seed_key", String(120), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


experiment_conditions = Table(
    "experiment_conditions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "experiment_id",
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("role", String(24), nullable=False),  # control / target / standalone
    Column("condition_code", String(EXPERIMENT_CODE_MAX_LENGTH + 8), nullable=False),
    Column("condition_name", String(DISPLAY_NAME_MAX_LENGTH), nullable=False),
    Column("recipe_snapshot", json_document, nullable=False),
    Column(
        "recipe_schema_version",
        Integer,
        nullable=False,
        default=CONDITION_RECIPE_SCHEMA_VERSION,
        server_default=str(CONDITION_RECIPE_SCHEMA_VERSION),
    ),
    Column("canonical_hash", String(64), nullable=False),
    Column(
        "source_baseline_version_id",
        ForeignKey(
            "baseline_versions.id",
            ondelete="RESTRICT",
            name="fk_experiment_conditions_source_baseline_version",
        ),
    ),
    Column("device_layout_code", String(LAYOUT_CODE_MAX_LENGTH), nullable=False),
    Column("device_layout_snapshot", json_document, nullable=False),
    Column("planned_substrate_count", Integer, nullable=False),
    Column("expected_device_count", Integer, nullable=False),
    Column("requires_manual_review", Boolean, nullable=False, default=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    CheckConstraint(
        "role IN ('control', 'target', 'standalone')",
        name="valid_condition_role",
    ),
    CheckConstraint("planned_substrate_count >= 1", name="positive_substrate_count"),
    CheckConstraint("expected_device_count >= 1", name="positive_expected_device_count"),
    UniqueConstraint(
        "experiment_id", "condition_code", name="uq_conditions_experiment_code"
    ),
)
Index("ix_experiment_conditions_experiment_id", experiment_conditions.c.experiment_id)


condition_substrate_exceptions = Table(
    "condition_substrate_exceptions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "condition_id",
        ForeignKey("experiment_conditions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("requested_count", Integer, nullable=False),
    Column("reason", Text, nullable=False),
    Column("requested_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column(
        "decision",
        String(24),
        nullable=False,
        default="pending",
        server_default="pending",
    ),
    Column("decided_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("decided_at", DateTime(timezone=True)),
    Column("decision_note", Text, nullable=False, default=""),
    Column("approved_condition_hash", String(64)),
    CheckConstraint(
        "decision IN ('pending', 'approved', 'rejected', 'invalidated')",
        name="valid_exception_decision",
    ),
    CheckConstraint("requested_count >= 1", name="positive_requested_count"),
)
Index(
    "ix_condition_substrate_exceptions_condition_id",
    condition_substrate_exceptions.c.condition_id,
)
Index(
    "uq_condition_active_substrate_exception",
    condition_substrate_exceptions.c.condition_id,
    unique=True,
    sqlite_where=condition_substrate_exceptions.c.decision.in_(["pending", "approved"]),
    postgresql_where=condition_substrate_exceptions.c.decision.in_(["pending", "approved"]),
)

result_files = Table(
    "result_files",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "experiment_id",
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "fabrication_batch_id",
        ForeignKey("fabrication_batches.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("filename", String(255), nullable=False),
    Column("content_type", String(100), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("content", LargeBinary, nullable=False),
    Column("group_assignment", Text, nullable=False, default=""),
    Column("metrics", json_document, nullable=False, default=dict),
    Column("analysis", json_document, nullable=False, default=dict),
    Column("analysis_schema_version", Integer, nullable=False, default=3, server_default="2"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    CheckConstraint("size_bytes > 0", name="positive_size"),
)
Index("ix_result_files_experiment_id", result_files.c.experiment_id)
Index("ix_result_files_batch_id", result_files.c.fabrication_batch_id)

audit_events = Table(
    "audit_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("actor_user_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("action", String(100), nullable=False),
    Column("entity_type", String(80), nullable=False),
    Column("entity_id", String(100)),
    Column("details", json_document, nullable=False, default=dict),
    Column("client_ip", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index("ix_audit_events_created_at", audit_events.c.created_at)
Index("ix_audit_events_actor_user_id", audit_events.c.actor_user_id)


campaigns = Table(
    "campaigns",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(CAMPAIGN_ID_MAX_LENGTH), nullable=False, unique=True),
    Column("display_name", String(DISPLAY_NAME_MAX_LENGTH), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column(
        "status",
        String(24),
        nullable=False,
        default="active",
        server_default="active",
    ),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True)),
    CheckConstraint(
        "status IN ('active', 'closed', 'archived')",
        name="valid_campaign_status",
    ),
)
Index("ix_campaigns_status_id", campaigns.c.status, campaigns.c.id)


BATCH_CODE_MAX_LENGTH = 200
BATCH_STATUS_MAX_LENGTH = 24
CONDITION_CODE_MAX_LENGTH = 200
LAYER_CODE_MAX_LENGTH = 80
DEVIATION_CATEGORY_MAX_LENGTH = 80
DEVIATION_SEVERITY_MAX_LENGTH = 24
DEVIATION_TYPE_MAX_LENGTH = 32
EXECUTION_METHOD_MAX_LENGTH = 40
EQUIPMENT_IDENTIFIER_MAX_LENGTH = 120
BATCH_NOTES_MAX_LENGTH = 2000
CONDITION_SET_HASH_MAX_LENGTH = 64

fabrication_batches = Table(
    "fabrication_batches",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "experiment_id",
        ForeignKey("experiments.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("batch_number", Integer, nullable=False),
    Column("batch_code", String(BATCH_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("status", String(BATCH_STATUS_MAX_LENGTH), nullable=False, default="draft", server_default="draft"),
    Column("condition_set_hash", String(CONDITION_SET_HASH_MAX_LENGTH), nullable=False),
    Column("notes", String(BATCH_NOTES_MAX_LENGTH), nullable=False, default="", server_default=""),
    Column("created_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("cancelled_at", DateTime(timezone=True)),
    CheckConstraint(
        "status IN ('draft', 'ready', 'in_progress', 'completed', 'cancelled')",
        name="valid_batch_status",
    ),
    CheckConstraint("batch_number > 0", name="positive_batch_number"),
    UniqueConstraint(
        "experiment_id", "batch_number", name="uq_batches_experiment_number"
    ),
)
Index("ix_fabrication_batches_experiment_id", fabrication_batches.c.experiment_id)
Index("ix_fabrication_batches_status", fabrication_batches.c.status)

fabrication_batch_conditions = Table(
    "fabrication_batch_conditions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_batch_id",
        ForeignKey("fabrication_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_condition_id", ForeignKey("experiment_conditions.id", ondelete="RESTRICT"), nullable=False),
    Column("condition_code", String(CONDITION_CODE_MAX_LENGTH), nullable=False),
    Column("condition_name", String(DISPLAY_NAME_MAX_LENGTH), nullable=False),
    Column("role", String(24), nullable=False),
    Column("source_condition_hash", String(64), nullable=False),
    Column("recipe_snapshot", json_document, nullable=False),
    Column("recipe_schema_version", Integer, nullable=False),
    Column("device_layout_code", String(LAYOUT_CODE_MAX_LENGTH), nullable=False),
    Column("device_layout_snapshot", json_document, nullable=False),
    Column("planned_substrate_count", Integer, nullable=False),
    Column("expected_device_count", Integer, nullable=False),
    Column("actual_substrate_count", Integer, nullable=True),
    CheckConstraint(
        "role IN ('control', 'target', 'standalone')",
        name="valid_batch_condition_role",
    ),
    CheckConstraint("planned_substrate_count >= 1", name="positive_batch_substrate_count"),
    CheckConstraint("expected_device_count >= 1", name="positive_batch_device_count"),
    UniqueConstraint(
        "fabrication_batch_id", "condition_code", name="uq_batch_conditions_code"
    ),
    CheckConstraint(
        "actual_substrate_count IS NULL OR actual_substrate_count >= 0",
        name="non_negative_actual_count",
    ),
)
Index(
    "ix_fabrication_batch_conditions_batch_id",
    fabrication_batch_conditions.c.fabrication_batch_id,
)
Index(
    "ix_fabrication_batch_conditions_source_condition_id",
    fabrication_batch_conditions.c.source_condition_id,
)

fabrication_substrates = Table(
    "fabrication_substrates",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "batch_condition_id",
        ForeignKey("fabrication_batch_conditions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("substrate_ordinal", Integer, nullable=False),
    Column("substrate_code", String(BATCH_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("substrate_mark", String(9), nullable=True),
    Column("status", String(24), nullable=False, default="planned", server_default="planned"),
    Column("notes", String(BATCH_NOTES_MAX_LENGTH), nullable=False, default="", server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('planned', 'active', 'completed', 'failed', 'excluded')",
        name="valid_substrate_status",
    ),
    CheckConstraint("substrate_ordinal > 0", name="positive_substrate_ordinal"),
    CheckConstraint(
        "substrate_mark IS NULL OR (length(substrate_mark) BETWEEN 4 AND 9)",
        name="valid_substrate_mark",
    ),
    UniqueConstraint(
        "batch_condition_id", "substrate_ordinal", name="uq_substrates_condition_ordinal"
    ),
)
Index(
    "ix_fabrication_substrates_batch_condition_id",
    fabrication_substrates.c.batch_condition_id,
)

fabrication_devices = Table(
    "fabrication_devices",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "substrate_id",
        ForeignKey("fabrication_substrates.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("device_ordinal", Integer, nullable=False),
    Column("device_code", String(BATCH_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("device_mark", String(9), nullable=True),
    Column("device_active_area_cm2", Numeric(10, 4), nullable=False),
    Column("status", String(24), nullable=False, default="planned", server_default="planned"),
    Column("notes", String(BATCH_NOTES_MAX_LENGTH), nullable=False, default="", server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('planned', 'active', 'completed', 'failed', 'excluded')",
        name="valid_device_status",
    ),
    CheckConstraint("device_ordinal > 0", name="positive_device_ordinal"),
    CheckConstraint(
        "device_mark IS NULL OR (length(device_mark) BETWEEN 5 AND 9)",
        name="valid_device_mark",
    ),
    CheckConstraint("device_active_area_cm2 > 0", name="positive_device_area"),
    UniqueConstraint(
        "substrate_id", "device_ordinal", name="uq_devices_substrate_ordinal"
    ),
)
Index(
    "ix_fabrication_devices_substrate_id",
    fabrication_devices.c.substrate_id,
)

result_device_assignments = Table(
    "result_device_assignments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "result_file_id",
        ForeignKey("result_files.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("analysis_device_id", String(80), nullable=False),
    Column("analysis_substrate_id", Text, nullable=False),
    Column("instrument_label", Text, nullable=False),
    Column(
        "batch_condition_id",
        ForeignKey("fabrication_batch_conditions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "fabrication_device_id",
        ForeignKey("fabrication_devices.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "result_file_id",
        "analysis_device_id",
        name="uq_result_assignment_analysis_device",
    ),
    UniqueConstraint(
        "result_file_id",
        "fabrication_device_id",
        name="uq_result_assignment_fabrication_device",
    ),
)
Index(
    "ix_result_device_assignments_result_file_id",
    result_device_assignments.c.result_file_id,
)
Index(
    "ix_result_device_assignments_fabrication_device_id",
    result_device_assignments.c.fabrication_device_id,
)
Index(
    "ix_result_device_assignments_batch_condition_id",
    result_device_assignments.c.batch_condition_id,
)

# Write-time cache over every scan assigned to a physical device: one row
# per (device, direction) holding the representative scan (highest-PCE
# valid scan of that direction across all uploads, or the user's explicit
# choice) plus how many scans the direction has. Fully re-derivable from
# result_files.analysis; rewritten in the assignment transaction.
device_scan_stats = Table(
    "device_scan_stats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_device_id",
        ForeignKey("fabrication_devices.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("direction", String(16), nullable=False),
    Column(
        "best_result_file_id",
        ForeignKey("result_files.id", ondelete="CASCADE"),
        nullable=True,
    ),
    Column("best_trace_id", String(80), nullable=True),
    Column("best_measured_at", DateTime(timezone=True), nullable=True),
    Column("best_metrics", json_document, nullable=True),
    Column("scan_count", Integer, nullable=False, default=0, server_default="0"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("direction IN ('forward', 'reverse')", name="valid_scan_direction"),
    CheckConstraint("scan_count >= 0", name="non_negative_scan_count"),
    UniqueConstraint(
        "fabrication_device_id",
        "direction",
        name="uq_device_scan_stats_device_direction",
    ),
)
Index(
    "ix_device_scan_stats_fabrication_device_id",
    device_scan_stats.c.fabrication_device_id,
)

# The user's explicit representative-scan choice per (device, direction).
# When absent, the cache falls back to the highest-PCE rule; a selection
# referencing a scan that is no longer assigned to the device is dropped
# when the cache is refreshed.
device_representative_scans = Table(
    "device_representative_scans",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_device_id",
        ForeignKey("fabrication_devices.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("direction", String(16), nullable=False),
    Column(
        "result_file_id",
        ForeignKey("result_files.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("trace_id", String(80), nullable=False),
    Column("selected_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("direction IN ('forward', 'reverse')", name="valid_scan_direction"),
    UniqueConstraint(
        "fabrication_device_id",
        "direction",
        name="uq_device_representative_device_direction",
    ),
)
Index(
    "ix_device_representative_scans_fabrication_device_id",
    device_representative_scans.c.fabrication_device_id,
)

solution_preparations = Table(
    "solution_preparations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_batch_id",
        ForeignKey("fabrication_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("preparation_code", String(BATCH_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("status", String(24), nullable=False, default="planned", server_default="planned"),
    Column("planned_solution_snapshot", json_document, nullable=False),
    Column(
        "planned_snapshot_schema_version",
        Integer,
        nullable=False,
        default=SOLUTION_SNAPSHOT_SCHEMA_VERSION,
        server_default=str(SOLUTION_SNAPSHOT_SCHEMA_VERSION),
    ),
    Column("planned_canonical_hash", String(64), nullable=False),
    Column("actual_solution_snapshot", json_document),
    Column("actual_snapshot_schema_version", Integer),
    Column("actual_canonical_hash", String(64)),
    Column("actual_recording_mode", String(24)),
    Column("prepared_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("prepared_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("notes", String(BATCH_NOTES_MAX_LENGTH), nullable=False, default="", server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('planned', 'preparing', 'ready', 'consumed', 'discarded')",
        name="valid_preparation_status",
    ),
    CheckConstraint(
        "actual_recording_mode IS NULL OR actual_recording_mode IN "
        "('copied_from_plan', 'entered')",
        name="valid_solution_actual_recording_mode",
    ),
    CheckConstraint(
        "(actual_solution_snapshot IS NULL AND actual_snapshot_schema_version IS NULL "
        "AND actual_canonical_hash IS NULL AND actual_recording_mode IS NULL) OR "
        "(actual_solution_snapshot IS NOT NULL AND actual_snapshot_schema_version IS NOT NULL "
        "AND actual_canonical_hash IS NOT NULL AND actual_recording_mode IS NOT NULL)",
        name="complete_solution_actual_metadata",
    ),
)
Index(
    "ix_solution_preparations_batch_id",
    solution_preparations.c.fabrication_batch_id,
)

solution_preparation_uses = Table(
    "solution_preparation_uses",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "solution_preparation_id",
        ForeignKey("solution_preparations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "batch_condition_id",
        ForeignKey("fabrication_batch_conditions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("layer_ordinal", Integer, nullable=False),
    Column("layer_role", String(LAYER_CODE_MAX_LENGTH), nullable=False),
    Column("layer_type", String(LAYER_CODE_MAX_LENGTH), nullable=False),
    Column("layer_snapshot_hash", String(64), nullable=False),
    UniqueConstraint(
        "solution_preparation_id",
        "batch_condition_id",
        "layer_ordinal",
        name="uq_preparation_use_unique",
    ),
)
Index(
    "ix_preparation_uses_preparation_id",
    solution_preparation_uses.c.solution_preparation_id,
)
Index(
    "ix_preparation_uses_batch_condition_id",
    solution_preparation_uses.c.batch_condition_id,
)

process_executions = Table(
    "process_executions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_batch_id",
        ForeignKey("fabrication_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("execution_code", String(BATCH_CODE_MAX_LENGTH), nullable=False, unique=True),
    Column("method", String(EXECUTION_METHOD_MAX_LENGTH), nullable=False),
    Column("layer_role", String(LAYER_CODE_MAX_LENGTH), nullable=False),
    Column("layer_type", String(LAYER_CODE_MAX_LENGTH), nullable=False),
    Column("layer_name", String(DISPLAY_NAME_MAX_LENGTH), nullable=False),
    Column("status", String(24), nullable=False, default="planned", server_default="planned"),
    Column("is_shared", Boolean, nullable=False, default=False, server_default="false"),
    Column("planned_process_snapshot", json_document, nullable=False),
    Column(
        "planned_snapshot_schema_version",
        Integer,
        nullable=False,
        default=PROCESS_SNAPSHOT_SCHEMA_VERSION,
        server_default=str(PROCESS_SNAPSHOT_SCHEMA_VERSION),
    ),
    Column("planned_canonical_hash", String(64), nullable=False),
    Column("actual_process_snapshot", json_document),
    Column("actual_snapshot_schema_version", Integer),
    Column("actual_canonical_hash", String(64)),
    Column("actual_recording_mode", String(24)),
    Column("equipment_identifier", String(EQUIPMENT_IDENTIFIER_MAX_LENGTH)),
    Column("executed_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("notes", String(BATCH_NOTES_MAX_LENGTH), nullable=False, default="", server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('planned', 'ready', 'running', 'completed', 'failed', 'cancelled')",
        name="valid_execution_status",
    ),
    CheckConstraint(
        "method IN ('spin_coating', 'annealing', 'vcd', 'thermal_evaporation', 'ald', 'sputtering')",
        name="valid_execution_method",
    ),
    CheckConstraint(
        "actual_recording_mode IS NULL OR actual_recording_mode IN "
        "('copied_from_plan', 'entered')",
        name="valid_process_actual_recording_mode",
    ),
    CheckConstraint(
        "(actual_process_snapshot IS NULL AND actual_snapshot_schema_version IS NULL "
        "AND actual_canonical_hash IS NULL AND actual_recording_mode IS NULL) OR "
        "(actual_process_snapshot IS NOT NULL AND actual_snapshot_schema_version IS NOT NULL "
        "AND actual_canonical_hash IS NOT NULL AND actual_recording_mode IS NOT NULL)",
        name="complete_process_actual_metadata",
    ),
)
Index(
    "ix_process_executions_batch_id",
    process_executions.c.fabrication_batch_id,
)

process_execution_members = Table(
    "process_execution_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "process_execution_id",
        ForeignKey("process_executions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "substrate_id",
        ForeignKey("fabrication_substrates.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "batch_condition_id",
        ForeignKey("fabrication_batch_conditions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("layer_ordinal", Integer, nullable=False),
    Column("layer_snapshot_hash", String(64), nullable=False),
    UniqueConstraint(
        "process_execution_id",
        "substrate_id",
        "layer_ordinal",
        name="uq_execution_member_unique",
    ),
)
Index(
    "ix_execution_members_execution_id",
    process_execution_members.c.process_execution_id,
)
Index(
    "ix_execution_members_substrate_id",
    process_execution_members.c.substrate_id,
)

execution_deviations = Table(
    "execution_deviations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "fabrication_batch_id",
        ForeignKey("fabrication_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("category", String(DEVIATION_CATEGORY_MAX_LENGTH), nullable=False),
    Column("severity", String(DEVIATION_SEVERITY_MAX_LENGTH), nullable=False),
    # Semantic type consumed by the workflow gates: only a matching, current
    # typed condition deviation unlocks a shortfall gate (see 0014).
    Column("deviation_type", String(DEVIATION_TYPE_MAX_LENGTH), nullable=False),
    Column("description", Text, nullable=False),
    Column("planned_value", json_document),
    Column("actual_value", json_document),
    Column("recorded_by_id", ForeignKey("users.id", ondelete="SET NULL")),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column(
        "supersedes_deviation_id",
        ForeignKey("execution_deviations.id", ondelete="SET NULL"),
    ),
    Column("solution_preparation_id", ForeignKey("solution_preparations.id", ondelete="SET NULL")),
    Column("process_execution_id", ForeignKey("process_executions.id", ondelete="SET NULL")),
    Column("substrate_id", ForeignKey("fabrication_substrates.id", ondelete="SET NULL")),
    Column("device_id", ForeignKey("fabrication_devices.id", ondelete="SET NULL")),
    Column(
        "condition_id",
        ForeignKey(
            "fabrication_batch_conditions.id",
            ondelete="SET NULL",
            name="fk_execution_deviations_condition_id_fabrication_batch_conditions",
        ),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "severity IN ('info', 'warning', 'error', 'critical')",
        name="valid_deviation_severity",
    ),
    CheckConstraint(
        "category IN ('process', 'material', 'equipment', 'substrate', 'device', 'operator', 'other')",
        name="valid_deviation_category",
    ),
    CheckConstraint(
        "deviation_type IN ('general', 'fabrication_shortfall', "
        "'measurement_shortfall')",
        name="valid_deviation_type",
    ),
    CheckConstraint(
        "(CASE WHEN solution_preparation_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN process_execution_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN substrate_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN device_id IS NULL THEN 0 ELSE 1 END + "
        "CASE WHEN condition_id IS NULL THEN 0 ELSE 1 END) <= 1",
        name="at_most_one_deviation_target",
    ),
)
Index(
    "ix_execution_deviations_batch_id",
    execution_deviations.c.fabrication_batch_id,
)
Index(
    "ix_execution_deviations_supersedes",
    execution_deviations.c.supersedes_deviation_id,
)
Index(
    "ix_execution_deviations_condition_type",
    execution_deviations.c.condition_id,
    execution_deviations.c.deviation_type,
)

device_layout_versions = Table(
    "device_layout_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(LAYOUT_CODE_MAX_LENGTH), nullable=False),
    Column("version", Integer, nullable=False, default=1, server_default="1"),
    Column("substrate_width_mm", Numeric(10, 4), nullable=False),
    Column("substrate_length_mm", Numeric(10, 4), nullable=False),
    Column("devices_per_substrate", Integer, nullable=False),
    Column("device_active_area_cm2", Numeric(10, 4), nullable=False),
    Column("total_active_area_cm2", Numeric(10, 4), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version > 0", name="positive_layout_version"),
    CheckConstraint("devices_per_substrate > 0", name="positive_devices_per_substrate"),
    CheckConstraint("substrate_width_mm > 0", name="positive_substrate_width"),
    CheckConstraint("substrate_length_mm > 0", name="positive_substrate_length"),
    CheckConstraint("device_active_area_cm2 > 0", name="positive_active_area"),
    UniqueConstraint("code", "version", name="uq_device_layouts_code_version"),
)
Index("ix_device_layout_versions_code", device_layout_versions.c.code)


class Database:
    """Own an async SQLAlchemy engine for PostgreSQL or isolated test SQLite."""

    def __init__(self, database_url: str | Path, *, create_schema: bool = False) -> None:
        self.url = normalize_database_url(database_url)
        self.should_create_schema = create_schema
        connect_args = {"timeout": 30} if self.url.startswith("sqlite+") else {}
        self.engine: AsyncEngine = create_async_engine(
            self.url,
            connect_args=connect_args,
            pool_pre_ping=not self.url.startswith("sqlite+"),
        )
        if self.url.startswith("sqlite+"):
            event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)

    async def initialize(self) -> None:
        if not self.should_create_schema:
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        async with self.engine.begin() as connection:
            yield connection


def normalize_database_url(database_url: str | Path) -> str:
    """Return an explicit SQLAlchemy async database URL."""

    if isinstance(database_url, Path):
        return _sqlite_url(database_url)
    value = str(database_url).strip()
    if not value:
        raise ValueError("database URL must not be blank")
    if "://" not in value:
        return _sqlite_url(Path(value))
    if value.startswith("postgresql+asyncpg://"):
        return value
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("sqlite+aiosqlite://"):
        return value
    raise ValueError("database URL must use PostgreSQL; SQLite is allowed only for tests")


def is_postgresql_url(database_url: str) -> bool:
    return database_url.startswith("postgresql+asyncpg://")


def _sqlite_url(path: Path) -> str:
    absolute_path = path.resolve().as_posix()
    return f"sqlite+aiosqlite:///{absolute_path}"


def _enable_sqlite_foreign_keys(
    dbapi_connection: object,
    _connection_record: object,
) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_schema(connection: Connection) -> None:
    """Create the current schema for migration and administration commands."""

    metadata.create_all(connection)
