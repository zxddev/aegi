"""实体接口。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from baize_core.api.models import EntityBatchRequest, EntityBatchResponse
from baize_core.api.utils import build_bbox
from baize_core.schemas.entity_event import Entity, EntityType


def get_router(orchestrator: Any) -> APIRouter:
    """实体相关路由。"""
    router = APIRouter()

    @router.post("/entities", response_model=EntityBatchResponse)
    async def create_entities(payload: EntityBatchRequest) -> EntityBatchResponse:
        """批量写入实体。"""
        try:
            entity_uids = await orchestrator.store_entities(payload.entities)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return EntityBatchResponse(entity_uids=entity_uids)

    @router.get("/entities", response_model=list[Entity])
    async def list_entities(
        entity_types: Annotated[list[EntityType] | None, Query()] = None,
        min_lon: Annotated[float | None, Query()] = None,
        min_lat: Annotated[float | None, Query()] = None,
        max_lon: Annotated[float | None, Query()] = None,
        max_lat: Annotated[float | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Entity]:
        """查询实体列表。"""
        bbox = build_bbox(min_lon, min_lat, max_lon, max_lat)
        try:
            return await orchestrator.list_entities(
                entity_types=entity_types,
                bbox=bbox,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/entities/{entity_uid}", response_model=Entity)
    async def get_entity(entity_uid: str) -> Entity:
        """获取实体。"""
        entity = await orchestrator.get_entity(entity_uid)
        if entity is None:
            raise HTTPException(status_code=404, detail="实体不存在")
        return entity

    return router
