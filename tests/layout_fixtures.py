"""Shared device-layout fixtures for tests that need an admin-seeded catalog.

The device-layout catalog is database-authoritative with no factory seed, so
test databases start empty. Tests that create experiments, conditions, or
batches call :func:`seed_standard_layouts` once in ``setUp`` (while logged in
as an administrator) to build the four reference layouts through the same
admin API the UI uses.
"""

STANDARD_LAYOUTS = [
    {
        "code": "15x15_dual_005",
        "version": 1,
        "substrate_width_mm": "15",
        "substrate_length_mm": "15",
        "devices_per_substrate": 2,
        "device_active_area_cm2": "0.05",
        "total_active_area_cm2": "0.10",
        "description": "15 × 15 mm substrate, 2 devices, 0.05 cm² each",
    },
    {
        "code": "20x20_single_1cm2",
        "version": 1,
        "substrate_width_mm": "20",
        "substrate_length_mm": "20",
        "devices_per_substrate": 1,
        "device_active_area_cm2": "1.00",
        "total_active_area_cm2": "1.00",
        "description": "20 × 20 mm substrate, 1 device, 1.00 cm²",
    },
    {
        "code": "25x25_six_010",
        "version": 1,
        "substrate_width_mm": "25",
        "substrate_length_mm": "25",
        "devices_per_substrate": 6,
        "device_active_area_cm2": "0.10",
        "total_active_area_cm2": "0.60",
        "description": "25 × 25 mm substrate, 6 devices, 0.10 cm² each",
    },
    {
        "code": "25x25_single_1cm2",
        "version": 2,
        "substrate_width_mm": "25",
        "substrate_length_mm": "25",
        "devices_per_substrate": 1,
        "device_active_area_cm2": "1.017",
        "total_active_area_cm2": "1.017",
        "description": "25 × 25 mm substrate, 1 device, 1.017 cm²",
    },
]


def seed_standard_layouts(client) -> None:
    """Create the four standard layouts via the admin API (idempotent)."""

    for layout in STANDARD_LAYOUTS:
        client.post("/api/device-layouts", json=layout)


def fixture_layouts():
    """The standard catalog as DeviceLayout objects (for repository-level tests)."""

    from decimal import Decimal

    from web.device_layouts import DeviceLayout

    return [
        DeviceLayout(
            code=layout["code"],
            version=int(layout["version"]),
            substrate_width_mm=Decimal(layout["substrate_width_mm"]),
            substrate_length_mm=Decimal(layout["substrate_length_mm"]),
            devices_per_substrate=int(layout["devices_per_substrate"]),
            device_active_area_cm2=Decimal(layout["device_active_area_cm2"]),
            total_active_area_cm2=Decimal(layout["total_active_area_cm2"]),
            description=layout["description"],
        )
        for layout in STANDARD_LAYOUTS
    ]


def fixture_layout(code: str):
    """One standard catalog layout by code (latest version)."""

    return next(layout for layout in fixture_layouts() if layout.code == code)


async def seed_standard_layouts_async(database) -> None:
    """Seed the standard layouts straight into a database (repository-level tests)."""

    from decimal import Decimal

    from web.services.catalog_service import create_device_layout

    async with database.engine.begin() as connection:
        for layout in STANDARD_LAYOUTS:
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
                )
            except ValueError:
                pass  # already present
