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

from fastapi import APIRouter

from pydantic import BaseModel

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


@router.post("/generate", status_code=201)
async def generate_hypotheses(case_uid: str, body: GenerateIn) -> GenerateOut:
    """生成竞争性假设（桩实现，完整版需注入 LLM + DB session）。"""
    # 桩：返回空结果，实际集成在 service 层完成
    return GenerateOut(
        hypotheses=[],
        action_uid="stub",
        trace_id="stub",
    )


@router.post("/{hypothesis_uid}/score", status_code=200)
async def score_hypothesis(case_uid: str, hypothesis_uid: str) -> ScoreOut:
    """对假设执行评分（桩实现）。"""
    return ScoreOut(
        hypothesis_uid=hypothesis_uid,
        coverage_score=0.0,
        confidence=0.0,
        gap_list=[],
        adversarial={},
        action_uid="stub",
        trace_id="stub",
    )


@router.get("/{hypothesis_uid}/explain", status_code=200)
async def explain_hypothesis(case_uid: str, hypothesis_uid: str) -> ExplainOut:
    """返回假设的可回放解释（桩实现）。"""
    return ExplainOut(
        hypothesis_uid=hypothesis_uid,
        hypothesis_text="",
        supporting_assertion_uids=[],
        contradicting_assertion_uids=[],
        gap_list=[],
        adversarial={},
        provenance=[],
    )
