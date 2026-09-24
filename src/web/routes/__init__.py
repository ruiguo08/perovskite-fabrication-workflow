"""HTTP route package: domain routers composed by :func:`create_router`.

Each domain module owns one endpoint group and delegates state changes to the
application operations in :mod:`web.operations`; :mod:`.common` holds the
cross-domain helpers and the OperationError-to-HTTP mapping. This module keeps
``create_router`` as the single assembly entry point used by ``web.app``.
"""

from fastapi import APIRouter

from .common import *  # noqa: F401,F403
from .batches import create_batches_router
from .campaigns import create_campaigns_router
from .catalogs import create_catalogs_router
from .devices import create_devices_router
from .experiments import create_experiments_router
from .results import create_results_router


def create_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Create authenticated JSON API and export routes for the laboratory workflow."""

    router = APIRouter(dependencies=[Depends(require_user)])
    router.include_router(create_experiments_router(repository, default_campaign_id=default_campaign_id))
    router.include_router(create_results_router(repository, default_campaign_id=default_campaign_id))
    router.include_router(create_catalogs_router(repository, default_campaign_id=default_campaign_id))
    router.include_router(create_campaigns_router(repository, default_campaign_id=default_campaign_id))
    router.include_router(create_batches_router(repository, default_campaign_id=default_campaign_id))
    router.include_router(create_devices_router(repository, default_campaign_id=default_campaign_id))
    return router
