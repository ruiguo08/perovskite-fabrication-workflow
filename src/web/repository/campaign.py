"""Campaign-domain methods of :class:`web.repository.WebRepository`."""

from __future__ import annotations

from typing import Any, Iterable, Mapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy import insert, select, update

from ..database import CAMPAIGN_CODE_MAX_LENGTH, campaigns
from .helpers import (
    _add_audit_event,
    _as_utc,
    _inserted_id,
    _normalize_display_name,
    _optional_utc,
    _utc_now,
)
from .records import CampaignRecord, CampaignStatus

def _campaign_record(row: Mapping[str, Any]) -> CampaignRecord:
    return CampaignRecord(
        id=int(row["id"]),
        code=str(row["code"]),
        display_name=str(row["display_name"]),
        description=str(row["description"]),
        status=CampaignStatus(row["status"]),
        created_at=_as_utc(row["created_at"]),
        updated_at=_as_utc(row["updated_at"]),
        closed_at=_optional_utc(row["closed_at"]),
        created_by_id=row["created_by_id"],
    )

def _normalize_campaign_code(code: str) -> str:
    normalized = code.strip()
    if not normalized:
        raise ValueError("campaign code must not be blank")
    if len(normalized) > CAMPAIGN_CODE_MAX_LENGTH:
        raise ValueError(
            f"campaign code must not exceed {CAMPAIGN_CODE_MAX_LENGTH} characters"
        )
    return normalized

class CampaignsMixin:
    """Campaign CRUD."""

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------
    async def create_campaign(
        self,
        *,
        code: str,
        display_name: str,
        description: str,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> CampaignRecord:
        normalized_code = _normalize_campaign_code(code)
        normalized_name = _normalize_display_name(display_name)
        now = _utc_now()
        async with self.database.begin() as connection:
            try:
                result = await connection.execute(
                    insert(campaigns).values(
                        code=normalized_code,
                        display_name=normalized_name,
                        description=description.strip(),
                        status=CampaignStatus.ACTIVE.value,
                        created_by_id=actor_user_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            except IntegrityError as error:
                raise ValueError(
                    f"a campaign with code {normalized_code!r} already exists"
                ) from error
            campaign_id = _inserted_id(result)
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="campaign.create",
                entity_type="campaign",
                entity_id=str(campaign_id),
                details={"code": normalized_code},
                client_ip=client_ip,
            )
        return await self.get_campaign_by_id(campaign_id)

    async def get_campaign_by_id(self, campaign_id: int) -> CampaignRecord:
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(campaigns).where(campaigns.c.id == campaign_id)
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown campaign id: {campaign_id}")
        return _campaign_record(row)

    async def get_campaign(self, code: str) -> CampaignRecord:
        normalized = _normalize_campaign_code(code)
        async with self.database.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(campaigns).where(campaigns.c.code == normalized)
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"unknown campaign code: {normalized}")
        return _campaign_record(row)

    async def list_campaigns(
        self,
        *,
        statuses: Iterable[CampaignStatus] | None = None,
    ) -> list[CampaignRecord]:
        statement = select(campaigns).order_by(campaigns.c.code)
        if statuses is not None:
            values = [item.value for item in statuses]
            if not values:
                return []
            statement = statement.where(campaigns.c.status.in_(values))
        async with self.database.engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        return [_campaign_record(row) for row in rows]

    async def update_campaign(
        self,
        code: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        status: CampaignStatus | None = None,
        actor_user_id: int | None,
        client_ip: str | None = None,
    ) -> CampaignRecord:
        normalized_code = _normalize_campaign_code(code)
        values: dict[str, Any] = {"updated_at": _utc_now()}
        if display_name is not None:
            values["display_name"] = _normalize_display_name(display_name)
        if description is not None:
            values["description"] = description.strip()
        if status is not None:
            values["status"] = status.value
            if status in (CampaignStatus.CLOSED, CampaignStatus.ARCHIVED):
                values["closed_at"] = _utc_now()
            elif status == CampaignStatus.ACTIVE:
                values["closed_at"] = None
        async with self.database.begin() as connection:
            result = await connection.execute(
                update(campaigns)
                .where(campaigns.c.code == normalized_code)
                .values(**values)
            )
            if result.rowcount != 1:
                raise KeyError(f"unknown campaign code: {normalized_code}")
            await _add_audit_event(
                connection,
                actor_user_id=actor_user_id,
                action="campaign.update",
                entity_type="campaign",
                entity_id=normalized_code,
                details={k: str(v) for k, v in values.items()},
                client_ip=client_ip,
            )
        return await self.get_campaign(normalized_code)
