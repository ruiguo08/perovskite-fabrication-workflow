"""Service-layer helpers for the database-authoritative catalog catalogs.

Business rules (read-only layouts, Decimal areas) live here. There is no
factory seed anywhere: materials are student/instructor records, presets are
user records, and layouts are administrator rows created through
``create_device_layout``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from ..audit_trail import add_audit_event as _add_audit_event
from ..database import device_layout_versions
from ..device_layouts import LAYOUT_CODE_MAX_LENGTH, DeviceLayout


async def list_device_layouts(connection: AsyncConnection) -> list[DeviceLayout]:
    """Return the latest immutable version of every device layout code."""

    latest_versions = (
        select(
            device_layout_versions.c.code,
            func.max(device_layout_versions.c.version).label("version"),
        )
        .group_by(device_layout_versions.c.code)
        .subquery()
    )
    rows = (
        await connection.execute(
            select(device_layout_versions)
            .join(
                latest_versions,
                (device_layout_versions.c.code == latest_versions.c.code)
                & (device_layout_versions.c.version == latest_versions.c.version),
            )
            .order_by(device_layout_versions.c.code)
        )
    ).mappings().all()
    return [
        DeviceLayout(
            code=str(row["code"]),
            substrate_width_mm=row["substrate_width_mm"],
            substrate_length_mm=row["substrate_length_mm"],
            devices_per_substrate=int(row["devices_per_substrate"]),
            device_active_area_cm2=row["device_active_area_cm2"],
            total_active_area_cm2=row["total_active_area_cm2"],
            description=str(row["description"]),
            version=int(row["version"]),
        )
        for row in rows
    ]


async def get_device_layout(
    connection: AsyncConnection,
    code: str,
    version: int,
) -> DeviceLayout | None:
    """Return one exact immutable layout version, or None if it does not exist."""

    row = (
        await connection.execute(
            select(device_layout_versions).where(
                device_layout_versions.c.code == code,
                device_layout_versions.c.version == int(version),
            )
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return DeviceLayout(
        code=str(row["code"]),
        substrate_width_mm=row["substrate_width_mm"],
        substrate_length_mm=row["substrate_length_mm"],
        devices_per_substrate=int(row["devices_per_substrate"]),
        device_active_area_cm2=row["device_active_area_cm2"],
        total_active_area_cm2=row["total_active_area_cm2"],
        description=str(row["description"]),
        version=int(row["version"]),
    )


async def resolve_layout(
    connection: AsyncConnection,
    code: str,
    version: int | None = None,
) -> DeviceLayout:
    """Resolve a layout code against the database catalog.

    Without ``version`` the latest version of the code is returned (used when
    a condition selects a layout for the first time). Frozen records must
    pass the version recorded in their ``device_layout_snapshot`` so later
    catalog updates never retroactively change stored geometry.
    """

    if version is not None:
        layout = await get_device_layout(connection, code, int(version))
        if layout is None:
            raise ValueError(
                f"device layout {code!r} version {int(version)} no longer exists"
            )
        return layout
    layouts = await list_device_layouts(connection)
    for layout in layouts:
        if layout.code == code:
            return layout
    raise ValueError(f"unknown device layout code: {code!r}")

async def create_device_layout(
    connection: AsyncConnection,
    *,
    code: str,
    version: int,
    substrate_width_mm: Decimal,
    substrate_length_mm: Decimal,
    devices_per_substrate: int,
    device_active_area_cm2: Decimal,
    total_active_area_cm2: Decimal,
    description: str,
    actor_user_id: int | None = None,
    client_ip: str | None = None,
) -> DeviceLayout:
    """Insert one immutable layout version (administrator-managed catalog).

    Layout rows are never edited: a changed geometry is rolled out as a new
    ``(code, version)`` row while old rows keep serving historical conditions.
    When ``actor_user_id`` is provided, the creation is recorded as an audit
    event — every other catalog creation path writes one, so layouts should
    not be the one catalog change with no provenance.
    """

    normalized_code = str(code).strip()
    if not normalized_code or len(normalized_code) > LAYOUT_CODE_MAX_LENGTH:
        raise ValueError(
            f"layout code must be 1..{LAYOUT_CODE_MAX_LENGTH} characters"
        )
    if int(version) < 1:
        raise ValueError("layout version must be a positive integer")
    if int(devices_per_substrate) < 1:
        raise ValueError("devices per substrate must be at least 1")
    for name, value in (
        ("substrate_width_mm", substrate_width_mm),
        ("substrate_length_mm", substrate_length_mm),
        ("device_active_area_cm2", device_active_area_cm2),
        ("total_active_area_cm2", total_active_area_cm2),
    ):
        # Storage columns are NUMERIC(10, 4): silently rounding a scientific
        # area such as 0.00001 to 0.0000 (or overflowing the 6 integer digits)
        # would corrupt the recorded geometry, so reject instead.
        if not isinstance(value, Decimal) or value <= 0:
            raise ValueError(f"{name} must be a positive decimal")
        # Range before precision: quantize() raises an uncaught
        # decimal.InvalidOperation for huge exponents such as 1e30.
        if value >= Decimal("1000000"):
            raise ValueError(f"{name} must be below 1000000")
        if value != value.quantize(Decimal("0.0001")):
            raise ValueError(
                f"{name} supports at most 4 decimal places (got {value})"
            )
    if not str(description).strip():
        raise ValueError("layout description must not be blank")
    if connection.dialect.name == "postgresql":
        stmt = (
            pg_insert(device_layout_versions)
            .values(
                code=normalized_code,
                version=int(version),
                substrate_width_mm=substrate_width_mm,
                substrate_length_mm=substrate_length_mm,
                devices_per_substrate=int(devices_per_substrate),
                device_active_area_cm2=device_active_area_cm2,
                total_active_area_cm2=total_active_area_cm2,
                description=str(description).strip(),
                created_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(constraint="uq_device_layouts_code_version")
        )
        result = await connection.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(
                f"device layout {normalized_code!r} version {int(version)} already exists"
            )
    else:
        existing = (
            await connection.execute(
                select(device_layout_versions.c.id).where(
                    device_layout_versions.c.code == normalized_code,
                    device_layout_versions.c.version == int(version),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(
                f"device layout {normalized_code!r} version {int(version)} already exists"
            )
        await connection.execute(
            insert(device_layout_versions).values(
                code=normalized_code,
                version=int(version),
                substrate_width_mm=substrate_width_mm,
                substrate_length_mm=substrate_length_mm,
                devices_per_substrate=int(devices_per_substrate),
                device_active_area_cm2=device_active_area_cm2,
                total_active_area_cm2=total_active_area_cm2,
                description=str(description).strip(),
                created_at=datetime.now(timezone.utc),
            )
        )
    if actor_user_id is not None:
        await _add_audit_event(
            connection,
            actor_user_id=actor_user_id,
            action="device_layout.create",
            entity_type="device_layout",
            entity_id=f"{normalized_code}@{int(version)}",
            details={
                "code": normalized_code,
                "version": int(version),
                "devices_per_substrate": int(devices_per_substrate),
            },
            client_ip=client_ip,
        )
    # Return exactly the inserted (code, version) row — never a different
    # (possibly newer) version that happens to share the code.
    return DeviceLayout(
        code=normalized_code,
        version=int(version),
        substrate_width_mm=substrate_width_mm,
        substrate_length_mm=substrate_length_mm,
        devices_per_substrate=int(devices_per_substrate),
        device_active_area_cm2=device_active_area_cm2,
        total_active_area_cm2=total_active_area_cm2,
        description=str(description).strip(),
    )
