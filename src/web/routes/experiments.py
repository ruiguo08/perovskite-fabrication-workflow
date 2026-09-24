"""Experiment plans: creation, conditions, plan lifecycle, and substrate exceptions."""

from .common import *  # noqa: F401,F403


def create_experiments_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register the experiments endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    @router.get("/experiments/{experiment_id}/export.json")
    async def export_experiment_json(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> Response:
        record = await _get_record_or_404(repository, experiment_id, auth_context)
        payload = build_plan_export(
            record,
            await repository.list_conditions_for_experiment(experiment_id),
            await repository.list_substrate_exceptions_for_experiment(experiment_id),
        )
        return Response(
            content=canonical_plan_json(payload),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="experiment-{experiment_id}-plan.json"'
                )
            },
        )
    @router.get("/experiments/{experiment_id}/export.pdf")
    async def export_experiment_pdf(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> Response:
        record = await _get_record_or_404(repository, experiment_id, auth_context)
        payload = build_plan_export(
            record,
            await repository.list_conditions_for_experiment(experiment_id),
            await repository.list_substrate_exceptions_for_experiment(experiment_id),
        )
        content = await run_in_threadpool(render_plan_pdf, payload)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="experiment-{experiment_id}-plan.pdf"'
                )
            },
        )
    @router.post(
        "/api/experiments",
        response_model=ExperimentResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_experiment_api(
        request: Request,
        payload: RecipePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ExperimentResponse:
        try:
            record = await _create_experiment(
                repository,
                payload.recipe.model_dump(mode="python"),
                campaign_id=(
                    payload.campaign_id
                    if payload.campaign_id is not None
                    else default_campaign_id
                ),
                source_baseline_version_id=payload.source_baseline_version_id,
                condition_plans=(
                    [item.model_dump(mode="python") for item in payload.condition_plans]
                    if payload.condition_plans is not None
                    else None
                ),
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            # The requested baseline version is outside the actor's source-use
            # boundary; report the uniform 404 so its existence is not leaked.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _record_response(record)
    @router.get("/api/experiments", response_model=list[ExperimentResponse])
    async def list_experiments_api(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[ExperimentResponse]:
        return [
            _record_response(record)
            for record in await repository.list_experiments(
                owner_user_id=_student_owner_id(auth_context)
            )
        ]
    @router.get(
        "/api/experiments/{experiment_id}",
        response_model=ExperimentDetailResponse,
    )
    async def get_experiment_detail_api(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ExperimentDetailResponse:
        record = await _get_record_or_404(repository, experiment_id, auth_context)
        return ExperimentDetailResponse(
            experiment=_record_response(record),
            conditions=[
                _condition_response(condition)
                for condition in await repository.list_conditions_for_experiment(
                    experiment_id
                )
            ],
            substrate_exceptions=[
                _substrate_exception_response(exception)
                for exception in await repository.list_active_substrate_exceptions_for_experiment(
                    experiment_id
                )
            ],
            fabrication_batches=[
                _fabrication_batch_response(batch)
                for batch in await repository.list_fabrication_batches_for_experiment(
                    experiment_id
                )
            ],
            results=[
                _result_summary_response(result)
                for result in await repository.list_results_for_experiment(
                    experiment_id
                )
            ],
        )
    @router.get(
        "/api/experiments/{experiment_id}/conditions",
        response_model=list[ConditionResponse],
    )
    async def list_conditions(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[ConditionResponse]:
        await _get_record_or_404(repository, experiment_id, auth_context)
        return [
            _condition_response(record)
            for record in await repository.list_conditions_for_experiment(
                experiment_id
            )
        ]
    @router.get(
        "/api/experiments/{experiment_id}/substrate-exceptions",
        response_model=list[SubstrateExceptionResponse],
    )
    async def list_substrate_exceptions(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[SubstrateExceptionResponse]:
        await _get_record_or_404(repository, experiment_id, auth_context)
        return [
            _substrate_exception_response(record)
            for record in await repository.list_active_substrate_exceptions_for_experiment(
                experiment_id
            )
        ]
    @router.post(
        "/api/experiments/{experiment_id}/conditions",
        response_model=ConditionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_condition(
        request: Request,
        experiment_id: int,
        payload: ConditionCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ConditionResponse:
        await _get_record_or_404(repository, experiment_id, auth_context)
        try:
            record = await repository.create_condition(
                experiment_id=experiment_id,
                role=ConditionRole(payload.role),
                condition_code=None,
                condition_name=payload.condition_name,
                recipe_snapshot=payload.recipe_snapshot.model_dump(mode="python"),
                source_baseline_version_id=payload.source_baseline_version_id,
                device_layout_code=payload.device_layout_code,
                planned_substrate_count=payload.planned_substrate_count,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _condition_response(record)
    @router.put(
        "/api/conditions/{condition_id}",
        response_model=ConditionResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_condition(
        request: Request,
        condition_id: int,
        payload: ConditionUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ConditionResponse:
        condition = await _condition_for_actor(
            repository, condition_id, auth_context
        )
        try:
            record = await repository.update_condition(
                condition.id,
                condition_name=payload.condition_name,
                recipe_snapshot=payload.recipe_snapshot.model_dump(mode="python"),
                source_baseline_version_id=payload.source_baseline_version_id,
                device_layout_code=payload.device_layout_code,
                planned_substrate_count=payload.planned_substrate_count,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _condition_response(record)
    @router.delete(
        "/api/conditions/{condition_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def delete_condition(
        request: Request,
        condition_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> None:
        condition = await _condition_for_actor(
            repository, condition_id, auth_context
        )
        try:
            await repository.delete_condition(
                condition.id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    @router.post(
        "/api/conditions/{condition_id}/substrate-exceptions",
        response_model=SubstrateExceptionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def request_substrate_exception(
        request: Request,
        condition_id: int,
        payload: SubstrateExceptionCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SubstrateExceptionResponse:
        condition = await _condition_for_actor(
            repository, condition_id, auth_context
        )
        try:
            record = await repository.request_substrate_exception(
                condition_id=condition.id,
                requested_count=payload.requested_count,
                reason=payload.reason,
                requested_by_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a pending or approved substrate exception already exists for this condition",
            ) from error
        return _substrate_exception_response(record)
    @router.post(
        "/api/substrate-exceptions/{exception_id}/decision",
        response_model=SubstrateExceptionResponse,
        dependencies=[
            Depends(require_role(UserRole.INSTRUCTOR)),
            Depends(require_csrf),
        ],
    )
    async def decide_substrate_exception(
        request: Request,
        exception_id: int,
        payload: SubstrateExceptionDecisionPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SubstrateExceptionResponse:
        try:
            record = await repository.decide_substrate_exception(
                exception_id,
                decision=ExceptionDecision(payload.decision),
                decided_by_id=auth_context.user.id,
                decision_note=payload.decision_note,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _substrate_exception_response(record)
    @router.patch(
        "/api/experiments/{experiment_id}/plan-status",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def update_plan_status(
        request: Request,
        experiment_id: int,
        payload: PlanStatusUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> None:
        await _get_record_or_404(repository, experiment_id, auth_context)
        try:
            await repository.update_plan_status(
                experiment_id,
                PlanStatus(payload.status),
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return router
