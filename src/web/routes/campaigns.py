"""Campaign directory management."""

from .common import *  # noqa: F401,F403


def create_campaigns_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register the campaigns endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    @router.get("/api/campaigns", response_model=list[CampaignResponse])
    async def list_campaigns(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[CampaignResponse]:
        if auth_context.user.role == UserRole.STUDENT:
            records = await repository.list_campaigns(
                statuses={CampaignStatus.ACTIVE}
            )
        else:
            records = await repository.list_campaigns()
        return [_campaign_response(c) for c in records]
    @router.post(
        "/api/campaigns",
        response_model=CampaignResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[
            Depends(require_role(UserRole.INSTRUCTOR)),
            Depends(require_csrf),
        ],
    )
    async def create_campaign(
        request: Request,
        payload: CampaignCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> CampaignResponse:
        try:
            record = await repository.create_campaign(
                code=payload.code,
                display_name=payload.display_name,
                description=payload.description,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        return _campaign_response(record)
    @router.patch(
        "/api/campaigns/{campaign_code}",
        response_model=CampaignResponse,
        dependencies=[
            Depends(require_role(UserRole.INSTRUCTOR)),
            Depends(require_csrf),
        ],
    )
    async def update_campaign(
        request: Request,
        campaign_code: str,
        payload: CampaignUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> CampaignResponse:
        if payload.status is not None and payload.status not in {
            CampaignStatus.ACTIVE.value,
            CampaignStatus.CLOSED.value,
            CampaignStatus.ARCHIVED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be one of: active, closed, archived",
            )
        try:
            record = await repository.update_campaign(
                campaign_code,
                display_name=payload.display_name,
                description=payload.description,
                status=CampaignStatus(payload.status) if payload.status else None,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return _campaign_response(record)
    return router
