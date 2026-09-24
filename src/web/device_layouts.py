"""Versioned, read-only device layout catalog.

Students cannot freely enter substrate dimensions, device counts, or active
areas. The catalog is database-authoritative: administrators create layouts
through ``POST /api/device-layouts`` (see ``catalog_service``), and every
plan condition selects one layout.

Areas are stored as :class:`~decimal.Decimal` / SQL ``NUMERIC`` so that binary
float rounding never corrupts a scientific area such as 0.05 cm². To change a
layout, create a new row with the same ``code`` and a bumped ``version``; the
old row remains for historical conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

LAYOUT_CODE_MAX_LENGTH = 40


@dataclass(frozen=True)
class DeviceLayout:
    """One immutable device layout entry."""

    code: str
    substrate_width_mm: Decimal
    substrate_length_mm: Decimal
    devices_per_substrate: int
    device_active_area_cm2: Decimal
    total_active_area_cm2: Decimal
    description: str
    version: int = 1


def expected_device_count(planned_substrate_count: int, layout: DeviceLayout) -> int:
    """Number of devices a condition is expected to produce."""

    if planned_substrate_count < 1:
        raise ValueError("planned substrate count must be at least 1")
    return planned_substrate_count * layout.devices_per_substrate


def layout_snapshot(layout: DeviceLayout) -> dict[str, Any]:
    """Return the immutable catalog fields copied into a condition."""

    return {
        "code": layout.code,
        "version": layout.version,
        "substrate_width_mm": str(layout.substrate_width_mm),
        "substrate_length_mm": str(layout.substrate_length_mm),
        "devices_per_substrate": layout.devices_per_substrate,
        "device_active_area_cm2": str(layout.device_active_area_cm2),
        "total_active_area_cm2": str(layout.total_active_area_cm2),
        "description": layout.description,
    }
