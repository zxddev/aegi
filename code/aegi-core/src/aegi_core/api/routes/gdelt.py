# Author: msq
"""GDELT DOC API 路由。"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_gdelt_client
from aegi_core.api.errors import AegiHTTPError
from aegi_core.db.models.gdelt_event import GdeltEvent
from aegi_core.infra.cameo import CAMEO_CATEGORY, cameo_category, cameo_root_label
from aegi_core.services.gdelt_scheduler import GDELTScheduler

router = APIRouter(prefix="/gdelt", tags=["gdelt"])


# ── Schemas ──────────────────────────────────────────────────


class GdeltEventResponse(BaseModel):
    uid: str
    gdelt_id: str
    case_uid: str | None = None
    title: str
    url: str
    source_domain: str = ""
    language: str = ""
    published_at: str | None = None
    cameo_code: str | None = None
    cameo_root: str | None = None
    cameo_label: str = ""
    cameo_category: str = "unknown"
    goldstein_scale: float | None = None
    actor1: str | None = None
    actor2: str | None = None
    actor1_country: str | None = None
    actor2_country: str | None = None
    geo_country: str | None = None
    geo_name: str | None = None
    tone: float | None = None
    status: str = "new"
    matched_subscription_uids: list[str] = Field(default_factory=list)
    created_at: str | None = None


class PaginatedGdeltEvents(BaseModel):
    items: list[GdeltEventResponse]
    total: int


class PollResponse(BaseModel):
    new_events: int
    events: list[GdeltEventResponse]


class SchedulerStatusResponse(BaseModel):
    state: str
    running: bool
    enabled: bool
    interval_minutes: float
    last_poll_time: str | None = None
    last_successful_poll_time: str | None = None
    next_poll_time: str | None = None


class IngestRequest(BaseModel):
    case_uid: str


class GdeltStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int] = Field(default_factory=dict)
    top_countries: list[dict] = Field(default_factory=list)
    by_day: list[dict] = Field(default_factory=list)
    cameo_distribution: dict[str, int] = Field(default_factory=dict)
    conflict_cooperation_ratio: float = 0.0
    anomaly_count: int = 0


# ── 辅助 ──────────────────────────────────────────────────────


def _event_to_response(ev: GdeltEvent) -> GdeltEventResponse:
    root = ev.cameo_root or ""
    return GdeltEventResponse(
        uid=ev.uid,
        gdelt_id=ev.gdelt_id,
        case_uid=ev.case_uid,
        title=ev.title,
        url=ev.url,
        source_domain=ev.source_domain,
        language=ev.language,
        published_at=ev.published_at.isoformat() if ev.published_at else None,
        cameo_code=ev.cameo_code,
        cameo_root=ev.cameo_root,
        cameo_label=cameo_root_label(root) if root else "",
        cameo_category=cameo_category(root) if root else "unknown",
        goldstein_scale=ev.goldstein_scale,
        actor1=ev.actor1,
        actor2=ev.actor2,
        actor1_country=ev.actor1_country,
        actor2_country=ev.actor2_country,
        geo_country=ev.geo_country,
        geo_name=ev.geo_name,
        tone=ev.tone,
        status=ev.status,
        matched_subscription_uids=ev.matched_subscription_uids or [],
        created_at=ev.created_at.isoformat() if ev.created_at else None,
    )


def _get_scheduler(request: Request) -> GDELTScheduler:
    scheduler = getattr(request.app.state, "gdelt_scheduler", None)
    if scheduler is None:
        raise AegiHTTPError(
            503,
            "service_unavailable",
            "GDELT scheduler not initialized",
            {},
        )
    return scheduler


def _scheduler_to_response(scheduler: GDELTScheduler) -> SchedulerStatusResponse:
    return SchedulerStatusResponse(
        state="running" if scheduler.is_running else "stopped",
        running=scheduler.is_running,
        enabled=scheduler.enabled,
        interval_minutes=scheduler.interval_minutes,
        last_poll_time=scheduler.last_poll_time.isoformat()
        if scheduler.last_poll_time
        else None,
        last_successful_poll_time=scheduler.last_successful_poll_time.isoformat()
        if scheduler.last_successful_poll_time
        else None,
        next_poll_time=scheduler.next_poll_time.isoformat()
        if scheduler.next_poll_time
        else None,
    )


# ── 端点 ──────────────────────────────────────────────────────


@router.post("/monitor/poll", response_model=PollResponse)
async def manual_poll(
    session: AsyncSession = Depends(get_db_session),
) -> PollResponse:
    """手动触发一次 GDELT 轮询。"""
    from aegi_core.services.gdelt_monitor import GDELTMonitor

    gdelt = get_gdelt_client()
    monitor = GDELTMonitor(gdelt=gdelt, db_session=session)
    doc_events = await monitor.poll()
    csv_events = await monitor.poll_events()
    new_events = [*doc_events, *csv_events]
    return PollResponse(
        new_events=len(new_events),
        events=[_event_to_response(ev) for ev in new_events],
    )


@router.post("/monitor/start", response_model=SchedulerStatusResponse)
async def start_scheduler(request: Request) -> SchedulerStatusResponse:
    """运行时启动 GDELT 调度器。"""
    scheduler = _get_scheduler(request)
    await scheduler.start()
    return _scheduler_to_response(scheduler)


@router.post("/monitor/stop", response_model=SchedulerStatusResponse)
async def stop_scheduler(request: Request) -> SchedulerStatusResponse:
    """运行时停止 GDELT 调度器。"""
    scheduler = _get_scheduler(request)
    await scheduler.stop()
    return _scheduler_to_response(scheduler)


@router.get("/monitor/status", response_model=SchedulerStatusResponse)
async def scheduler_status(request: Request) -> SchedulerStatusResponse:
    """查询 GDELT 调度器状态。"""
    scheduler = _get_scheduler(request)
    return _scheduler_to_response(scheduler)


@router.get("/events", response_model=PaginatedGdeltEvents)
async def list_events(
    skip: int = 0,
    offset: int | None = None,
    limit: int = 20,
    status: str | None = None,
    geo_country: str | None = None,
    cameo_root: str | None = None,
    min_goldstein: float | None = None,
    max_goldstein: float | None = None,
    actor_country: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedGdeltEvents:
    """分页查询 GDELT 事件。"""
    query_offset = skip if offset is None else offset
    filters = []
    if status:
        filters.append(GdeltEvent.status == status)
    if geo_country:
        filters.append(GdeltEvent.geo_country == geo_country)
    if cameo_root:
        filters.append(GdeltEvent.cameo_root == cameo_root)
    if min_goldstein is not None:
        filters.append(GdeltEvent.goldstein_scale >= min_goldstein)
    if max_goldstein is not None:
        filters.append(GdeltEvent.goldstein_scale <= max_goldstein)
    if actor_country:
        country = actor_country.upper()
        filters.append(
            sa.or_(
                GdeltEvent.actor1_country == country,
                GdeltEvent.actor2_country == country,
            )
        )

    total_q = sa.select(sa.func.count()).select_from(GdeltEvent)
    if filters:
        total_q = total_q.where(*filters)
    total = (await session.execute(total_q)).scalar() or 0

    rows_q = (
        sa.select(GdeltEvent)
        .order_by(GdeltEvent.created_at.desc())
        .offset(query_offset)
        .limit(limit)
    )
    if filters:
        rows_q = rows_q.where(*filters)
    rows = (await session.execute(rows_q)).scalars().all()

    return PaginatedGdeltEvents(
        items=[_event_to_response(r) for r in rows],
        total=total,
    )


@router.get("/events/{uid}", response_model=GdeltEventResponse)
async def get_event_detail(
    uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> GdeltEventResponse:
    """获取单个 GDELT 事件详情。"""
    ev = (
        await session.execute(sa.select(GdeltEvent).where(GdeltEvent.uid == uid))
    ).scalar_one_or_none()
    if not ev:
        raise AegiHTTPError(404, "not_found", f"GDELT event {uid} not found", {})
    return _event_to_response(ev)


@router.get("/anomalies", response_model=PaginatedGdeltEvents)
async def list_anomalies(
    skip: int = 0,
    offset: int | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedGdeltEvents:
    """分页查询异常事件（status=anomaly）。"""
    query_offset = skip if offset is None else offset
    filters = [GdeltEvent.status == "anomaly"]

    total = (
        await session.execute(
            sa.select(sa.func.count()).select_from(GdeltEvent).where(*filters)
        )
    ).scalar() or 0

    rows = (
        (
            await session.execute(
                sa.select(GdeltEvent)
                .where(*filters)
                .order_by(GdeltEvent.created_at.desc())
                .offset(query_offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return PaginatedGdeltEvents(
        items=[_event_to_response(r) for r in rows],
        total=total,
    )


@router.post("/events/{uid}/ingest")
async def ingest_event(
    uid: str,
    body: IngestRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """手动将 GDELT 事件 ingest 到指定 case。"""
    from aegi_core.services.gdelt_monitor import GDELTMonitor

    ev = (
        await session.execute(sa.select(GdeltEvent).where(GdeltEvent.uid == uid))
    ).scalar_one_or_none()
    if not ev:
        raise AegiHTTPError(404, "not_found", f"GDELT event {uid} not found", {})
    if ev.status == "ingested":
        raise AegiHTTPError(409, "conflict", "Event already ingested", {})

    gdelt = get_gdelt_client()
    monitor = GDELTMonitor(gdelt=gdelt, db_session=session)
    await monitor.ingest_event(ev, body.case_uid)
    return {"status": "ingested", "case_uid": body.case_uid}


@router.get("/stats", response_model=GdeltStatsResponse)
async def stats(
    session: AsyncSession = Depends(get_db_session),
) -> GdeltStatsResponse:
    """GDELT 事件统计。"""
    total = (
        await session.execute(sa.select(sa.func.count()).select_from(GdeltEvent))
    ).scalar() or 0

    # 按 status 分组
    status_rows = (
        await session.execute(
            sa.select(GdeltEvent.status, sa.func.count()).group_by(GdeltEvent.status)
        )
    ).all()
    by_status = {row[0]: row[1] for row in status_rows}

    # 按 country top 20
    country_rows = (
        await session.execute(
            sa.select(GdeltEvent.geo_country, sa.func.count().label("cnt"))
            .where(GdeltEvent.geo_country.isnot(None))
            .group_by(GdeltEvent.geo_country)
            .order_by(sa.desc("cnt"))
            .limit(20)
        )
    ).all()
    top_countries = [{"country": r[0], "count": r[1]} for r in country_rows]

    day_rows = (
        await session.execute(
            sa.select(
                sa.func.date_trunc("day", GdeltEvent.created_at).label("day"),
                sa.func.count().label("cnt"),
            )
            .group_by("day")
            .order_by(sa.desc("day"))
            .limit(30)
        )
    ).all()
    by_day = [
        {
            "day": r[0].date().isoformat() if r[0] else "",
            "count": r[1],
        }
        for r in day_rows
    ]

    cameo_rows = (
        await session.execute(
            sa.select(GdeltEvent.cameo_root, sa.func.count())
            .where(GdeltEvent.cameo_root.isnot(None))
            .group_by(GdeltEvent.cameo_root)
        )
    ).all()
    cameo_distribution = {str(row[0]): row[1] for row in cameo_rows if row[0]}

    conflict_roots = [code for code, cat in CAMEO_CATEGORY.items() if cat == "conflict"]
    cooperation_roots = [
        code for code, cat in CAMEO_CATEGORY.items() if cat == "cooperation"
    ]

    conflict_count = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(GdeltEvent)
            .where(GdeltEvent.cameo_root.in_(conflict_roots))
        )
    ).scalar() or 0
    cooperation_count = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(GdeltEvent)
            .where(GdeltEvent.cameo_root.in_(cooperation_roots))
        )
    ).scalar() or 0

    conflict_cooperation_ratio = (
        conflict_count / cooperation_count if cooperation_count > 0 else 0.0
    )
    anomaly_count = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(GdeltEvent)
            .where(GdeltEvent.status == "anomaly")
        )
    ).scalar() or 0

    return GdeltStatsResponse(
        total=total,
        by_status=by_status,
        top_countries=top_countries,
        by_day=by_day,
        cameo_distribution=cameo_distribution,
        conflict_cooperation_ratio=conflict_cooperation_ratio,
        anomaly_count=anomaly_count,
    )
