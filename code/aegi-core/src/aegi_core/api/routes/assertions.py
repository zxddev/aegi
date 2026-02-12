# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.contracts.schemas import (
    AssertionFeedbackCreate,
    AssertionFeedbackSummary,
    AssertionFeedbackV1,
)
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.assertion_feedback import AssertionFeedback
from aegi_core.services import feedback_service


router = APIRouter(prefix="/assertions", tags=["assertions"])


def _feedback_to_v1(row: AssertionFeedback) -> AssertionFeedbackV1:
    return AssertionFeedbackV1(
        uid=row.uid,
        assertion_uid=row.assertion_uid,
        case_uid=row.case_uid,
        user_id=row.user_id,
        verdict=row.verdict,
        confidence_override=row.confidence_override,
        comment=row.comment,
        suggested_value=row.suggested_value,
        created_at=row.created_at,
    )


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


@router.post("/{assertion_uid}/feedback", response_model=AssertionFeedbackV1)
async def create_feedback(
    assertion_uid: str,
    body: AssertionFeedbackCreate,
    session: AsyncSession = Depends(get_db_session),
) -> AssertionFeedbackV1:
    row = await feedback_service.create_feedback(
        session,
        assertion_uid=assertion_uid,
        user_id=body.user_id,
        verdict=body.verdict,
        confidence_override=body.confidence_override,
        comment=body.comment,
        suggested_value=body.suggested_value,
    )
    return _feedback_to_v1(row)


@router.get("/{assertion_uid}/feedback", response_model=list[AssertionFeedbackV1])
async def list_feedback(
    assertion_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[AssertionFeedbackV1]:
    rows = await feedback_service.list_feedback_for_assertion(session, assertion_uid)
    return [_feedback_to_v1(row) for row in rows]


@router.get(
    "/{assertion_uid}/feedback/summary",
    response_model=AssertionFeedbackSummary,
)
async def get_feedback_summary(
    assertion_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> AssertionFeedbackSummary:
    summary = await feedback_service.get_feedback_summary(session, assertion_uid)
    return AssertionFeedbackSummary.model_validate(summary)


@router.delete("/{assertion_uid}/feedback/{feedback_uid}")
async def delete_feedback(
    assertion_uid: str,
    feedback_uid: str,
    user_id: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await feedback_service.delete_feedback(
        session,
        assertion_uid=assertion_uid,
        feedback_uid=feedback_uid,
        user_id=user_id,
    )
    return {"status": "deleted"}


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
