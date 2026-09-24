"""Fabrication batches: freezing, run sheets, lifecycle, and exports."""

from .common import *  # noqa: F401,F403


def create_batches_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register the batches endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    @router.post(
        "/api/experiments/{experiment_id}/fabrication-batches",
        response_model=FabricationBatchResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_fabrication_batch(
        request: Request,
        experiment_id: int,
        payload: FabricationBatchCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> FabricationBatchResponse:
        await _get_record_or_404(repository, experiment_id, auth_context)
        try:
            record = await repository.create_fabrication_batch(
                experiment_id=experiment_id,
                notes=payload.notes,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except (PermissionError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return _fabrication_batch_response(record)
    @router.get(
        "/api/experiments/{experiment_id}/fabrication-batches",
        response_model=list[FabricationBatchResponse],
    )
    async def list_fabrication_batches(
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[FabricationBatchResponse]:
        await _get_record_or_404(repository, experiment_id, auth_context)
        return [
            _fabrication_batch_response(record)
            for record in await repository.list_fabrication_batches_for_experiment(
                experiment_id
            )
        ]
    @router.get(
        "/api/fabrication-batches/{batch_id}",
        response_model=FabricationBatchResponse,
    )
    async def get_fabrication_batch(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> FabricationBatchResponse:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return _fabrication_batch_response(record)
    @router.get(
        "/api/fabrication-batches",
        response_model=list[FabricationBatchListItemResponse],
    )
    async def list_fabrication_batches_api(
        auth_context: Annotated[AuthContext, Depends(require_user)],
        status: BatchStatus | None = None,
        experiment_id: int | None = None,
    ) -> list[FabricationBatchListItemResponse]:
        if experiment_id is not None:
            await _get_record_or_404(repository, experiment_id, auth_context)
        return [
            _fabrication_batch_list_item_response(item)
            for item in await repository.list_fabrication_batches_for_actor(
                _student_owner_id(auth_context),
                status=status,
                experiment_id=experiment_id,
            )
        ]
    @router.get(
        "/api/fabrication-batches/{batch_id}/run-sheet",
        response_model=RunSheetResponse,
    )
    async def get_fabrication_batch_run_sheet(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> RunSheetResponse:
        await _batch_for_actor_or_404(repository, batch_id, auth_context)
        sheet = await repository.get_batch_run_sheet(batch_id)
        return RunSheetResponse(
            batch=_fabrication_batch_response(sheet["batch"]),
            conditions=[
                _frozen_batch_condition_response(condition)
                for condition in sheet["conditions"]
            ],
            substrates=[
                _fabrication_substrate_response(substrate)
                for substrate in sheet["substrates"]
            ],
            devices=[
                _fabrication_device_response(device)
                for device in sheet["devices"]
            ],
            preparations=[
                RunSheetPreparationResponse(
                    preparation=_solution_preparation_response(preparation),
                    uses=[
                        SolutionPreparationUseResponse(**use)
                        for use in sheet["preparation_uses"][int(preparation.id)]
                    ],
                )
                for preparation in sheet["preparations"]
            ],
            executions=[
                RunSheetExecutionResponse(
                    execution=_process_execution_response(execution),
                    members=[
                        ProcessExecutionMemberResponse(**member)
                        for member in sheet["execution_members"][int(execution.id)]
                    ],
                )
                for execution in sheet["executions"]
            ],
            deviations=[
                _deviation_response(deviation)
                for deviation in sheet["deviations"]
            ],
            editor_config=EditorConfigResponse(
                vcd_valves=list(VCD_VALVES),
                max_solid_chemicals=MAX_SOLID_CHEMICALS,
                max_solvents=MAX_SOLVENTS,
            ),
        )
    @router.patch(
        "/api/fabrication-batches/{batch_id}/status",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def update_fabrication_batch_status(
        request: Request,
        batch_id: int,
        payload: FabricationBatchStatusUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> None:
        try:
            await update_batch_status(
                repository,
                batch_id=batch_id,
                status=BatchStatus(payload.status),
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
                actual_substrate_counts=(
                    {
                        int(key): int(value)
                        for key, value in payload.actual_substrate_counts.items()
                    }
                    if payload.actual_substrate_counts is not None
                    else None
                ),
                shortfall_deviations=(
                    [
                        (int(item.condition_id), str(item.description))
                        for item in payload.shortfall_deviations
                    ]
                    if payload.shortfall_deviations is not None
                    else None
                ),
                actor_role=auth_context.user.role,
            )
        except OperationError as error:
            raise _operation_error_to_http(error) from error
    @router.post(
        "/api/fabrication-batches/{batch_id}/record-as-planned",
        response_model=RecordAsPlannedResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def record_fabrication_batch_as_planned(
        request: Request,
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> RecordAsPlannedResponse:
        try:
            counts = await repository.record_batch_as_planned(
                batch_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return RecordAsPlannedResponse(**counts)
    @router.get(
        "/api/fabrication-batches/{batch_id}/conditions",
        response_model=list[FrozenBatchConditionResponse],
    )
    async def get_fabrication_batch_conditions(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[FrozenBatchConditionResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _frozen_batch_condition_response(c)
            for c in await repository.get_fabrication_batch_conditions(batch_id)
        ]
    @router.get(
        "/api/fabrication-batches/{batch_id}/substrates",
        response_model=list[FabricationSubstrateResponse],
    )
    async def get_fabrication_batch_substrates(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[FabricationSubstrateResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _fabrication_substrate_response(s)
            for s in await repository.get_fabrication_substrates_for_batch(batch_id)
        ]
    @router.get(
        "/api/fabrication-batches/{batch_id}/devices",
        response_model=list[FabricationDeviceResponse],
    )
    async def get_fabrication_batch_devices(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[FabricationDeviceResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _fabrication_device_response(d)
            for d in await repository.get_fabrication_devices_for_batch(batch_id)
        ]
    @router.get(
        "/api/fabrication-batches/{batch_id}/solution-preparations",
        response_model=list[SolutionPreparationResponse],
    )
    async def list_solution_preparations(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[SolutionPreparationResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _solution_preparation_response(p)
            for p in await repository.list_solution_preparations(batch_id)
        ]
    @router.post(
        "/api/fabrication-batches/{batch_id}/solution-preparations",
        response_model=SolutionPreparationResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_solution_preparation(
        request: Request,
        batch_id: int,
        payload: SolutionPreparationCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SolutionPreparationResponse:
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
        try:
            record = await repository.create_solution_preparation(
                fabrication_batch_id=batch_id,
                planned_solution_snapshot=payload.planned_solution_snapshot,
                notes=payload.notes,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _solution_preparation_response(record)
    @router.get(
        "/api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}/uses",
        response_model=list[SolutionPreparationUseResponse],
    )
    async def list_solution_preparation_uses(
        batch_id: int,
        preparation_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[dict[str, Any]]:
        batch = await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            preparation = await repository.get_solution_preparation(preparation_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if preparation.fabrication_batch_id != batch.id:
            raise HTTPException(status_code=404, detail="solution preparation not found")
        return await repository.list_solution_preparation_uses(preparation_id)
    @router.post(
        "/api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}/split",
        response_model=SolutionPreparationResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def split_solution_preparation(
        request: Request,
        batch_id: int,
        preparation_id: int,
        payload: MembershipSplitPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SolutionPreparationResponse:
        await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            source = await repository.get_solution_preparation(preparation_id)
            if source.fabrication_batch_id != batch_id:
                raise KeyError("solution preparation not found")
            record = await repository.split_solution_preparation(
                preparation_id,
                member_ids=payload.member_ids,
                notes=payload.notes,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _solution_preparation_response(record)
    @router.post(
        "/api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}/merge",
        response_model=SolutionPreparationResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def merge_solution_preparations(
        request: Request,
        batch_id: int,
        preparation_id: int,
        payload: MembershipMergePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SolutionPreparationResponse:
        await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            record = await repository.merge_solution_preparations(
                preparation_id,
                source_id=payload.source_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _solution_preparation_response(record)
    @router.patch(
        "/api/fabrication-batches/{batch_id}/solution-preparations/{preparation_id}",
        response_model=SolutionPreparationResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_solution_preparation(
        request: Request,
        batch_id: int,
        preparation_id: int,
        payload: SolutionPreparationUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> SolutionPreparationResponse:
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
        try:
            record = await repository.update_solution_preparation(
                preparation_id,
                status=PreparationStatus(payload.status) if payload.status else None,
                actual_solution_snapshot=payload.actual_solution_snapshot,
                actual_matches_planned=payload.actual_matches_planned,
                notes=payload.notes,
                fabrication_batch_id=batch_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _solution_preparation_response(record)
    @router.get(
        "/api/fabrication-batches/{batch_id}/process-executions",
        response_model=list[ProcessExecutionResponse],
    )
    async def list_process_executions(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[ProcessExecutionResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _process_execution_response(e)
            for e in await repository.list_process_executions(batch_id)
        ]
    @router.post(
        "/api/fabrication-batches/{batch_id}/process-executions",
        response_model=ProcessExecutionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_process_execution(
        request: Request,
        batch_id: int,
        payload: ProcessExecutionCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ProcessExecutionResponse:
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
        try:
            record = await repository.create_process_execution(
                fabrication_batch_id=batch_id,
                method=payload.method,
                layer_role=payload.layer_role,
                layer_type=payload.layer_type,
                layer_name=payload.layer_name,
                planned_process_snapshot=payload.planned_process_snapshot,
                is_shared=payload.is_shared,
                notes=payload.notes,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _process_execution_response(record)
    @router.get(
        "/api/fabrication-batches/{batch_id}/process-executions/{execution_id}/members",
        response_model=list[ProcessExecutionMemberResponse],
    )
    async def list_process_execution_members(
        batch_id: int,
        execution_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[dict[str, Any]]:
        batch = await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            execution = await repository.get_process_execution(execution_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if execution.fabrication_batch_id != batch.id:
            raise HTTPException(status_code=404, detail="process execution not found")
        return await repository.list_process_execution_members(execution_id)
    @router.post(
        "/api/fabrication-batches/{batch_id}/process-executions/{execution_id}/split",
        response_model=ProcessExecutionResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def split_process_execution(
        request: Request,
        batch_id: int,
        execution_id: int,
        payload: MembershipSplitPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ProcessExecutionResponse:
        await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            source = await repository.get_process_execution(execution_id)
            if source.fabrication_batch_id != batch_id:
                raise KeyError("process execution not found")
            record = await repository.split_process_execution(
                execution_id,
                member_ids=payload.member_ids,
                notes=payload.notes,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _process_execution_response(record)
    @router.post(
        "/api/fabrication-batches/{batch_id}/process-executions/{execution_id}/merge",
        response_model=ProcessExecutionResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def merge_process_executions(
        request: Request,
        batch_id: int,
        execution_id: int,
        payload: MembershipMergePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ProcessExecutionResponse:
        await _batch_for_actor_or_404(repository, batch_id, auth_context)
        try:
            record = await repository.merge_process_executions(
                execution_id,
                source_id=payload.source_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _process_execution_response(record)
    @router.patch(
        "/api/fabrication-batches/{batch_id}/process-executions/{execution_id}",
        response_model=ProcessExecutionResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_process_execution(
        request: Request,
        batch_id: int,
        execution_id: int,
        payload: ProcessExecutionUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ProcessExecutionResponse:
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
        try:
            record = await repository.update_process_execution(
                execution_id,
                status=ExecutionStatus(payload.status) if payload.status else None,
                actual_process_snapshot=payload.actual_process_snapshot,
                actual_matches_planned=payload.actual_matches_planned,
                equipment_identifier=payload.equipment_identifier,
                notes=payload.notes,
                fabrication_batch_id=batch_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _process_execution_response(record)
    @router.get(
        "/api/fabrication-batches/{batch_id}/deviations",
        response_model=list[DeviationResponse],
    )
    async def list_deviations(
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[DeviationResponse]:
        try:
            record = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, record.experiment_id, auth_context)
        return [
            _deviation_response(d)
            for d in await repository.list_deviations(batch_id)
        ]
    @router.post(
        "/api/fabrication-batches/{batch_id}/deviations",
        response_model=DeviationResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_deviation(
        request: Request,
        batch_id: int,
        payload: DeviationCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> DeviationResponse:
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        await _get_record_or_404(repository, batch.experiment_id, auth_context)
        try:
            record = await repository.create_deviation(
                fabrication_batch_id=batch_id,
                category=payload.category,
                severity=payload.severity,
                description=payload.description,
                planned_value=payload.planned_value,
                actual_value=payload.actual_value,
                supersedes_deviation_id=payload.supersedes_deviation_id,
                solution_preparation_id=payload.solution_preparation_id,
                process_execution_id=payload.process_execution_id,
                substrate_id=payload.substrate_id,
                device_id=payload.device_id,
                condition_id=payload.condition_id,
                deviation_type=payload.deviation_type,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except PermissionError as error:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return _deviation_response(record)
    @router.get(
        "/experiments/{experiment_id}/batches/{batch_id}/export.json",
    )
    async def export_fabrication_batch_json(
        request: Request,
        experiment_id: int,
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> Response:
        await _get_record_or_404(repository, experiment_id, auth_context)
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        if batch.experiment_id != experiment_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="batch not found",
            )
        payload = await _build_batch_export_payload(repository, batch)
        return Response(
            content=canonical_batch_json(payload),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="batch-{batch_id}-execution.json"'
                )
            },
        )
    @router.get(
        "/experiments/{experiment_id}/batches/{batch_id}/export.pdf",
    )
    async def export_fabrication_batch_pdf(
        experiment_id: int,
        batch_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> Response:
        await _get_record_or_404(repository, experiment_id, auth_context)
        try:
            batch = await repository.get_fabrication_batch(batch_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if batch.experiment_id != experiment_id:
            raise HTTPException(status_code=404, detail="batch not found")
        payload = await _build_batch_export_payload(repository, batch)
        return Response(
            content=await run_in_threadpool(render_batch_pdf, payload),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="batch-{batch_id}-traveler.pdf"'
                )
            },
        )
    return router
