"""Fabrication-device scan history and representative-curve routes.

A physical device may be scanned many times — repeat scans inside one
upload, and fresh uploads days later. The device scan-history endpoint
lists every assigned scan (verbatim per-trace records) with the per-
direction representative the UI shows by default; the representative
endpoint stores the user's explicit choice, which overrides the default
highest-PCE rule until cleared.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .common import (
    AuthContext,
    _client_ip,
    _get_record_or_404,
    require_csrf,
    require_user,
)
from ..models import (
    DeviceJvScansResponse,
    RepresentativeScanPayload,
)
from ..repository import WebRepository


def create_devices_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register fabrication-device scan endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    async def _device_for_actor_or_404(
        device_id: int,
        auth_context: AuthContext,
    ) -> dict[str, Any]:
        try:
            context = await repository.get_fabrication_device_context(device_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="fabrication device not found",
            ) from error
        await _get_record_or_404(repository, int(context["experiment_id"]), auth_context)
        return context

    @router.get(
        "/api/fabrication-devices/{device_id}/jv-scans",
        response_model=DeviceJvScansResponse,
    )
    async def get_device_jv_scans_api(
        device_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> DeviceJvScansResponse:
        await _device_for_actor_or_404(device_id, auth_context)
        return _device_scans_response(
            await repository.get_device_jv_scans(device_id)
        )

    @router.put(
        "/api/fabrication-devices/{device_id}/jv-scans/representative",
        response_model=DeviceJvScansResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def set_representative_scan_api(
        device_id: int,
        request: Request,
        payload: RepresentativeScanPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> DeviceJvScansResponse:
        await _device_for_actor_or_404(device_id, auth_context)
        try:
            await repository.set_representative_scan(
                device_id,
                direction=payload.direction,
                result_file_id=payload.result_file_id,
                trace_id=payload.trace_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="fabrication device not found",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return _device_scans_response(
            await repository.get_device_jv_scans(device_id)
        )

    @router.delete(
        "/api/fabrication-devices/{device_id}/jv-scans/representative",
        response_model=DeviceJvScansResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def clear_representative_scan_api(
        device_id: int,
        request: Request,
        direction: str,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> DeviceJvScansResponse:
        await _device_for_actor_or_404(device_id, auth_context)
        try:
            await repository.clear_representative_scan(
                device_id,
                direction=direction,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        return _device_scans_response(
            await repository.get_device_jv_scans(device_id)
        )

    return router


def _device_scans_response(record: dict[str, Any]) -> DeviceJvScansResponse:
    return DeviceJvScansResponse(
        **{
            field_name: record[field_name]
            for field_name in DeviceJvScansResponse.model_fields
        }
    )
