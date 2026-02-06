# Author: msq
"""Hypothesis API routes – generate/score/explain.

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (1.2)
        openspec/changes/ach-hypothesis-analysis/design.md (API Contract)
Evidence:
  - POST /cases/{case_uid}/hypotheses/generate
  - POST /cases/{case_uid}/hypotheses/{hypothesis_uid}/score
  - GET  /cases/{case_uid}/hypotheses/{hypothesis_uid}/explain
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_backend
from aegi_core.api.errors import not_found
from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.db.models.action import Action
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.hypothesis_engine import (
    LLMBackend,
    analyze_hypothesis,
    generate_hypotheses as svc_generate,
)

router = APIRouter(prefix="/cases/{case_uid}/hypotheses", tags=["hypotheses"])


class GenerateIn(BaseModel):
    assertion_uids: list[str]
    source_claim_uids: list[str]
    context: dict | None = None


class GenerateOut(BaseModel):
    hypotheses: list[dict]
    action_uid: str
    trace_id: str


class ScoreOut(BaseModel):
    hypothesis_uid: str
    coverage_score: float
    confidence: float
    gap_list: list[str]
    adversarial: dict
    action_uid: str
    trace_id: str


class ExplainOut(BaseModel):
    hypothesis_uid: str
    hypothesis_text: str
    supporting_assertion_uids: list[str]
    contradicting_assertion_uids: list[str]
    gap_list: list[str]
    adversarial: dict
    provenance: list[dict]


def _assertion_to_v1(row: Assertion) -> AssertionV1:
    return AssertionV1(
        uid=row.uid,
        case_uid=row.case_uid,
        kind=row.kind,
        value=row.value,
        source_claim_uids=row.source_claim_uids,
        confidence=row.confidence,
        modality=row.modality,
        segment_ref=row.segment_ref,
        media_time_range=row.media_time_range,
        created_at=row.created_at,
    )


def _sc_to_v1(row: SourceClaim) -> SourceClaimV1:
    return SourceClaimV1(
        uid=row.uid,
        case_uid=row.case_uid,
        artifact_version_uid=row.artifact_version_uid,
        chunk_uid=row.chunk_uid,
        evidence_uid=row.evidence_uid,
        quote=row.quote,
        selectors=row.selectors,
        attributed_to=row.attributed_to,
        modality=row.modality,
        segment_ref=row.segment_ref,
        media_time_range=row.media_time_range,
        language=row.language,
        original_quote=row.original_quote,
        translation=row.translation,
        translation_meta=row.translation_meta,
        created_at=row.created_at,
    )


@router.post("/generate", status_code=201)
async def generate_hypotheses_endpoint(
    case_uid: str,
    body: GenerateIn,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMBackend = Depends(get_llm_backend),
) -> GenerateOut:
    """生成竞争性假设。"""
    rows_a = await session.execute(
        sa.select(Assertion).where(Assertion.uid.in_(body.assertion_uids))
    )
    assertions = [_assertion_to_v1(r) for r in rows_a.scalars().all()]

    rows_sc = await session.execute(
        sa.select(SourceClaim).where(SourceClaim.uid.in_(body.source_claim_uids))
    )
    source_claims = [_sc_to_v1(r) for r in rows_sc.scalars().all()]

    budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)
    results, svc_action, svc_trace, _ = await svc_generate(
        assertions=assertions,
        source_claims=source_claims,
        case_uid=case_uid,
        llm=llm,
        budget=budget,
        context=body.context,
    )

    action_uid = f"act_{uuid4().hex}"
    hyp_dicts: list[dict] = []
    for r in results:
        hyp_uid = f"hyp_{uuid4().hex}"
        session.add(
            Hypothesis(
                uid=hyp_uid,
                case_uid=case_uid,
                label=r.hypothesis_text,
                supporting_assertion_uids=r.supporting_assertion_uids,
                contradicting_assertion_uids=r.contradicting_assertion_uids,
                coverage_score=r.coverage_score,
                confidence=r.confidence,
                gap_list=r.gap_list,
                adversarial_result={},
                trace_id=svc_action.trace_id,
            )
        )
        hyp_dicts.append(
            {
                "hypothesis_uid": hyp_uid,
                "hypothesis_text": r.hypothesis_text,
                "coverage_score": r.coverage_score,
                "confidence": r.confidence,
            }
        )

    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="hypotheses.generate",
            inputs=body.model_dump(exclude_none=True),
            outputs={"hypothesis_uids": [h["hypothesis_uid"] for h in hyp_dicts]},
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    return GenerateOut(
        hypotheses=hyp_dicts,
        action_uid=action_uid,
        trace_id=svc_action.trace_id or "",
    )


@router.post("/{hypothesis_uid}/score", status_code=200)
async def score_hypothesis(
    case_uid: str,
    hypothesis_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> ScoreOut:
    """对假设执行评分。"""
    hyp = await session.get(Hypothesis, hypothesis_uid)
    if hyp is None:
        raise not_found("Hypothesis", hypothesis_uid)

    rows_a = await session.execute(sa.select(Assertion).where(Assertion.case_uid == case_uid))
    assertions = [_assertion_to_v1(r) for r in rows_a.scalars().all()]

    rows_sc = await session.execute(sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid))
    source_claims = [_sc_to_v1(r) for r in rows_sc.scalars().all()]

    result = analyze_hypothesis(hyp.label, assertions, source_claims)

    hyp.supporting_assertion_uids = result.supporting_assertion_uids
    hyp.contradicting_assertion_uids = result.contradicting_assertion_uids
    hyp.coverage_score = result.coverage_score
    hyp.confidence = result.confidence
    hyp.gap_list = result.gap_list
    hyp.adversarial_result = {}

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="hypotheses.score",
            inputs={"hypothesis_uid": hypothesis_uid},
            outputs={
                "coverage_score": result.coverage_score,
                "confidence": result.confidence,
            },
        )
    )
    await session.commit()

    return ScoreOut(
        hypothesis_uid=hypothesis_uid,
        coverage_score=result.coverage_score,
        confidence=result.confidence,
        gap_list=result.gap_list,
        adversarial={},
        action_uid=action_uid,
        trace_id=hyp.trace_id or "",
    )


@router.get("/{hypothesis_uid}/explain", status_code=200)
async def explain_hypothesis(
    case_uid: str,
    hypothesis_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> ExplainOut:
    """返回假设的可回放解释。"""
    hyp = await session.get(Hypothesis, hypothesis_uid)
    if hyp is None:
        raise not_found("Hypothesis", hypothesis_uid)

    provenance: list[dict] = []
    if hyp.supporting_assertion_uids:
        all_sc = await session.execute(
            sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid)
        )
        for sc in all_sc.scalars().all():
            provenance.append(
                {
                    "source_claim_uid": sc.uid,
                    "quote": sc.quote,
                    "attributed_to": sc.attributed_to,
                }
            )

    return ExplainOut(
        hypothesis_uid=hypothesis_uid,
        hypothesis_text=hyp.label,
        supporting_assertion_uids=hyp.supporting_assertion_uids or [],
        contradicting_assertion_uids=hyp.contradicting_assertion_uids or [],
        gap_list=hyp.gap_list or [],
        adversarial=hyp.adversarial_result or {},
        provenance=provenance,
    )
