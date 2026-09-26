"""Application operation: save result analysis assignments and exclusions.

Owns authorization (result existence, role-scoped experiment ownership),
input validation, the pure domain regrouping, the transaction (opened here,
executed by the connection-level data function in
:mod:`web.repository.result`), and the audit record.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..jv_parser import assign_substrates_to_groups
from ..repository.records import UserRole
from .errors import InvalidInput, RecordNotFound


@dataclass(frozen=True)
class ResultAssignmentInput:
    """One substrate-to-condition assignment from the command payload."""

    analysis_substrate_id: str
    batch_condition_id: int


@dataclass(frozen=True)
class ResultExclusionInput:
    """One device exclusion from the command payload."""

    analysis_device_id: str
    reason: str


def batch_result_groups(conditions: Sequence[Any]) -> list[dict[str, Any]]:
    """Project frozen batch conditions into the domain grouping shape used
    by :func:`web.jv_parser.assign_substrates_to_groups`."""

    return [
        {
            "group_id": str(condition.id),
            "batch_condition_id": condition.id,
            "condition_code": condition.condition_code,
            "kind": condition.role,
            "name": condition.condition_name,
        }
        for condition in conditions
    ]


async def save_result_analysis(
    repository,
    *,
    file_id: int,
    assignments: Sequence[ResultAssignmentInput],
    exclusions: Sequence[ResultExclusionInput],
    group_assignment: str | None,
    correction_reason: str | None = None,
    actor_user_id: int,
    actor_role: UserRole | None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    """Authorize, validate, and persist one result-assignment command.

    ``actor_role`` is the authenticated role of the caller; ``None`` is only
    used by the deprecated repository delegate, which keeps that method's
    original no-pre-check semantics (the transaction still enforces batch
    ownership for students).
    """

    # --- Authorization -------------------------------------------------
    # A missing result and a result owned by another student report the
    # same error so the response never reveals existence.
    try:
        result = await repository.get_result(file_id)
    except KeyError as error:
        raise RecordNotFound(str(error)) from error
    if actor_role is not None:
        owner_scope = actor_user_id if actor_role == UserRole.STUDENT else None
        try:
            await repository.get_experiment(
                int(result["experiment_id"]), owner_user_id=owner_scope
            )
        except KeyError as error:
            raise RecordNotFound(str(error)) from error

    # --- Input validation (messages preserved from the historical route) --
    submitted_ids = [item.analysis_substrate_id for item in assignments]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise InvalidInput("duplicate analysis substrate assignments are not allowed")
    exclusion_device_ids = [item.analysis_device_id for item in exclusions]
    if len(exclusion_device_ids) != len(set(exclusion_device_ids)):
        raise InvalidInput("duplicate analysis device exclusions are not allowed")
    expected_ids = {
        str(substrate["substrate_id"])
        for substrate in result.get("analysis", {}).get("substrates", [])
    }
    submitted_set = set(submitted_ids)
    if submitted_set != expected_ids:
        missing = sorted(expected_ids - submitted_set)
        extra = sorted(submitted_set - expected_ids)
        raise InvalidInput(
            "every result substrate must be assigned to a batch condition"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unexpected: {', '.join(extra)}" if extra else "")
        )

    # --- Domain regrouping + transaction --------------------------------
    # The historical route reported regrouping and transaction failures
    # alike as client errors (400), so both share one error boundary.
    # Existence of the result itself was already checked above.
    groups = batch_result_groups(
        await repository.get_fabrication_batch_conditions(
            int(result["fabrication_batch_id"])
        )
    )
    assignments_by_substrate = {
        item.analysis_substrate_id: str(item.batch_condition_id)
        for item in assignments
    }
    exclusions_by_device = {
        item.analysis_device_id: item.reason for item in exclusions
    }
    from ..repository.result import apply_result_assignment

    try:
        grouped_analysis = await asyncio.to_thread(
            assign_substrates_to_groups,
            result["analysis"],
            assignments_by_substrate,
            groups,
            exclusions_by_device,
        )
        counts = {
            str(group["group_id"]): sum(
                substrate.get("group_id") == group["group_id"]
                for substrate in grouped_analysis["substrates"]
            )
            for group in groups
        }
        if group_assignment is None:
            group_assignment = "; ".join(
                f"{group['name']}: {counts[str(group['group_id'])]} substrates"
                for group in groups
            )
        async with repository.database.begin() as connection:
            await apply_result_assignment(
                connection,
                file_id=file_id,
                analysis=grouped_analysis,
                substrate_assignments={
                    key: int(value)
                    for key, value in assignments_by_substrate.items()
                },
                group_assignment=group_assignment,
                correction_reason=correction_reason,
                actor_user_id=actor_user_id,
                client_ip=client_ip,
            )
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidInput(str(error)) from error
    return await repository.get_result(file_id)
