# Author: msq
"""报告生成与查询 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.api.errors import not_found
from aegi_core.contracts.schemas import ReportSummaryV1, ReportV1, ReportSectionV1
from aegi_core.db.models.report import Report
from aegi_core.infra.llm_client import LLMClient
from aegi_core.services.report_generator import ReportGenerator

router = APIRouter(prefix="/cases/{case_uid}/reports", tags=["reports"])

_generator = ReportGenerator()


class GenerateReportRequest(BaseModel):
    report_type: str  # briefing | ach_matrix | evidence_chain | narrative | quality
    sections: list[str] | None = None
    language: str = "en"


@router.post("/generate")
async def generate_report(
    case_uid: str,
    body: GenerateReportRequest,
    db: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    report = await _generator.generate(
        case_uid=case_uid,
        report_type=body.report_type,
        sections_filter=body.sections,
        language=body.language,
        db=db,
        llm=llm,
    )
    return report.model_dump()


@router.get("")
async def list_reports(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(Report)
        .where(Report.case_uid == case_uid)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        sa.select(Report)
        .where(Report.case_uid == case_uid)
        .order_by(Report.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "items": [
            ReportSummaryV1(
                uid=r.uid,
                case_uid=r.case_uid,
                report_type=r.report_type,
                title=r.title,
                created_at=r.created_at,
            ).model_dump()
            for r in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{report_uid}")
async def get_report(
    case_uid: str,
    report_uid: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    r = await db.get(Report, report_uid)
    if r is None or r.case_uid != case_uid:
        raise not_found("Report", report_uid)

    sections_data = r.sections.get("sections", []) if r.sections else []
    sections = [ReportSectionV1.model_validate(s) for s in sections_data]

    return ReportV1(
        uid=r.uid,
        case_uid=r.case_uid,
        report_type=r.report_type,
        title=r.title,
        sections=sections,
        rendered_markdown=r.rendered_markdown,
        config=r.config or {},
        trace_id=r.trace_id,
        created_at=r.created_at,
    ).model_dump()


@router.get("/{report_uid}/markdown")
async def get_report_markdown(
    case_uid: str,
    report_uid: str,
    db: AsyncSession = Depends(get_db_session),
) -> PlainTextResponse:
    r = await db.get(Report, report_uid)
    if r is None or r.case_uid != case_uid:
        raise not_found("Report", report_uid)
    return PlainTextResponse(
        content=r.rendered_markdown,
        media_type="text/markdown",
    )


@router.get("/{report_uid}/json")
async def get_report_json(
    case_uid: str,
    report_uid: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    r = await db.get(Report, report_uid)
    if r is None or r.case_uid != case_uid:
        raise not_found("Report", report_uid)
    return r.sections or {}
