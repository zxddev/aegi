# Author: msq
"""Investigation history and control API."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import AegiHTTPError
from aegi_core.db.models.investigation import Investigation
from aegi_core.db.utils import utcnow
from aegi_core.services.investigation_agent import cancel_investigation_run

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


class InvestigationSummary(BaseModel):
    uid: str
    case_uid: str
    trigger_event_type: str
    trigger_event_uid: str
    status: str
    total_claims_extracted: int
    gap_resolved: bool
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_by: str | None = None
    created_at: str | None = None


class InvestigationDetail(BaseModel):
    uid: str
    case_uid: str
    trigger_event_type: str
    trigger_event_uid: str
    status: str
    config: dict = Field(default_factory=dict)
    rounds: list[dict] = Field(default_factory=list)
    total_claims_extracted: int
    gap_resolved: bool
    started_at: str | None = None
    completed_at: str | None = None
    cancelled_by: str | None = None
    created_at: str | None = None


class PaginatedInvestigations(BaseModel):
    items: list[InvestigationSummary]
    total: int


class CancelInvestigationRequest(BaseModel):
    cancelled_by: str = "expert"


def _to_summary(row: Investigation) -> InvestigationSummary:
    return InvestigationSummary(
        uid=row.uid,
        case_uid=row.case_uid,
        trigger_event_type=row.trigger_event_type,
        trigger_event_uid=row.trigger_event_uid,
        status=row.status,
        total_claims_extracted=row.total_claims_extracted,
        gap_resolved=row.gap_resolved,
        started_at=row.started_at.isoformat() if row.started_at else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        cancelled_by=row.cancelled_by,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _to_detail(row: Investigation) -> InvestigationDetail:
    return InvestigationDetail(
        uid=row.uid,
        case_uid=row.case_uid,
        trigger_event_type=row.trigger_event_type,
        trigger_event_uid=row.trigger_event_uid,
        status=row.status,
        config=row.config or {},
        rounds=row.rounds or [],
        total_claims_extracted=row.total_claims_extracted,
        gap_resolved=row.gap_resolved,
        started_at=row.started_at.isoformat() if row.started_at else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        cancelled_by=row.cancelled_by,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.get("", response_model=PaginatedInvestigations)
async def list_investigations(
    case_uid: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedInvestigations:
    filters = []
    if case_uid:
        filters.append(Investigation.case_uid == case_uid)
    if status:
        filters.append(Investigation.status == status)

    count_stmt = sa.select(sa.func.count()).select_from(Investigation)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await session.execute(count_stmt)).scalar() or 0

    rows_stmt = (
        sa.select(Investigation)
        .order_by(Investigation.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows = (await session.execute(rows_stmt)).scalars().all()

    return PaginatedInvestigations(
        items=[_to_summary(row) for row in rows],
        total=total,
    )


@router.get("/{uid}", response_model=InvestigationDetail)
async def get_investigation(
    uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> InvestigationDetail:
    row = (
        await session.execute(sa.select(Investigation).where(Investigation.uid == uid))
    ).scalar_one_or_none()
    if row is None:
        raise AegiHTTPError(404, "not_found", f"Investigation {uid} not found", {})
    return _to_detail(row)


@router.post("/{uid}/cancel")
async def cancel_investigation(
    uid: str,
    body: CancelInvestigationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = (
        await session.execute(sa.select(Investigation).where(Investigation.uid == uid))
    ).scalar_one_or_none()
    if row is None:
        raise AegiHTTPError(404, "not_found", f"Investigation {uid} not found", {})
    if row.status != "running":
        raise AegiHTTPError(
            409,
            "conflict",
            f"Investigation {uid} is not running",
            {"status": row.status},
        )

    row.status = "cancelled"
    row.cancelled_by = body.cancelled_by
    row.completed_at = utcnow()
    await session.commit()

    signal_sent = await cancel_investigation_run(uid)
    return {"uid": uid, "status": "cancelled", "cancel_signal_sent": signal_sent}
