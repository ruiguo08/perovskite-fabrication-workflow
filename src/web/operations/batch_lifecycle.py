"""Application operation: fabrication-batch lifecycle status transitions.

Owns the existence pre-checks, role-scoped ownership authorization, the
transaction boundary, and error translation for moving a fabrication batch
through its status machine — including completion, which records actual
substrate counts, shortfall deviations, and materialized substrates
atomically (see :func:`web.repository.batch.apply_batch_status_update`).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from ..repository.records import BatchStatus, FabricationBatchRecord, UserRole
from .errors import AccessDenied, InvalidInput, RecordNotFound


async def update_batch_status(
    repository,
    *,
    batch_id: int,
    status: BatchStatus,
    actor_user_id: int,
    client_ip: str | None = None,
    actual_substrate_counts: Mapping[int, int] | None = None,
    shortfall_deviations: Sequence[tuple[int, str]] | None = None,
    actor_role: UserRole | None,
) -> FabricationBatchRecord:
    """Authorize and apply one batch status transition.

    ``actor_role`` is the authenticated role of the caller; ``None`` is only
    used by the deprecated repository delegate, which keeps that method's
    original no-pre-check semantics (the transaction still enforces role and
    ownership through the batch row lock).
    """

    # --- Existence and ownership pre-checks -----------------------------
    # A missing batch and a batch of another student's experiment report
    # the same error so the response never reveals existence.
    try:
        batch = await repository.get_fabrication_batch(batch_id)
    except KeyError as error:
        raise RecordNotFound(str(error)) from error
    if actor_role is not None:
        owner_scope = actor_user_id if actor_role == UserRole.STUDENT else None
        try:
            await repository.get_experiment(
                int(batch.experiment_id), owner_user_id=owner_scope
            )
        except KeyError as error:
            raise RecordNotFound(str(error)) from error

    # --- Transaction -----------------------------------------------------
    from ..repository.batch import apply_batch_status_update

    try:
        async with repository.database.begin() as connection:
            await apply_batch_status_update(
                connection,
                batch_id=batch_id,
                status=status,
                actor_user_id=actor_user_id,
                client_ip=client_ip,
                actual_substrate_counts=actual_substrate_counts,
                shortfall_deviations=shortfall_deviations,
            )
    except PermissionError as error:
        raise AccessDenied(str(error)) from error
    except ValueError as error:
        raise InvalidInput(str(error)) from error
    except KeyError as error:
        raise RecordNotFound(str(error)) from error
    return await repository.get_fabrication_batch(batch_id)
