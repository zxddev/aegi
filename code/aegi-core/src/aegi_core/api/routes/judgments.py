# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.judgment import Judgment


router = APIRouter(prefix="/judgments", tags=["judgments"])


@router.get("/{judgment_uid}")
async def get_judgment(
    judgment_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    j = await session.get(Judgment, judgment_uid)
    if j is None:
        raise not_found("Judgment", judgment_uid)

    return {
        "judgment_uid": j.uid,
        "case_uid": j.case_uid,
        "title": j.title,
        "assertion_uids": j.assertion_uids,
    }


@router.get("/cases/{case_uid}/list")
async def list_judgments(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(Judgment)
        .where(Judgment.case_uid == case_uid)
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        sa.select(Judgment)
        .where(Judgment.case_uid == case_uid)
        .order_by(Judgment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "judgment_uid": j.uid,
                "case_uid": j.case_uid,
                "title": j.title,
                "assertion_uids": j.assertion_uids,
            }
            for j in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
