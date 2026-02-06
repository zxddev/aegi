# Author: msq
"""Quality scoring API routes – meta-cognition quality assessment.

Source: openspec/changes/meta-cognition-quality-scoring/design.md
Evidence:
  - POST /cases/{case_uid}/quality/score_judgment
  - GET /cases/{case_uid}/quality/judgments/{judgment_uid}
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
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
    forecasts: Optional[list[dict]] = None


@router.post("/score_judgment")
async def score_judgment(case_uid: str, req: ScoreJudgmentRequest) -> QualityReportV1:
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
    return score_confidence(inp)


@router.get("/judgments/{judgment_uid}")
async def get_judgment_quality(case_uid: str, judgment_uid: str) -> dict:
    """获取已缓存的 judgment 质量报告（桩实现）。"""
    return {
        "status": "stub",
        "detail": "Full persistence integration deferred to merge coordinator",
        "case_uid": case_uid,
        "judgment_uid": judgment_uid,
    }
