"""Safe command-line administration for the PostgreSQL web database."""

from __future__ import annotations

import argparse
import asyncio
import csv
import getpass
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .auth import hash_password, normalize_username
from .database import Database, is_postgresql_url, normalize_database_url
from .repository import UserRole, WebRepository


def _expected_migration_head() -> str:
    """Load the Alembic head revision from the ScriptDirectory, not a
    hard-coded string, so a new forward migration is the head automatically.

    The config path comes from ``PEROVSKITE_ALEMBIC_CONFIG`` (set by systemd
    units) or falls back to the source-tree ``alembic.ini`` for development.
    """
    config_path = os.environ.get("PEROVSKITE_ALEMBIC_CONFIG", "")
    if not config_path:
        source_root = Path(__file__).resolve().parents[2]
        config_path = str(source_root / "alembic.ini")
    config = AlembicConfig(config_path)
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(
            f"expected exactly one Alembic head, found {len(heads)}: {heads}"
        )
    return heads[0]


async def _is_pre_squash_database(connection: Any) -> bool:
    """Detect a database stamped with the old pre-squash 0007 chain.

    The old chain left ``substrate_mark`` at width 3 and ``device_mark`` at
    width 4; the squashed initial schema widened them to 9.  Either column
    missing entirely or at the old width indicates an incompatible database.
    """

    sub_width = await connection.scalar(
        text(
            "SELECT character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_name='fabrication_substrates' "
            "AND column_name='substrate_mark'"
        )
    )
    dev_width = await connection.scalar(
        text(
            "SELECT character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_name='fabrication_devices' "
            "AND column_name='device_mark'"
        )
    )
    # Old chain: substrate_mark=3, device_mark=4
    # Squashed: substrate_mark=9, device_mark=9
    # Missing columns or old widths → pre-squash (incompatible)
    if sub_width is None or dev_width is None:
        return True
    return int(sub_width) == 3 or int(dev_width) == 4


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        prog="perovskite-workflow-admin",
        description="Manage local accounts without exposing an account-creation API.",
    )
    command_parser.add_argument(
        "--database-url",
        help="PostgreSQL URL; defaults to PEROVSKITE_DATABASE_URL",
    )
    subcommands = command_parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check-database", help="Check connectivity and migrations")
    subcommands.add_parser("list-users", help="List local users without password hashes")
    subcommands.add_parser(
        "cleanup-sessions", help="Delete expired sessions from the database"
    )
    export = subcommands.add_parser(
        "export-audit", help="Export audit events as JSON lines or CSV"
    )
    export.add_argument("--since", help="Inclusive ISO-8601 lower bound")
    export.add_argument("--until", help="Inclusive ISO-8601 upper bound")
    export.add_argument("--actor", help="Filter by actor username")
    export.add_argument("--action", help="Filter by action prefix")
    export.add_argument(
        "--format", choices=["json", "csv"], default="json"
    )
    export.add_argument(
        "--limit", type=int, default=10_000, help="Maximum rows to export"
    )
    training = subcommands.add_parser(
        "export-training-data",
        help="Export (X, y) training rows for completed batches",
    )
    training.add_argument("--experiment-id", type=int)
    training.add_argument("--batch-id", type=int)
    training.add_argument("--format", choices=["json", "csv"], default="json")
    export_catalog = subcommands.add_parser(
        "export-catalog",
        help="Export catalog data (layouts, materials, presets, baselines) as one JSON document",
    )
    export_catalog.add_argument(
        "--output",
        default="-",
        help="Output file path; '-' (default) writes JSON to stdout",
    )
    import_catalog = subcommands.add_parser(
        "import-catalog",
        help="Import catalog data exported by export-catalog (idempotent: existing names are skipped)",
    )
    import_catalog.add_argument(
        "input",
        help="JSON file path exported by export-catalog (use '-' for stdin)",
    )
    import_catalog.add_argument(
        "--actor",
        required=True,
        help="Username recorded as the importer for audit events",
    )
    subcommands.add_parser(
        "status", help="Print maintenance counters for monitoring"
    )
    create = subcommands.add_parser("create-user", help="Create a local user")
    create.add_argument("username")
    create.add_argument("--display-name", required=True)
    create.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in UserRole],
    )
    return command_parser


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    database_url = (args.database_url or os.environ.get("PEROVSKITE_DATABASE_URL", "")).strip()
    if not database_url:
        raise SystemExit("PEROVSKITE_DATABASE_URL or --database-url is required")
    normalized_url = normalize_database_url(database_url)
    if not is_postgresql_url(normalized_url):
        raise SystemExit("administration commands require PostgreSQL")
    database = Database(normalized_url)
    asyncio.run(_run_and_dispose(args, database))


async def _run_and_dispose(args: argparse.Namespace, database: Database) -> None:
    try:
        await run_command(args, database)
    finally:
        await database.dispose()


def _parse_timestamp_bound(value: str | None, label: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise SystemExit(f"--{label} must be an ISO-8601 timestamp: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


AUDIT_CSV_HEADER = [
    "id",
    "created_at",
    "actor_username",
    "action",
    "entity_type",
    "entity_id",
    "client_ip",
    "details",
]


async def _run_export_audit(args: argparse.Namespace, repository: Any) -> None:
    since = _parse_timestamp_bound(args.since, "since")
    until = _parse_timestamp_bound(args.until, "until")
    actor_user_id: int | None = None
    if args.actor:
        user = await repository.get_user_by_username(args.actor)
        if user is None:
            print(f"unknown actor username: {args.actor}")
            raise SystemExit(1)
        actor_user_id = user.id
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    events = await repository.list_audit_events(
        since=since,
        until=until,
        actor_user_id=actor_user_id,
        action_prefix=args.action,
        limit=args.limit,
    )
    if args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(AUDIT_CSV_HEADER)
        for event in events:
            writer.writerow(
                [
                    event.id,
                    event.created_at.isoformat(),
                    event.actor_username or "",
                    event.action,
                    event.entity_type,
                    event.entity_id or "",
                    event.client_ip or "",
                    json.dumps(event.details, sort_keys=True),
                ]
            )
    else:
        for event in events:
            print(
                json.dumps(
                    {
                        "id": event.id,
                        "created_at": event.created_at.isoformat(),
                        "actor_user_id": event.actor_user_id,
                        "actor_username": event.actor_username,
                        "action": event.action,
                        "entity_type": event.entity_type,
                        "entity_id": event.entity_id,
                        "client_ip": event.client_ip,
                        "details": event.details,
                    }
                )
            )


TRAINING_META_COLUMNS = [
    "batch_condition_id",
    "experiment_id",
    "batch_id",
    "batch_code",
    "batch_status",
    "condition_code",
    "condition_name",
    "role",
    "source_condition_hash",
    "result_file_ids",
    "excluded_device_count",
    "feature_source",
    "variant_index",
    "substrate_ids",
    "export_schema_version",
    "exported_at",
]
TRAINING_METRIC_COLUMNS = [
    "device_count",
    "voc",
    "jsc",
    "ff",
    "pce",
    "pce_mean",
    "pce_best",
    "hysteresis_index",
]


async def _run_export_training_data(args: argparse.Namespace, repository: Any) -> None:
    if args.experiment_id is None and args.batch_id is None:
        raise SystemExit("provide --experiment-id or --batch-id")
    rows = await repository.build_training_dataset(
        experiment_id=args.experiment_id,
        batch_id=args.batch_id,
    )
    # Self-description: the header leads the JSON output and its field lists
    # match the CSV columns, so a consumer can validate the shape and units
    # without reading this source.
    from perovskite_bo.web_adapter import (
        TRAINING_EXPORT_SCHEMA_VERSION,
        training_export_header,
    )

    exported_at = datetime.now(timezone.utc).isoformat()
    if args.format == "json":
        header = training_export_header()
        header["exported_at"] = exported_at
        print(json.dumps(header))
        for row in rows:
            print(
                json.dumps(
                    {
                        "record_type": "data",
                        "export_schema_version": TRAINING_EXPORT_SCHEMA_VERSION,
                        "exported_at": exported_at,
                        **row,
                    }
                )
            )
        return
    from perovskite_bo.web_adapter import search_space_parameter_names

    parameter_names = search_space_parameter_names()
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            *TRAINING_META_COLUMNS,
            *parameter_names,
            *TRAINING_METRIC_COLUMNS,
        ]
    )
    for row in rows:
        metrics = row["metrics"] or {}
        meta_values = []
        for column in TRAINING_META_COLUMNS:
            if column in ("export_schema_version", "exported_at"):
                continue
            value = row[column]
            if column == "substrate_ids":
                value = ";".join(str(item) for item in value)
            meta_values.append(value)
        writer.writerow(
            meta_values
            + [TRAINING_EXPORT_SCHEMA_VERSION, exported_at]
            + [row["features"].get(name) for name in parameter_names]
            + [metrics.get(name) for name in TRAINING_METRIC_COLUMNS]
        )


CATALOG_EXPORT_SCHEMA_VERSION = 1


async def _collect_catalog_export(repository: Any) -> dict[str, Any]:
    """Snapshot every catalog table the deployment relies on.

    Only user-independent directory data is exported: device layouts,
    materials (with products), layer presets, and baselines. Accounts,
    experiments, and audit events stay in their database of origin.
    """

    from sqlalchemy import and_, select

    from web import database as db
    from web.services.catalog_service import list_device_layouts
    from web.repository import (
        _baseline_record,
        _baseline_statement,
        _layer_preset_record,
        _layer_preset_statement,
        _material_record,
    )

    async with repository.database.engine.connect() as connection:
        layouts = await list_device_layouts(connection)
        # Only active materials are exported: a student's still-pending
        # proposal must not ride the transfer path into another database,
        # where import (run by an instructor/administrator) would
        # auto-activate it and bypass the review gate.
        material_rows = (
            await connection.execute(
                select(db.materials)
                .where(db.materials.c.status == "active")
                .order_by(db.materials.c.category, db.materials.c.name)
            )
        ).mappings().all()
        # Likewise only products that already passed review can transfer.
        product_rows = (
            await connection.execute(
                select(db.material_products)
                .where(db.material_products.c.status == "active")
                .order_by(db.material_products.c.id)
            )
        ).mappings().all()
        # Only shared presets and baselines transfer: personal records are
        # owned by one user, and import would silently re-scope them (the
        # importing operator becomes the owner / a student's personal
        # baseline would become shared). The transfer path is for the lab's
        # reviewed shared directory only.
        preset_rows = (
            await connection.execute(
                _layer_preset_statement()
                .where(
                    and_(
                        db.layer_presets.c.status == "active",
                        db.layer_presets.c.scope == "shared",
                    )
                )
                .order_by(db.layer_presets.c.name)
            )
        ).mappings().all()
        baseline_rows = (
            await connection.execute(
                _baseline_statement()
                .where(
                    and_(
                        db.baselines.c.status == "active",
                        db.baselines.c.scope == "shared",
                    )
                )
                .order_by(db.baselines.c.name)
            )
        ).mappings().all()

    products_by_material: dict[int, list[dict[str, Any]]] = {}
    for row in product_rows:
        specification = row["specification"]
        if isinstance(specification, str):
            specification = json.loads(specification)
        products_by_material.setdefault(int(row["material_id"]), []).append(
            {
                "vendor": str(row["vendor"]),
                "catalog_number": str(row["catalog_number"]),
                "specification": dict(specification),
                "status": str(row["status"]),
            }
        )
    material_records = [
        _material_record(row, products_by_material.get(int(row["id"]), []))
        for row in material_rows
    ]
    preset_records = [_layer_preset_record(row) for row in preset_rows]
    baseline_records = [_baseline_record(row) for row in baseline_rows]
    return {
        "export_schema_version": CATALOG_EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "device_layouts": [
            {
                "code": layout.code,
                "version": layout.version,
                "substrate_width_mm": str(layout.substrate_width_mm),
                "substrate_length_mm": str(layout.substrate_length_mm),
                "devices_per_substrate": layout.devices_per_substrate,
                "device_active_area_cm2": str(layout.device_active_area_cm2),
                "total_active_area_cm2": str(layout.total_active_area_cm2),
                "description": layout.description,
            }
            for layout in layouts
        ],
        "materials": [
            {
                "category": material["category"],
                "name": material["name"],
                "formula": material["formula"],
                "cas_number": material["cas_number"],
                "specification": material["specification"],
                "status": material["status"],
                "products": [
                    {
                        "vendor": product["vendor"],
                        "catalog_number": product["catalog_number"],
                        "specification": product["specification"],
                        "status": product["status"],
                    }
                    for product in material["products"]
                ],
            }
            for material in material_records
        ],
        "layer_presets": [
            {
                "name": preset["name"],
                "scope": preset["scope"],
                "layer": preset["layer"],
                "deposition_process": preset["deposition_process"],
            }
            for preset in preset_records
        ],
        "baselines": [
            {
                "name": baseline["name"],
                "scope": baseline["scope"],
                "device_recipe": baseline["device_recipe"],
                "deposition_process": baseline["deposition_process"],
            }
            for baseline in baseline_records
        ],
    }


async def _run_export_catalog(
    args: argparse.Namespace, repository: Any
) -> None:
    document = await _collect_catalog_export(repository)
    payload = json.dumps(document, indent=2, sort_keys=True)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload, encoding="utf-8")
        counts = {key: len(document[key]) for key in (
            "device_layouts", "materials", "layer_presets", "baselines"
        )}
        print(f"Wrote {counts} to {args.output}")


async def _find_material_id_on(
    connection: Any, category: str, name: str
) -> int | None:
    """Resolve an existing material by its unique (category, name)."""

    from sqlalchemy import select

    from web import database as db

    return await connection.scalar(
        select(db.materials.c.id).where(
            db.materials.c.category == category,
            db.materials.c.name == name,
        )
    )


async def _existing_material_id(database: Database, category: str, name: str) -> int | None:
    async with database.engine.connect() as connection:
        return await _find_material_id_on(connection, category, name)


async def _existing_product_id(
    database: Database, material_id: int, vendor: str, catalog_number: str
) -> int | None:
    from sqlalchemy import select

    from web import database as db

    async with database.engine.connect() as connection:
        return await connection.scalar(
            select(db.material_products.c.id).where(
                db.material_products.c.material_id == material_id,
                db.material_products.c.vendor == vendor,
                db.material_products.c.catalog_number == catalog_number,
            )
        )


async def _existing_preset_id(
    database: Database, name: str, scope: str
) -> int | None:
    """A shared preset exists when its (scope='shared', name) is taken.

    Personal presets are not exported (shared-scope filter), so this check
    only ever sees shared rows.
    """

    from sqlalchemy import select

    from web import database as db

    async with database.engine.connect() as connection:
        return await connection.scalar(
            select(db.layer_presets.c.id).where(
                db.layer_presets.c.name == name,
                db.layer_presets.c.scope == scope,
            )
        )


async def _existing_baseline_id(database: Database, name: str) -> int | None:
    from sqlalchemy import select

    from web import database as db

    async with database.engine.connect() as connection:
        return await connection.scalar(
            select(db.baselines.c.id).where(
                db.baselines.c.name == name,
                db.baselines.c.scope == "shared",
            )
        )


async def _run_import_catalog(
    args: argparse.Namespace, database: Database, repository: Any
) -> None:
    from decimal import Decimal

    from web.services.catalog_service import create_device_layout

    actor = await repository.get_user_by_username(args.actor)
    if actor is None:
        print(f"unknown actor username: {args.actor}")
        raise SystemExit(1)
    if actor.role not in (UserRole.INSTRUCTOR, UserRole.ADMINISTRATOR):
        print("the importer account must be an instructor or administrator")
        raise SystemExit(1)

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.input).read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit(f"input is not valid JSON: {error}") from error
    if (
        not isinstance(document, dict)
        or document.get("export_schema_version") != CATALOG_EXPORT_SCHEMA_VERSION
    ):
        raise SystemExit(
            "input is not a catalog export produced by export-catalog "
            f"(expected schema version {CATALOG_EXPORT_SCHEMA_VERSION})"
        )

    created = {"device_layouts": 0, "materials": 0, "material_products": 0, "layer_presets": 0, "baselines": 0}
    skipped = 0
    actor_user_id = actor.id

    # Idempotency is pre-check based (SELECT before INSERT), not
    # IntegrityError recovery: on PostgreSQL a constraint violation marks the
    # whole transaction failed, so per-item catch-and-continue cannot work
    # there. Pre-checks behave identically on SQLite and PostgreSQL.
    async with database.engine.connect() as connection:
        for layout in document.get("device_layouts", []):
            from web.services.catalog_service import get_device_layout

            existing_layout = await get_device_layout(
                connection,
                str(layout["code"]).strip(),
                int(layout["version"]),
            )
            if existing_layout is not None:
                skipped += 1
                continue
            try:
                await create_device_layout(
                    connection,
                    code=layout["code"],
                    version=int(layout["version"]),
                    substrate_width_mm=Decimal(layout["substrate_width_mm"]),
                    substrate_length_mm=Decimal(layout["substrate_length_mm"]),
                    devices_per_substrate=int(layout["devices_per_substrate"]),
                    device_active_area_cm2=Decimal(layout["device_active_area_cm2"]),
                    total_active_area_cm2=Decimal(layout["total_active_area_cm2"]),
                    description=layout["description"],
                    actor_user_id=actor_user_id,
                )
                created["device_layouts"] += 1
            except ValueError as error:
                print(f"device layout {layout.get('code')!r} rejected: {error}")
                raise SystemExit(1)
        await connection.commit()

    for material in document.get("materials", []):
        # The material may already exist in the target database; products
        # still need importing (a prior interrupted import, or products added
        # on the source after the first transfer), so resolve the id either
        # way and always run the product loop.
        existing_id = await _existing_material_id(
            database, material["category"], material["name"]
        )
        if existing_id is not None:
            skipped += 1
            material_id = existing_id
        else:
            try:
                record = await repository.create_material(
                    category=material["category"],
                    name=material["name"],
                    formula=material["formula"],
                    cas_number=material["cas_number"],
                    specification=material.get("specification") or {},
                    actor_user_id=actor_user_id,
                )
                created["materials"] += 1
                material_id = record["id"]
            except ValueError as error:
                print(f"material {material.get('name')!r} rejected: {error}")
                raise SystemExit(1)
        for product in material.get("products", []):
            product_exists = await _existing_product_id(
                database, material_id, product["vendor"], product["catalog_number"]
            )
            if product_exists is not None:
                skipped += 1
                continue
            try:
                await repository.create_material_product(
                    material_id,
                    vendor=product["vendor"],
                    catalog_number=product["catalog_number"],
                    specification=product.get("specification") or {},
                    actor_user_id=actor_user_id,
                )
                created["material_products"] += 1
            except ValueError as error:
                print(
                    f"product {product.get('catalog_number')!r} rejected: {error}"
                )
                raise SystemExit(1)

    for preset in document.get("layer_presets", []):
        if await _existing_preset_id(database, preset["name"], preset.get("scope") or "shared") is not None:
            skipped += 1
            continue
        try:
            await repository.create_layer_preset(
                name=preset["name"],
                layer=preset["layer"],
                deposition_process=preset.get("deposition_process"),
                scope=preset.get("scope") or "shared",
                actor_user_id=actor_user_id,
            )
            created["layer_presets"] += 1
        except (ValueError, PermissionError) as error:
            print(f"layer preset {preset.get('name')!r} rejected: {error}")
            raise SystemExit(1)

    for baseline in document.get("baselines", []):
        if await _existing_baseline_id(database, baseline["name"]) is not None:
            skipped += 1
            continue
        try:
            # Same validation as the API path (_baseline_values): an import
            # document is untrusted input, so the stored snapshot must pass
            # full recipe/process validation, not just the schema version.
            from web.routes import _baseline_values
            from web.models import BaselinePayload

            normalized = _baseline_values(
                BaselinePayload.model_validate(
                    {
                        "name": baseline["name"],
                        "device_recipe": baseline["device_recipe"],
                        "deposition_process": baseline["deposition_process"],
                    }
                )
            )
            await repository.save_baseline(
                normalized[0],
                normalized[1],
                normalized[2],
                actor_user_id=actor_user_id,
            )
            created["baselines"] += 1
        except ValueError as error:
            print(f"baseline {baseline.get('name')!r} rejected: {error}")
            raise SystemExit(1)

    print(f"Created {created}.")
    print(f"Skipped {skipped} already-existing record(s).")


async def run_command(args: argparse.Namespace, database: Database) -> None:
    repository = WebRepository(database)
    if args.command == "check-database":
        expected_head = _expected_migration_head()
        async with database.engine.connect() as connection:
            # Pre-squash fingerprint detection: reject databases stamped with
            # the old 0007 chain before any normal table queries.
            if await _is_pre_squash_database(connection):
                print(
                    "database has the old pre-squash schema "
                    "(substrate_mark width=3); recreate from a verified "
                    "backup before running migrations"
                )
                raise SystemExit(1)
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            await connection.execute(text("SELECT 1 FROM users LIMIT 1"))
        if revision != expected_head:
            print(
                f"database schema revision is {revision} but expected "
                f"{expected_head}; run alembic upgrade head"
            )
            raise SystemExit(1)
        print(f"Database is reachable; schema revision: {revision}")
        return
    if args.command == "cleanup-sessions":
        deleted = await repository.delete_expired_sessions(
            datetime.now(timezone.utc)
        )
        print(f"Deleted {deleted} expired session(s).")
        return
    if args.command == "export-audit":
        await _run_export_audit(args, repository)
        return
    if args.command == "export-training-data":
        await _run_export_training_data(args, repository)
        return
    if args.command == "export-catalog":
        await _run_export_catalog(args, repository)
        return
    if args.command == "import-catalog":
        await _run_import_catalog(args, database, repository)
        return
    if args.command == "status":
        counters = await repository.maintenance_status(
            now=datetime.now(timezone.utc)
        )
        for key in sorted(counters):
            print(f"{key}: {counters[key]}")
        return
    if args.command == "list-users":
        for user in await repository.list_users():
            state = "active" if user.is_active else "disabled"
            print(f"{user.username}\t{user.role.value}\t{state}\t{user.display_name}")
        return
    if args.command == "create-user":
        try:
            username = normalize_username(args.username)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        display_name = args.display_name.strip()
        if not display_name:
            raise SystemExit("display name must not be blank")
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("passwords do not match")
        try:
            user = await repository.create_user(
                username=username,
                display_name=display_name,
                password_hash=hash_password(password, username=username),
                role=UserRole(args.role),
            )
        except IntegrityError as error:
            raise SystemExit(f"user {username!r} already exists") from error
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print(f"Created {user.role.value} account {user.username!r}.")
        return
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
