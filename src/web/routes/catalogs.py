"""Input-time catalog data: baselines, layer presets, materials, device layouts, and editor configuration."""

from .common import *  # noqa: F401,F403


def create_catalogs_router(
    repository: WebRepository,
    *,
    default_campaign_id: str | None,
) -> APIRouter:
    """Register the catalogs endpoints on a fresh router."""

    router = APIRouter(dependencies=[Depends(require_user)])

    @router.post(
        "/api/baselines",
        response_model=BaselineResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def save_baseline(
        request: Request,
        payload: BaselinePayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_user),
        ],
    ) -> BaselineResponse:
        """Create a baseline owned by the actor.

        The server derives the scope from the role: a student-created
        baseline is always Personal (no student-supplied scope is accepted
        by the request contract); instructor and administrator direct
        creation is Shared.
        """
        try:
            name, normalized, deposition_process = _baseline_values(payload)
            record = await repository.save_baseline(
                name,
                normalized,
                deposition_process=deposition_process,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a baseline named {payload.name.strip()!r} already exists",
            ) from error
        return BaselineResponse(**record)
    @router.put(
        "/api/baselines/{baseline_id}",
        response_model=BaselineResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_baseline(
        request: Request,
        baseline_id: int,
        payload: BaselinePayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_user),
        ],
    ) -> BaselineResponse:
        """Append an immutable revision to an editable baseline.

        Only the owner may revise a Personal baseline; Shared baselines keep
        the administrator-only revision policy. Any other actor receives the
        uniform 404 resource boundary.
        """

        try:
            name, normalized, deposition_process = _baseline_values(payload)
            record = await repository.update_baseline(
                baseline_id,
                name,
                normalized,
                deposition_process=deposition_process,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"a baseline named {payload.name.strip()!r} already exists",
            ) from error
        return BaselineResponse(**record)
    @router.post(
        "/api/baselines/{baseline_id}/promote",
        response_model=BaselineResponse,
        dependencies=[Depends(require_csrf), Depends(require_role(UserRole.INSTRUCTOR))],
    )
    async def promote_baseline(
        request: Request,
        baseline_id: int,
        payload: BaselinePromotePayload,
        auth_context: Annotated[
            AuthContext,
            Depends(require_user),
        ],
    ) -> BaselineResponse:
        """Promote an active Personal baseline to Shared.

        Promotion is explicit and immediate: it records the exact current
        baseline version, the promoter, the timestamp, and the optional note
        in the audit trail, then the baseline becomes lab-wide visible and
        usable as an experiment starting point.
        """
        try:
            record = await repository.promote_baseline(
                baseline_id,
                promoted_by_user_id=auth_context.user.id,
                note=payload.note,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a shared baseline with this name already exists",
            ) from error
        return BaselineResponse(**record)
    @router.get(
        "/api/baselines",
        response_model=list[BaselineResponse],
    )
    async def list_baselines(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[BaselineResponse]:
        """List baselines visible to the actor under the visibility matrix."""
        return [
            BaselineResponse(**record)
            for record in await repository.list_baselines(
                actor_user_id=auth_context.user.id,
                include_archived=(
                    auth_context.user.role != UserRole.STUDENT
                ),
            )
        ]
    @router.get(
        "/api/baselines/{baseline_id}",
        response_model=BaselineResponse,
    )
    async def get_baseline(
        baseline_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> BaselineResponse:
        try:
            record = await repository.get_baseline(
                baseline_id,
                actor_user_id=auth_context.user.id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return BaselineResponse(**record)
    @router.delete(
        "/api/baselines/{baseline_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf), Depends(require_role(UserRole.ADMINISTRATOR))],
    )
    async def delete_baseline(
        request: Request,
        baseline_id: int,
        auth_context: Annotated[
            AuthContext,
            Depends(require_role(UserRole.ADMINISTRATOR)),
        ],
    ) -> None:
        try:
            await repository.delete_baseline(
                baseline_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
    @router.get(
        "/api/baselines/{baseline_id}/versions",
        response_model=list[BaselineVersionResponse],
    )
    async def list_baseline_versions(
        baseline_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[BaselineVersionResponse]:
        try:
            versions = await repository.list_baseline_versions(
                baseline_id,
                actor_user_id=auth_context.user.id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return [BaselineVersionResponse(**version) for version in versions]
    @router.get(
        "/api/layer-presets",
        response_model=list[LayerPresetResponse],
    )
    async def list_layer_presets(
        auth_context: Annotated[AuthContext, Depends(require_user)],
        include_inactive: bool = False,
        promotable: bool = False,
    ) -> list[LayerPresetResponse]:
        if promotable:
            # Instructor review list: other users' active personal presets
            # that may be promoted to shared.
            if auth_context.user.role not in (UserRole.INSTRUCTOR, UserRole.ADMINISTRATOR):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="only instructors may list promotable layer presets",
                )
            records = await repository.list_promotable_layer_presets(
                actor_user_id=auth_context.user.id,
            )
            return [LayerPresetResponse(**record) for record in records]
        records = await repository.list_layer_presets(
            actor_user_id=auth_context.user.id,
            include_inactive=include_inactive,
        )
        return [LayerPresetResponse(**record) for record in records]
    @router.get(
        "/api/layer-presets/{preset_id}/versions",
        response_model=list[LayerPresetVersionResponse],
    )
    async def list_layer_preset_versions(
        preset_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[LayerPresetVersionResponse]:
        try:
            records = await repository.list_layer_preset_versions(
                preset_id,
                actor_user_id=auth_context.user.id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        return [LayerPresetVersionResponse(**record) for record in records]
    @router.post(
        "/api/layer-presets",
        response_model=LayerPresetResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_layer_preset(
        request: Request,
        payload: LayerPresetPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> LayerPresetResponse:
        try:
            record = await repository.create_layer_preset(
                name=payload.name,
                layer=payload.layer.model_dump(mode="python"),
                deposition_process=(
                    payload.deposition_process.model_dump(mode="python")
                    if payload.deposition_process is not None
                    else None
                ),
                scope=payload.scope,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="you already have a layer preset with this name",
            ) from error
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return LayerPresetResponse(**record)
    @router.put(
        "/api/layer-presets/{preset_id}",
        response_model=LayerPresetResponse,
        dependencies=[Depends(require_csrf)],
    )
    async def update_layer_preset(
        request: Request,
        preset_id: int,
        payload: LayerPresetPayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> LayerPresetResponse:
        try:
            record = await repository.update_layer_preset(
                preset_id,
                name=payload.name,
                layer=payload.layer.model_dump(mode="python"),
                deposition_process=(
                    payload.deposition_process.model_dump(mode="python")
                    if payload.deposition_process is not None
                    else None
                ),
                scope=payload.scope,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="you already have a layer preset with this name",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return LayerPresetResponse(**record)
    @router.post(
        "/api/layer-presets/{preset_id}/promote",
        response_model=LayerPresetResponse,
        dependencies=[Depends(require_csrf), Depends(require_role(UserRole.INSTRUCTOR))],
    )
    async def promote_layer_preset(
        request: Request,
        preset_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> LayerPresetResponse:
        """Promote an active Personal layer preset to Shared.

        One-way, instructor-gated: the preset becomes lab-wide selectable and
        the promotion (who, when, from where) lands in the audit trail.
        """
        try:
            record = await repository.promote_layer_preset(
                preset_id,
                promoted_by_user_id=auth_context.user.id,
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
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a shared layer preset with this name already exists",
            ) from error
        return LayerPresetResponse(**record)
    @router.delete(
        "/api/layer-presets/{preset_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_csrf)],
    )
    async def deactivate_layer_preset(
        request: Request,
        preset_id: int,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> None:
        try:
            await repository.deactivate_layer_preset(
                preset_id,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
    @router.get("/api/materials", response_model=list[MaterialResponse])
    async def list_materials(
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[MaterialResponse]:
        records = await repository.list_materials(actor_user_id=auth_context.user.id)
        return [MaterialResponse(**record) for record in records]
    @router.post(
        "/api/materials",
        response_model=MaterialResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_material(
        request: Request,
        payload: MaterialCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> MaterialResponse:
        try:
            record = await repository.create_material(
                category=payload.category,
                name=payload.name,
                formula=payload.formula,
                cas_number=payload.cas_number,
                specification=payload.specification,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a material with this category and name already exists",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        return MaterialResponse(**record)
    @router.patch(
        "/api/materials/{material_id}",
        response_model=MaterialResponse,
        dependencies=[
            Depends(require_csrf),
            Depends(require_role(UserRole.INSTRUCTOR)),
        ],
    )
    async def update_material(
        request: Request,
        material_id: int,
        payload: MaterialUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> MaterialResponse:
        try:
            record = await repository.update_material(
                material_id,
                name=payload.name,
                formula=payload.formula,
                cas_number=payload.cas_number,
                specification=payload.specification,
                status=payload.status,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="a material with this category and name already exists",
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        return MaterialResponse(**record)
    @router.post(
        "/api/materials/{material_id}/products",
        response_model=MaterialResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf)],
    )
    async def create_material_product(
        request: Request,
        material_id: int,
        payload: MaterialProductCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> MaterialResponse:
        try:
            record = await repository.create_material_product(
                material_id,
                vendor=payload.vendor,
                catalog_number=payload.catalog_number,
                specification=payload.specification,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="this supplier product already exists for the material",
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        return MaterialResponse(**record)
    @router.patch(
        "/api/material-products/{product_id}",
        response_model=MaterialResponse,
        dependencies=[
            Depends(require_csrf),
            Depends(require_role(UserRole.INSTRUCTOR)),
        ],
    )
    async def update_material_product(
        request: Request,
        product_id: int,
        payload: MaterialProductUpdatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> MaterialResponse:
        try:
            record = await repository.update_material_product(
                product_id,
                vendor=payload.vendor,
                catalog_number=payload.catalog_number,
                specification=payload.specification,
                status=payload.status,
                actor_user_id=auth_context.user.id,
                client_ip=_client_ip(request),
            )
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="this supplier product already exists for the material",
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
        except (PermissionError, ValueError) as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        return MaterialResponse(**record)
    @router.get("/api/device-layouts")
    async def list_device_layouts_endpoint(
        _auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> list[dict[str, Any]]:
        async with repository.database.engine.connect() as connection:
            layouts = await list_device_layouts(connection)
        return [
            {
                "code": layout.code,
                "version": layout.version,
                "substrate_width_mm": str(layout.substrate_width_mm),
                "substrate_length_mm": str(layout.substrate_length_mm),
                "devices_per_substrate": layout.devices_per_substrate,
                "device_active_area_cm2": str(layout.device_active_area_cm2),
                "total_active_area_cm2": str(layout.total_active_area_cm2),
                "description": layout.description,
            }
            for layout in layouts
        ]
    @router.post(
        "/api/device-layouts",
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(require_csrf), Depends(require_role(UserRole.ADMINISTRATOR))],
    )
    async def create_device_layout_endpoint(
        request: Request,
        payload: DeviceLayoutCreatePayload,
        auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> dict[str, Any]:
        """Create one immutable device-layout version (administrator only).

        Layouts are the only catalog students cannot build themselves: every
        condition needs one, so a fresh deployment is unusable until the
        administrator creates the first layout here.
        """
        async with repository.database.engine.begin() as connection:
            try:
                layout = await create_device_layout(
                    connection,
                    code=payload.code,
                    version=payload.version,
                    substrate_width_mm=payload.substrate_width_mm,
                    substrate_length_mm=payload.substrate_length_mm,
                    devices_per_substrate=payload.devices_per_substrate,
                    device_active_area_cm2=payload.device_active_area_cm2,
                    total_active_area_cm2=payload.total_active_area_cm2,
                    description=payload.description,
                    actor_user_id=auth_context.user.id,
                    client_ip=_client_ip(request),
                )
            except ValueError as error:
                # Duplicate (code, version) conflicts are 409; validation
                # problems (precision, range, format) are 400.
                conflict = "already exists" in str(error)
                raise HTTPException(
                    status_code=(
                        status.HTTP_409_CONFLICT
                        if conflict
                        else status.HTTP_400_BAD_REQUEST
                    ),
                    detail=str(error),
                ) from error
        return {
            "code": layout.code,
            "version": layout.version,
            "substrate_width_mm": str(layout.substrate_width_mm),
            "substrate_length_mm": str(layout.substrate_length_mm),
            "devices_per_substrate": layout.devices_per_substrate,
            "device_active_area_cm2": str(layout.device_active_area_cm2),
            "total_active_area_cm2": str(layout.total_active_area_cm2),
            "description": layout.description,
        }
    @router.get("/api/editor-config", response_model=EditorConfigResponse)
    async def get_editor_config_endpoint(
        _auth_context: Annotated[AuthContext, Depends(require_user)],
    ) -> EditorConfigResponse:
        """Server-authoritative editor bounds: valve choices and list caps."""

        return EditorConfigResponse(
            vcd_valves=list(VCD_VALVES),
            max_solid_chemicals=MAX_SOLID_CHEMICALS,
            max_solvents=MAX_SOLVENTS,
        )
    return router
