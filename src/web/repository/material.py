"""Material-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Mapping
from sqlalchemy import and_, insert, or_, select, update

from ..database import (
    MATERIAL_CAS_NUMBER_MAX_LENGTH,
    MATERIAL_CATALOG_NUMBER_MAX_LENGTH,
    MATERIAL_FORMULA_MAX_LENGTH,
    MATERIAL_NAME_MAX_LENGTH,
    MATERIAL_VENDOR_MAX_LENGTH,
    material_products,
    materials,
)
from .helpers import _actor_role, _add_audit_event, _as_utc, _inserted_id, _utc_now
from .records import MATERIAL_CATEGORIES, MATERIAL_STATUSES, ROLE_RANK
from .records import UserRole

import json

def _material_product_record(row: Mapping[str, Any]) -> dict[str, Any]:
    specification = row["specification"]
    if isinstance(specification, str):
        specification = json.loads(specification)
    return {
        "id": int(row["id"]),
        "vendor": str(row["vendor"]),
        "catalog_number": str(row["catalog_number"]),
        "specification": dict(specification),
        "status": str(row["status"]),
        "created_at": _as_utc(row["created_at"]).isoformat(),
        "updated_at": _as_utc(row["updated_at"]).isoformat(),
    }

def _material_record(
    row: Mapping[str, Any],
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    specification = row["specification"]
    if isinstance(specification, str):
        specification = json.loads(specification)
    return {
        "id": int(row["id"]),
        "category": str(row["category"]),
        "name": str(row["name"]),
        "formula": str(row["formula"]),
        "cas_number": str(row["cas_number"]),
        "specification": dict(specification),
        "status": str(row["status"]),
        "products": products,
        "created_at": _as_utc(row["created_at"]).isoformat(),
        "updated_at": _as_utc(row["updated_at"]).isoformat(),
    }

def _normalize_material_category(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in MATERIAL_CATEGORIES:
        choices = ", ".join(sorted(MATERIAL_CATEGORIES))
        raise ValueError(f"material category must be one of: {choices}")
    return normalized

def _normalize_material_status(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in MATERIAL_STATUSES:
        choices = ", ".join(sorted(MATERIAL_STATUSES))
        raise ValueError(f"material status must be one of: {choices}")
    return normalized

def _normalize_material_text(value: str, label: str, max_length: int) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{label} must not exceed {max_length} characters")
    return normalized

def _normalize_material_values(
    name: str,
    formula: str,
    cas_number: str,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": _normalize_material_text(name, "material name", MATERIAL_NAME_MAX_LENGTH),
        "formula": _normalize_optional_material_text(
            formula, MATERIAL_FORMULA_MAX_LENGTH
        ),
        "cas_number": _normalize_optional_material_text(
            cas_number, MATERIAL_CAS_NUMBER_MAX_LENGTH
        ),
        "specification": dict(specification),
    }

def _normalize_optional_material_text(value: str, max_length: int) -> str:
    normalized = str(value).strip()
    if len(normalized) > max_length:
        raise ValueError(f"material text must not exceed {max_length} characters")
    return normalized

def _require_material_manager(actor_role: UserRole) -> None:
    if ROLE_RANK[actor_role] < ROLE_RANK[UserRole.INSTRUCTOR]:
        raise PermissionError("instructor access is required to manage materials")

class MaterialsMixin:
    """Material directory and vendor product management."""

    async def list_materials(
        self,
        *,
        actor_user_id: int,
    ) -> list[dict[str, Any]]:
        """Return active catalog records plus a student's own pending proposals."""

        async with self.database.engine.connect() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            is_manager = ROLE_RANK[actor_role] >= ROLE_RANK[UserRole.INSTRUCTOR]
            statement = select(materials).order_by(materials.c.category, materials.c.name)
            if not is_manager:
                statement = statement.where(
                    or_(
                        materials.c.status == "active",
                        and_(
                            materials.c.status == "pending",
                            materials.c.created_by_id == actor_user_id,
                        ),
                    )
                )
            material_rows = (await connection.execute(statement)).mappings().all()
            material_ids = [int(row["id"]) for row in material_rows]
            if not material_ids:
                return []
            product_statement = select(material_products).where(
                material_products.c.material_id.in_(material_ids)
            )
            if not is_manager:
                product_statement = product_statement.where(
                    or_(
                        material_products.c.status == "active",
                        and_(
                            material_products.c.status == "pending",
                            material_products.c.created_by_id == actor_user_id,
                        ),
                    )
                )
            product_rows = (
                await connection.execute(
                    product_statement.order_by(
                        material_products.c.vendor,
                        material_products.c.catalog_number,
                    )
                )
            ).mappings().all()
        products_by_material: dict[int, list[dict[str, Any]]] = {}
        for row in product_rows:
            products_by_material.setdefault(int(row["material_id"]), []).append(
                _material_product_record(row)
            )
        return [
            _material_record(row, products_by_material.get(int(row["id"]), []))
            for row in material_rows
        ]

    async def create_material(
        self,
        *,
        category: str,
        name: str,
        formula: str,
        cas_number: str,
        specification: Mapping[str, Any],
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Create a pending student proposal or an active staff catalog record."""

        category = _normalize_material_category(category)
        values = _normalize_material_values(name, formula, cas_number, specification)
        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            is_manager = ROLE_RANK[actor_role] >= ROLE_RANK[UserRole.INSTRUCTOR]
            result = await connection.execute(
                insert(materials).values(
                    category=category,
                    **values,
                    status="active" if is_manager else "pending",
                    created_by_id=actor_user_id,
                    reviewed_by_id=actor_user_id if is_manager else None,
                    reviewed_at=now if is_manager else None,
                    created_at=now,
                    updated_at=now,
                )
            )
            material_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="material.create",
                entity_type="material",
                entity_id=str(material_id),
                details={"category": category, "name": values["name"]},
                client_ip=client_ip,
            )
        return await self._get_material_for_actor(material_id, actor_user_id)

    async def update_material(
        self,
        material_id: int,
        *,
        name: str | None,
        formula: str | None,
        cas_number: str | None,
        specification: Mapping[str, Any] | None,
        status: str | None,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Maintain or review a material; only staff can alter shared records."""

        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            _require_material_manager(actor_role)
            row = (
                await connection.execute(
                    select(materials).where(materials.c.id == material_id).with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise KeyError(f"unknown material id: {material_id}")
            values: dict[str, Any] = {"updated_at": now}
            if name is not None:
                values["name"] = _normalize_material_text(
                    name, "material name", MATERIAL_NAME_MAX_LENGTH
                )
            if formula is not None:
                values["formula"] = _normalize_optional_material_text(
                    formula, MATERIAL_FORMULA_MAX_LENGTH
                )
            if cas_number is not None:
                values["cas_number"] = _normalize_optional_material_text(
                    cas_number, MATERIAL_CAS_NUMBER_MAX_LENGTH
                )
            if specification is not None:
                values["specification"] = dict(specification)
            if status is not None:
                values["status"] = _normalize_material_status(status)
                values["reviewed_by_id"] = actor_user_id
                values["reviewed_at"] = now
            await connection.execute(
                update(materials).where(materials.c.id == material_id).values(**values)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="material.update",
                entity_type="material",
                entity_id=str(material_id),
                details={"status": values.get("status", row["status"])},
                client_ip=client_ip,
            )
        return await self._get_material_for_actor(material_id, actor_user_id)

    async def create_material_product(
        self,
        material_id: int,
        *,
        vendor: str,
        catalog_number: str,
        specification: Mapping[str, Any],
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Submit a supplier product for a visible material."""

        vendor = _normalize_material_text(vendor, "vendor", MATERIAL_VENDOR_MAX_LENGTH)
        catalog_number = _normalize_material_text(
            catalog_number, "catalog number", MATERIAL_CATALOG_NUMBER_MAX_LENGTH
        )
        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            material = (
                await connection.execute(
                    select(materials).where(materials.c.id == material_id).with_for_update()
                )
            ).mappings().one_or_none()
            if material is None:
                raise KeyError(f"unknown material id: {material_id}")
            is_manager = ROLE_RANK[actor_role] >= ROLE_RANK[UserRole.INSTRUCTOR]
            if (
                not is_manager
                and material["status"] != "active"
                and not (
                    material["status"] == "pending"
                    and material["created_by_id"] == actor_user_id
                )
            ):
                raise PermissionError("students can add products only to active or own pending materials")
            product_status = "active" if is_manager and material["status"] == "active" else "pending"
            result = await connection.execute(
                insert(material_products).values(
                    material_id=material_id,
                    vendor=vendor,
                    catalog_number=catalog_number,
                    specification=dict(specification),
                    status=product_status,
                    created_by_id=actor_user_id,
                    reviewed_by_id=actor_user_id if product_status == "active" else None,
                    reviewed_at=now if product_status == "active" else None,
                    created_at=now,
                    updated_at=now,
                )
            )
            product_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="material_product.create",
                entity_type="material_product",
                entity_id=str(product_id),
                details={"material_id": material_id, "catalog_number": catalog_number},
                client_ip=client_ip,
            )
        return await self._get_material_for_actor(material_id, actor_user_id)

    async def update_material_product(
        self,
        product_id: int,
        *,
        vendor: str | None,
        catalog_number: str | None,
        specification: Mapping[str, Any] | None,
        status: str | None,
        actor_user_id: int,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Maintain or review a supplier product; only staff can alter it."""

        now = _utc_now()
        async with self.database.begin() as connection:
            actor_role = await _actor_role(connection, actor_user_id)
            _require_material_manager(actor_role)
            row = (
                await connection.execute(
                    select(
                        material_products,
                        materials.c.status.label("material_status"),
                    )
                    .join(materials, materials.c.id == material_products.c.material_id)
                    .where(material_products.c.id == product_id)
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise KeyError(f"unknown material product id: {product_id}")
            values: dict[str, Any] = {"updated_at": now}
            if vendor is not None:
                values["vendor"] = _normalize_material_text(
                    vendor, "vendor", MATERIAL_VENDOR_MAX_LENGTH
                )
            if catalog_number is not None:
                values["catalog_number"] = _normalize_material_text(
                    catalog_number, "catalog number", MATERIAL_CATALOG_NUMBER_MAX_LENGTH
                )
            if specification is not None:
                values["specification"] = dict(specification)
            if status is not None:
                normalized_status = _normalize_material_status(status)
                if normalized_status == "active" and row["material_status"] != "active":
                    raise ValueError("a product cannot be active while its material is not active")
                values["status"] = normalized_status
                values["reviewed_by_id"] = actor_user_id
                values["reviewed_at"] = now
            await connection.execute(
                update(material_products)
                .where(material_products.c.id == product_id)
                .values(**values)
            )
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="material_product.update",
                entity_type="material_product",
                entity_id=str(product_id),
                details={"status": values.get("status", row["status"])},
                client_ip=client_ip,
            )
            material_id = int(row["material_id"])
        return await self._get_material_for_actor(material_id, actor_user_id)

    async def _get_material_for_actor(
        self,
        material_id: int,
        actor_user_id: int,
    ) -> dict[str, Any]:
        records = await self.list_materials(actor_user_id=actor_user_id)
        for record in records:
            if record["id"] == material_id:
                return record
        raise KeyError(f"unknown material id: {material_id}")
