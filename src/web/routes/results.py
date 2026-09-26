"""Characterization results: upload, listing, detail, and assignment saving."""

import gzip

from .common import *  # noqa: F401,F403
from .common import _flat_metrics_from_analysis  # underscore name: not re-exported by *
from fastapi import Query

from ..publication_plots import (
    MEDIA_TYPES,
    PlotInputError,
    PlotUnavailableError,
    figure_filename,
    render_publication_figure,
)


def create_results_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register the results endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    @router.post(
        "/api/experiments/{experiment_id}/results",
        response_model=UploadedResultResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def upload_result_api(
        request: Request,
        experiment_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
        result_file: Annotated[
            UploadFile,
            File(description="Characterization result file"),
        ],
        fabrication_batch_id: Annotated[int, Form()],
    ) -> UploadedResultResponse:
        await _get_record_or_404(repository, experiment_id, auth_context)
        # Authorization and ownership before any payload work: the batch must
        # exist, be accessible to this actor, and belong to this experiment —
        # otherwise a uniform 404 (never revealing whether the batch exists)
        # — and only then is the file read, the device area resolved, and the
        # CSV parsed.
        batch = await _batch_for_actor_or_404(
            repository, fabrication_batch_id, auth_context
        )
        if batch.experiment_id != experiment_id:
            # Same fixed body as the not-found/no-access paths so clients
            # cannot distinguish "exists elsewhere" from "does not exist".
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="fabrication batch not found",
            )
        try:
            content = await _read_result_file(result_file)
            filename, content_type = validate_result_upload_metadata(result_file, content)
            # Total-current columns are converted with J = I / A using the
            # batch's device layout; None leaves such columns unsupported.
            device_active_area_cm2 = await repository.get_batch_device_active_area(
                fabrication_batch_id
            )
            analysis = await run_in_threadpool(
                parse_jv_analysis,
                content,
                source_filename=filename,
                device_active_area_cm2=device_active_area_cm2,
            )
            # The metrics column is a write-time cache pooled from the
            # per-trace instrument-reported values (v7 stores no aggregate
            # summaries in the analysis JSON); the analysis keeps every scan
            # as an individual trace.
            metrics = _flat_metrics_from_analysis(analysis)
            uploaded = await repository.add_result(
                experiment_id=experiment_id,
                fabrication_batch_id=fabrication_batch_id,
                filename=filename,
                content_type=content_type,
                content=content,
                metrics=metrics,
                analysis=analysis,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
                complete_experiment=False,
            )
        except (
            TypeError,
            ValueError,
            csv.Error,
            KeyError,
            IndexError,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return UploadedResultResponse(
            **{
                field_name: uploaded[field_name]
                for field_name in UploadedResultResponse.model_fields
            }
        )
    @router.get(
        "/api/results",
        response_model=list[ResultListItemResponse],
    )
    async def list_results_api(
        auth_context: Annotated[AuthContext, Depends(require_user)],
        experiment_id: int | None = None,
        fabrication_batch_id: int | None = None,
    ) -> list[ResultListItemResponse]:
        if experiment_id is not None:
            await _get_record_or_404(repository, experiment_id, auth_context)
        if fabrication_batch_id is not None:
            await _batch_for_actor_or_404(repository, fabrication_batch_id, auth_context)
        return [
            _result_list_item_response(item)
            for item in await repository.list_results_for_actor(
                _student_owner_id(auth_context),
                experiment_id=experiment_id,
                fabrication_batch_id=fabrication_batch_id,
            )
        ]
    @router.get(
        "/api/results/{file_id}",
        response_model=ResultDetailResponse,
    )
    async def get_result_detail_api(
        file_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ResultDetailResponse:
        result = await _result_for_actor_or_404(repository, file_id, auth_context)
        return await _result_detail_response(repository, result)

    @router.get("/api/results/{file_id}/figures/{figure_kind}")
    async def get_result_figure_api(
        request: Request,
        file_id: int,
        figure_kind: str,
        auth_context: Annotated[AuthContext, Depends(require_user)],
        format: str = Query(default="svg", pattern="^(svg|pdf|tiff)$"),
        metric: str | None = Query(default=None, pattern="^(voc|jsc|ff|pce)$"),
        direction: str = Query(default="forward", pattern="^(forward|reverse)$"),
        palette: str | None = Query(default=None),
        scale_min: float | None = Query(default=None),
        scale_max: float | None = Query(default=None),
        threshold: float | None = Query(default=None),
        device_id: list[str] = Query(default=[]),
        preview_exclusions: bool = False,
        excluded_device_id: list[str] = Query(default=[]),
        flagged_device_id: list[str] = Query(default=[]),
        download: bool = False,
    ) -> Response:
        result = await _result_for_actor_or_404(repository, file_id, auth_context)
        if figure_kind not in {"jv", "boxplot", "uniformity"}:
            raise HTTPException(status_code=404, detail="unknown figure type")
        detail = await _result_detail_response(repository, result)
        try:
            content = await run_in_threadpool(
                render_publication_figure,
                detail.analysis,
                [group.model_dump() for group in detail.groups],
                kind=figure_kind,
                figure_format=format,
                metric=metric,
                direction=direction,
                palette=palette,
                scale_min=scale_min,
                scale_max=scale_max,
                threshold=threshold,
                device_ids=device_id,
                excluded_device_ids=excluded_device_id if preview_exclusions else None,
                flagged_device_ids=flagged_device_id,
            )
        except PlotInputError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except PlotUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        filename = figure_filename(figure_kind, metric, format)
        disposition = "attachment" if download else "inline"
        headers = {
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            # The same URL can represent different saved assignments.
            # Matplotlib's content-keyed SVG cache avoids repeat rendering;
            # the browser must revalidate the current analysis every time.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Vary": "Accept-Encoding",
        }
        if format == "svg" and "gzip" in request.headers.get("accept-encoding", "").lower():
            content = gzip.compress(content, compresslevel=6, mtime=0)
            headers["Content-Encoding"] = "gzip"
        return Response(
            content=content,
            media_type=MEDIA_TYPES[format],
            headers=headers,
        )

    @router.get(
        "/api/results/{file_id}/assignments",
        response_model=list[ResultAssignmentRowResponse],
    )
    async def get_result_assignments_api(
        file_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[ResultAssignmentRowResponse]:
        await _result_for_actor_or_404(repository, file_id, auth_context)
        return [
            _result_assignment_row_response(row)
            for row in await repository.list_result_device_assignments(file_id)
        ]
    @router.post(
        "/api/results/{file_id}/assignments",
        response_model=ResultDetailResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def save_result_assignments_api(
        request: Request,
        file_id: int,
        payload: ResultAssignmentsPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> ResultDetailResponse:
        try:
            saved = await save_result_analysis(
                repository,
                file_id=file_id,
                assignments=[
                    ResultAssignmentInput(
                        analysis_substrate_id=item.analysis_substrate_id,
                        batch_condition_id=item.batch_condition_id,
                    )
                    for item in payload.assignments
                ],
                exclusions=[
                    ResultExclusionInput(
                        analysis_device_id=item.analysis_device_id,
                        reason=item.reason,
                    )
                    for item in payload.exclusions
                ],
                group_assignment=None,
                correction_reason=payload.correction_reason,
                actor_user_id=auth_context.user.id,
                actor_role=auth_context.user.role,
                client_ip=_client_ip(request),
            )
        except OperationError as error:
            raise _operation_error_to_http(error) from error
        return await _result_detail_response(repository, saved)
    return router
