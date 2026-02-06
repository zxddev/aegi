# Author: msq
"""Quality scoring API routes – meta-cognition quality assessment.

Source: openspec/changes/meta-cognition-quality-scoring/design.md
Evidence:
  - POST /cases/{case_uid}/quality/score_judgment
  - GET /cases/{case_uid}/quality/judgments/{judgment_uid}
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
from aegi_core.db.models.action import Action
from aegi_core.services.confidence_scorer import (
    QualityInput,
    QualityReportV1,
    score_confidence,
)

router = APIRouter(prefix="/cases/{case_uid}/quality", tags=["quality"])


class ScoreJudgmentRequest(BaseModel):
    judgment_uid: str
    title: str
    assertion_uids: list[str] = Field(default_factory=list)
    assertions: list[AssertionV1] = Field(default_factory=list)
    hypotheses: list[HypothesisV1] = Field(default_factory=list)
    narratives: list[NarrativeV1] = Field(default_factory=list)
    source_claims: list[SourceClaimV1] = Field(default_factory=list)
    forecasts: list[dict] | None = None


@router.post("/score_judgment")
async def score_judgment(
    case_uid: str,
    req: ScoreJudgmentRequest,
    session: AsyncSession = Depends(get_db_session),
) -> QualityReportV1:
    """评估 judgment 的元认知质量。"""
    inp = QualityInput(
        judgment_uid=req.judgment_uid,
        case_uid=case_uid,
        title=req.title,
        assertion_uids=req.assertion_uids,
        assertions=req.assertions,
        hypotheses=req.hypotheses,
        narratives=req.narratives,
        source_claims=req.source_claims,
        forecasts=req.forecasts,
    )
    report = score_confidence(inp)

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="quality.score_judgment",
            inputs={"judgment_uid": req.judgment_uid},
            outputs=report.model_dump(mode="json"),
            trace_id=report.trace_id,
        )
    )
    await session.commit()

    return report


@router.get("/judgments/{judgment_uid}")
async def get_judgment_quality(
    case_uid: str,
    judgment_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """获取已缓存的 judgment 质量报告。"""
    row = await session.execute(
        sa.select(Action)
        .where(
            Action.case_uid == case_uid,
            Action.action_type == "quality.score_judgment",
            Action.inputs["judgment_uid"].astext == judgment_uid,
        )
        .order_by(Action.created_at.desc())
        .limit(1)
    )
    action = row.scalars().first()
    if action is None:
        raise not_found("QualityReport", judgment_uid)

    return action.outputs
