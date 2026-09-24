"""Audit-event persistence shared by the repository, services, and operations.

This is a deliberately low-level module: it depends only on the database
metadata and the standard library, so both ``web.repository`` and
``web.services`` can use it without forming an import cycle. Business writes
and their audit records share the caller's transaction/connection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from .database import audit_events


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def add_audit_event(
    connection: AsyncConnection,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    details: dict[str, Any],
    client_ip: str | None,
) -> None:
    """Append one audit event on the caller's connection.

    The caller owns the transaction: the audit row commits (or rolls back)
    together with the business write it documents.
    """

    await connection.execute(
        insert(audit_events).values(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            client_ip=client_ip,
            created_at=utc_now(),
        )
    )
