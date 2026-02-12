"""OSINT 采集 API 路由。"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import (
    get_db_session,
    get_llm_client,
    get_qdrant_store,
    get_searxng_client,
)
from aegi_core.api.errors import AegiHTTPError
from aegi_core.db.models.collection_job import CollectionJob

router = APIRouter(
    prefix="/cases/{case_uid}/collection",
    tags=["collection"],
)


# ── 请求 / 响应 schema ────────────────────────────────────


class CreateJobRequest(BaseModel):
    query: str
    categories: str = "general"
    language: str = "zh-CN"
    max_results: int = Field(default=10, ge=1, le=100)
    extract_claims: bool = True
    cron_expression: str | None = None


class CollectionJobResponse(BaseModel):
    uid: str
    case_uid: str
    query: str
    categories: str
    language: str
    max_results: int
    status: str
    error: str | None = None
    urls_found: int = 0
    urls_ingested: int = 0
    urls_deduped: int = 0
    claims_extracted: int = 0
    result_meta: dict = Field(default_factory=dict)
    cron_expression: str | None = None
    created_at: str | None = None


class CollectionJobSummary(BaseModel):
    uid: str
    query: str
    status: str
    urls_found: int = 0
    urls_ingested: int = 0
    claims_extracted: int = 0
    created_at: str | None = None


class PaginatedJobs(BaseModel):
    items: list[CollectionJobSummary]
    total: int


class SearchPreviewRequest(BaseModel):
    query: str
    categories: str = "general"
    language: str = "zh-CN"
    limit: int = Field(default=5, ge=1, le=20)


class SearchPreviewItem(BaseModel):
    title: str
    url: str
    snippet: str
    engine: str = ""
    credibility: dict = Field(default_factory=dict)


def _job_to_response(job: CollectionJob) -> CollectionJobResponse:
    return CollectionJobResponse(
        uid=job.uid,
        case_uid=job.case_uid,
        query=job.query,
        categories=job.categories,
        language=job.language,
        max_results=job.max_results,
        status=job.status,
        error=job.error,
        urls_found=job.urls_found,
        urls_ingested=job.urls_ingested,
        urls_deduped=job.urls_deduped,
        claims_extracted=job.claims_extracted,
        result_meta=job.result_meta or {},
        cron_expression=job.cron_expression,
        created_at=job.created_at.isoformat() if job.created_at else None,
    )


# ── 后台任务执行器 ────────────────────────────────────────


async def _run_collection_job(
    job_uid: str, case_uid: str, extract_claims: bool
) -> None:
    """在后台执行采集任务。"""
    from aegi_core.db.session import ENGINE
    from aegi_core.services.osint_collector import OSINTCollector
    from aegi_core.ws.manager import ws_manager
    from aegi_core.ws.protocol import NotifyKind

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        job = (
            await session.execute(
                sa.select(CollectionJob).where(CollectionJob.uid == job_uid)
            )
        ).scalar_one_or_none()
        if not job:
            return

        job.status = "running"
        await session.commit()

        try:
            searxng = get_searxng_client()
            llm = get_llm_client()
            qdrant = get_qdrant_store()

            collector = OSINTCollector(
                searxng=searxng,
                llm=llm,
                qdrant=qdrant,
                db_session=session,
            )
            try:
                result = await collector.collect(
                    job.query,
                    case_uid,
                    categories=job.categories,
                    language=job.language,
                    max_results=job.max_results,
                    extract_claims=extract_claims,
                )
            finally:
                await collector.close()

            job.status = "completed"
            job.urls_found = result.urls_found
            job.urls_ingested = result.urls_ingested
            job.urls_deduped = result.urls_deduped
            job.claims_extracted = result.claims_extracted
            job.result_meta = {
                "artifact_version_uids": result.artifact_version_uids,
                "source_claim_uids": result.source_claim_uids,
                "errors": result.errors,
            }
            await session.commit()

            # 通过 WebSocket 通知
            await ws_manager.broadcast(
                NotifyKind.collection_done,
                {
                    "job_uid": job_uid,
                    "case_uid": case_uid,
                    "status": "completed",
                    "urls_ingested": result.urls_ingested,
                    "claims_extracted": result.claims_extracted,
                },
            )

        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            await session.commit()


# ── 端点 ─────────────────────────────────────────────────────


@router.post("/jobs", response_model=CollectionJobResponse)
async def create_job(
    case_uid: str,
    body: CreateJobRequest,
    bg: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> CollectionJobResponse:
    """创建 OSINT 采集任务并在后台启动。"""
    job_uid = f"cj_{uuid4().hex}"
    job = CollectionJob(
        uid=job_uid,
        case_uid=case_uid,
        query=body.query,
        categories=body.categories,
        language=body.language,
        max_results=body.max_results,
        status="pending",
        cron_expression=body.cron_expression,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    bg.add_task(_run_collection_job, job_uid, case_uid, body.extract_claims)
    return _job_to_response(job)


@router.get("/jobs", response_model=PaginatedJobs)
async def list_jobs(
    case_uid: str,
    offset: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedJobs:
    """列出 case 下的采集任务。"""
    total_q = (
        sa.select(sa.func.count())
        .select_from(CollectionJob)
        .where(CollectionJob.case_uid == case_uid)
    )
    total = (await session.execute(total_q)).scalar() or 0

    rows_q = (
        sa.select(CollectionJob)
        .where(CollectionJob.case_uid == case_uid)
        .order_by(CollectionJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(rows_q)).scalars().all()

    items = [
        CollectionJobSummary(
            uid=r.uid,
            query=r.query,
            status=r.status,
            urls_found=r.urls_found,
            urls_ingested=r.urls_ingested,
            claims_extracted=r.claims_extracted,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]
    return PaginatedJobs(items=items, total=total)


@router.get("/jobs/{job_uid}", response_model=CollectionJobResponse)
async def get_job(
    case_uid: str,
    job_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> CollectionJobResponse:
    """按 UID 获取采集任务。"""
    job = (
        await session.execute(
            sa.select(CollectionJob).where(
                CollectionJob.uid == job_uid,
                CollectionJob.case_uid == case_uid,
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise AegiHTTPError(404, "not_found", f"Job {job_uid} not found", {})
    return _job_to_response(job)


@router.post("/jobs/{job_uid}/trigger")
async def trigger_job(
    case_uid: str,
    job_uid: str,
    bg: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """重新触发已有的采集任务。"""
    job = (
        await session.execute(
            sa.select(CollectionJob).where(
                CollectionJob.uid == job_uid,
                CollectionJob.case_uid == case_uid,
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise AegiHTTPError(404, "not_found", f"Job {job_uid} not found", {})
    if job.status == "running":
        raise AegiHTTPError(409, "conflict", "Job is already running", {})

    job.status = "pending"
    await session.commit()
    bg.add_task(_run_collection_job, job_uid, case_uid, True)
    return {"status": "triggered"}


@router.delete("/jobs/{job_uid}")
async def delete_job(
    case_uid: str,
    job_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """删除采集任务。"""
    job = (
        await session.execute(
            sa.select(CollectionJob).where(
                CollectionJob.uid == job_uid,
                CollectionJob.case_uid == case_uid,
            )
        )
    ).scalar_one_or_none()
    if not job:
        raise AegiHTTPError(404, "not_found", f"Job {job_uid} not found", {})
    await session.delete(job)
    await session.commit()
    return {"status": "deleted"}


@router.post("/search_preview", response_model=list[SearchPreviewItem])
async def search_preview_endpoint(
    case_uid: str,
    body: SearchPreviewRequest,
) -> list[SearchPreviewItem]:
    """预览搜索结果 + 可信度评分 — 不入库。"""
    from aegi_core.services.osint_collector import search_preview

    searxng = get_searxng_client()
    results = await search_preview(
        searxng,
        body.query,
        categories=body.categories,
        language=body.language,
        limit=body.limit,
    )
    return [SearchPreviewItem(**r) for r in results]
