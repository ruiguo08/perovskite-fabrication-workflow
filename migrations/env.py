"""Alembic environment for the asynchronous PostgreSQL database."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from web.database import metadata, normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = metadata


def database_url() -> str:
    value = os.environ.get(
        "PEROVSKITE_MIGRATION_DATABASE_URL",
        os.environ.get("PEROVSKITE_DATABASE_URL", ""),
    ).strip()
    if not value:
        raise RuntimeError(
            "PEROVSKITE_MIGRATION_DATABASE_URL or PEROVSKITE_DATABASE_URL "
            "must be set before running Alembic"
        )
    normalized = normalize_database_url(value)
    if not normalized.startswith("postgresql+asyncpg://"):
        raise RuntimeError("Alembic migrations require a PostgreSQL database URL")
    return normalized


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    engine = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
