# Author: msq
"""Assertion 反馈服务。"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.assertion_feedback import AssertionFeedback
from aegi_core.db.models.case import Case
from aegi_core.db.utils import utcnow
from aegi_core.services.event_bus import AegiEvent, get_event_bus

VERDICT_AGREE = "agree"
VERDICT_DISAGREE = "disagree"
VERDICT_NEED_MORE = "need_more_evidence"
VERDICT_PARTIAL = "partially_agree"


async def _ensure_assertion_exists(db: AsyncSession, assertion_uid: str) -> Assertion:
    assertion = await db.get(Assertion, assertion_uid)
    if assertion is None:
        raise not_found("Assertion", assertion_uid)
    return assertion


async def _ensure_case_exists(db: AsyncSession, case_uid: str) -> Case:
    case = await db.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)
    return case


async def create_feedback(
    db: AsyncSession,
    *,
    assertion_uid: str,
    user_id: str,
    verdict: str,
    confidence_override: float | None = None,
    comment: str | None = None,
    suggested_value: dict | None = None,
) -> AssertionFeedback:
    """创建或更新反馈（同一 user+assertion 为 upsert）。"""
    assertion = await _ensure_assertion_exists(db, assertion_uid)

    row = (
        await db.execute(
            sa.select(AssertionFeedback).where(
                AssertionFeedback.assertion_uid == assertion_uid,
                AssertionFeedback.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = AssertionFeedback(
            uid=f"afb_{uuid4().hex}",
            assertion_uid=assertion_uid,
            case_uid=assertion.case_uid,
            user_id=user_id,
            verdict=verdict,
            confidence_override=confidence_override,
            comment=comment,
            suggested_value=suggested_value,
        )
        db.add(row)
    else:
        row.case_uid = assertion.case_uid
        row.verdict = verdict
        row.confidence_override = confidence_override
        row.comment = comment
        row.suggested_value = suggested_value
        row.created_at = utcnow()

    await db.commit()
    await db.refresh(row)

    await get_event_bus().emit(
        AegiEvent(
            event_type="assertion.feedback_received",
            case_uid=assertion.case_uid,
            severity="low",
            payload={
                "feedback_uid": row.uid,
                "assertion_uid": assertion_uid,
                "case_uid": assertion.case_uid,
                "user_id": user_id,
                "verdict": verdict,
                "confidence_override": confidence_override,
            },
        )
    )
    return row


async def list_feedback_for_assertion(
    db: AsyncSession,
    assertion_uid: str,
) -> list[AssertionFeedback]:
    """查询某个 Assertion 的全部反馈。"""
    await _ensure_assertion_exists(db, assertion_uid)
    return (
        (
            await db.execute(
                sa.select(AssertionFeedback)
                .where(AssertionFeedback.assertion_uid == assertion_uid)
                .order_by(AssertionFeedback.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


def _consensus(
    *,
    total_feedback: int,
    agree_count: int,
    disagree_count: int,
    need_more_evidence_count: int,
) -> str:
    if total_feedback == 0:
        return "no_feedback"
    half = total_feedback / 2
    if agree_count > half:
        return "agreed"
    if disagree_count > half:
        return "disputed"
    if need_more_evidence_count > half:
        return "uncertain"
    return "mixed"


async def get_feedback_summary(
    db: AsyncSession,
    assertion_uid: str,
) -> dict:
    """获取某个 Assertion 的反馈汇总。"""
    await _ensure_assertion_exists(db, assertion_uid)

    row = (
        await db.execute(
            sa.select(
                sa.func.count(AssertionFeedback.uid).label("total_feedback"),
                sa.func.sum(
                    sa.case((AssertionFeedback.verdict == VERDICT_AGREE, 1), else_=0)
                ).label("agree_count"),
                sa.func.sum(
                    sa.case((AssertionFeedback.verdict == VERDICT_DISAGREE, 1), else_=0)
                ).label("disagree_count"),
                sa.func.sum(
                    sa.case(
                        (AssertionFeedback.verdict == VERDICT_NEED_MORE, 1), else_=0
                    )
                ).label("need_more_evidence_count"),
                sa.func.sum(
                    sa.case((AssertionFeedback.verdict == VERDICT_PARTIAL, 1), else_=0)
                ).label("partially_agree_count"),
                sa.func.avg(AssertionFeedback.confidence_override).label(
                    "avg_confidence_override"
                ),
            ).where(AssertionFeedback.assertion_uid == assertion_uid)
        )
    ).one()

    total_feedback = int(row.total_feedback or 0)
    agree_count = int(row.agree_count or 0)
    disagree_count = int(row.disagree_count or 0)
    need_more_evidence_count = int(row.need_more_evidence_count or 0)
    partially_agree_count = int(row.partially_agree_count or 0)
    avg_confidence_override = (
        float(row.avg_confidence_override)
        if row.avg_confidence_override is not None
        else None
    )

    return {
        "assertion_uid": assertion_uid,
        "total_feedback": total_feedback,
        "agree_count": agree_count,
        "disagree_count": disagree_count,
        "need_more_evidence_count": need_more_evidence_count,
        "partially_agree_count": partially_agree_count,
        "avg_confidence_override": avg_confidence_override,
        "consensus": _consensus(
            total_feedback=total_feedback,
            agree_count=agree_count,
            disagree_count=disagree_count,
            need_more_evidence_count=need_more_evidence_count,
        ),
    }


async def get_user_feedback_history(
    db: AsyncSession,
    user_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[AssertionFeedback]:
    """获取某用户的反馈历史。"""
    return (
        (
            await db.execute(
                sa.select(AssertionFeedback)
                .where(AssertionFeedback.user_id == user_id)
                .order_by(AssertionFeedback.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def get_case_feedback_stats(
    db: AsyncSession,
    case_uid: str,
) -> dict:
    """获取某个 Case 下 Assertion 的反馈统计。"""
    await _ensure_case_exists(db, case_uid)

    total_assertions = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(Assertion)
            .where(Assertion.case_uid == case_uid)
        )
    ).scalar_one()

    assertions_with_feedback = (
        await db.execute(
            sa.select(
                sa.func.count(sa.distinct(AssertionFeedback.assertion_uid))
            ).where(AssertionFeedback.case_uid == case_uid)
        )
    ).scalar_one()

    aggregate = (
        await db.execute(
            sa.select(
                sa.func.count(AssertionFeedback.uid).label("total_feedback"),
                sa.func.sum(
                    sa.case((AssertionFeedback.verdict == VERDICT_AGREE, 1), else_=0)
                ).label("agree_count"),
            ).where(AssertionFeedback.case_uid == case_uid)
        )
    ).one()
    total_feedback = int(aggregate.total_feedback or 0)
    agree_count = int(aggregate.agree_count or 0)

    disputed_rows = (
        (
            await db.execute(
                sa.select(AssertionFeedback.assertion_uid)
                .where(AssertionFeedback.case_uid == case_uid)
                .group_by(AssertionFeedback.assertion_uid)
                .having(
                    sa.func.sum(
                        sa.case(
                            (AssertionFeedback.verdict == VERDICT_DISAGREE, 1), else_=0
                        )
                    )
                    > (sa.func.count(AssertionFeedback.uid) / 2.0)
                )
            )
        )
        .scalars()
        .all()
    )

    total_assertions_int = int(total_assertions or 0)
    assertions_with_feedback_int = int(assertions_with_feedback or 0)
    feedback_coverage = (
        assertions_with_feedback_int / total_assertions_int
        if total_assertions_int > 0
        else 0.0
    )
    overall_agreement_rate = (
        agree_count / total_feedback if total_feedback > 0 else None
    )

    return {
        "case_uid": case_uid,
        "total_assertions": total_assertions_int,
        "assertions_with_feedback": assertions_with_feedback_int,
        "feedback_coverage": feedback_coverage,
        "overall_agreement_rate": overall_agreement_rate,
        "disputed_assertions": list(disputed_rows),
    }


async def delete_feedback(
    db: AsyncSession,
    *,
    assertion_uid: str,
    feedback_uid: str,
    user_id: str,
) -> None:
    """删除反馈，仅创建者允许删除。"""
    feedback = (
        await db.execute(
            sa.select(AssertionFeedback).where(
                AssertionFeedback.uid == feedback_uid,
                AssertionFeedback.assertion_uid == assertion_uid,
            )
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise not_found("AssertionFeedback", feedback_uid)
    if feedback.user_id != user_id:
        raise AegiHTTPError(
            403,
            "forbidden",
            "Only feedback creator can delete",
            {"feedback_uid": feedback_uid, "user_id": user_id},
        )

    await db.delete(feedback)
    await db.commit()
