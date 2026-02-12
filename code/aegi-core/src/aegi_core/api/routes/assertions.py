# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.assertion import Assertion


router = APIRouter(prefix="/assertions", tags=["assertions"])


@router.get("/{assertion_uid}")
async def get_assertion(
    assertion_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    a = await session.get(Assertion, assertion_uid)
    if a is None:
        raise not_found("Assertion", assertion_uid)

    return {
        "assertion_uid": a.uid,
        "case_uid": a.case_uid,
        "kind": a.kind,
        "source_claim_uids": a.source_claim_uids,
        "value": a.value,
        "confidence": a.confidence,
    }


@router.get("/cases/{case_uid}/list")
async def list_assertions(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    kind: str | None = None,
    confidence_min: float | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = sa.select(Assertion).where(Assertion.case_uid == case_uid)
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(Assertion)
        .where(Assertion.case_uid == case_uid)
    )

    if kind:
        stmt = stmt.where(Assertion.kind == kind)
        count_stmt = count_stmt.where(Assertion.kind == kind)
    if confidence_min is not None:
        stmt = stmt.where(Assertion.confidence >= confidence_min)
        count_stmt = count_stmt.where(Assertion.confidence >= confidence_min)

    total = (await session.execute(count_stmt)).scalar() or 0
    rows = (
        (
            await session.execute(
                stmt.order_by(Assertion.created_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "items": [
            {
                "assertion_uid": a.uid,
                "case_uid": a.case_uid,
                "kind": a.kind,
                "source_claim_uids": a.source_claim_uids,
                "value": a.value,
                "confidence": a.confidence,
            }
            for a in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
