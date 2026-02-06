"""事件接口。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from baize_core.api.models import EventBatchRequest, EventBatchResponse
from baize_core.api.utils import build_bbox
from baize_core.schemas.entity_event import Event, EventType


def get_router(orchestrator: Any) -> APIRouter:
    """事件相关路由。"""
    router = APIRouter()

    @router.post("/events", response_model=EventBatchResponse)
    async def create_events(payload: EventBatchRequest) -> EventBatchResponse:
        """批量写入事件。"""
        try:
            event_uids = await orchestrator.store_events(payload.events)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return EventBatchResponse(event_uids=event_uids)

    @router.get("/events", response_model=list[Event])
    async def list_events(
        event_types: Annotated[list[EventType] | None, Query()] = None,
        time_start: Annotated[datetime | None, Query()] = None,
        time_end: Annotated[datetime | None, Query()] = None,
        min_lon: Annotated[float | None, Query()] = None,
        min_lat: Annotated[float | None, Query()] = None,
        max_lon: Annotated[float | None, Query()] = None,
        max_lat: Annotated[float | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[Event]:
        """查询事件列表。"""
        bbox = build_bbox(min_lon, min_lat, max_lon, max_lat)
        try:
            return await orchestrator.list_events(
                event_types=event_types,
                time_start=time_start,
                time_end=time_end,
                bbox=bbox,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/events/{event_uid}", response_model=Event)
    async def get_event(event_uid: str) -> Event:
        """获取事件。"""
        event = await orchestrator.get_event(event_uid)
        if event is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return event

    return router
