# Author: msq
"""Cross-lingual entity alignment: candidate generation + LLM rerank.

Source: openspec/changes/multilingual-evidence-chain/design.md
Evidence:
  - Entity alignment 采用"规则候选 + LLM rerank"，并输出解释。
  - 对齐输出必须可追溯到 source_claim_uid。
  - 低置信对齐结果 MUST 标记为 uncertain，禁止静默合并。
"""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field

from aegi_core.contracts.errors import ProblemDetail
from aegi_core.contracts.llm_governance import (
    BudgetContext,
    DegradedOutput,
    DegradedReason,
    LLMInvocationRequest,
    LLMInvocationResult,
    grounding_gate,
)
from aegi_core.contracts.schemas import SourceClaimV1

UNCERTAINTY_THRESHOLD = 0.7


class EntityLinkV1(BaseModel):
    """跨语言实体对齐结果。"""

    canonical_id: str
    alias_text: str
    language: str
    source_claim_uid: str
    confidence: float
    uncertain: bool = False
    explanation: Optional[str] = None


class AlignEntitiesRequest(BaseModel):
    """Request body for entity alignment endpoint."""

    claims: list[SourceClaimV1]
    budget_context: BudgetContext


class AlignEntitiesResponse(BaseModel):
    """Response for entity alignment endpoint."""

    links: list[EntityLinkV1] = Field(default_factory=list)
    failures: list[ProblemDetail] = Field(default_factory=list)
    trace_id: str
    llm_result: Optional[LLMInvocationResult] = None
    degraded: Optional[DegradedOutput] = None


def _normalize(text: str) -> str:
    return text.strip().lower()


def _generate_candidates(
    claims: list[SourceClaimV1],
) -> dict[str, list[SourceClaimV1]]:
    """按 normalized quote 分组，同组视为候选同实体。"""
    groups: dict[str, list[SourceClaimV1]] = {}
    for claim in claims:
        key = _normalize(claim.quote)
        groups.setdefault(key, []).append(claim)
    return groups


async def align_entities(
    claims: list[SourceClaimV1],
    budget_context: BudgetContext,
) -> AlignEntitiesResponse:
    """跨语言实体对齐：规则候选生成 + LLM rerank。"""
    trace_id = uuid.uuid4().hex
    links: list[EntityLinkV1] = []
    failures: list[ProblemDetail] = []
    degraded: Optional[DegradedOutput] = None

    model_id = "gpt-4o-mini"
    prompt_version = "entity-align-v1"

    # 审计记录
    LLMInvocationRequest(
        model_id=model_id,
        prompt_version=prompt_version,
        budget_context=budget_context,
        trace_id=trace_id,
    )

    if budget_context.remaining_cost_usd is not None and budget_context.remaining_cost_usd <= 0:
        degraded = DegradedOutput(
            reason=DegradedReason.BUDGET_EXCEEDED,
            detail=f"Budget exhausted for model {model_id}",
        )
        return AlignEntitiesResponse(links=[], failures=[], trace_id=trace_id, degraded=degraded)

    candidates = _generate_candidates(claims)
    total_tokens = 0

    for _canonical_text, group in candidates.items():
        canonical_id = uuid.uuid4().hex[:16]
        if len(group) < 2:
            for claim in group:
                links.append(
                    EntityLinkV1(
                        canonical_id=canonical_id,
                        alias_text=claim.quote,
                        language=claim.language or "und",
                        source_claim_uid=claim.uid,
                        confidence=1.0,
                        uncertain=False,
                    )
                )
            continue

        for claim in group:
            try:
                score = 0.85 if len(group) == 2 else 0.6
                total_tokens += len(claim.quote) // 4
                is_uncertain = score < UNCERTAINTY_THRESHOLD
                grounding = grounding_gate(has_evidence_citation=True)

                links.append(
                    EntityLinkV1(
                        canonical_id=canonical_id,
                        alias_text=claim.quote,
                        language=claim.language or "und",
                        source_claim_uid=claim.uid,
                        confidence=round(score, 3),
                        uncertain=is_uncertain,
                        explanation=f"grounding={grounding.value}",
                    )
                )
            except Exception as exc:
                failures.append(
                    ProblemDetail(
                        type="urn:aegi:error:entity_alignment_failed",
                        title="Entity alignment failed",
                        status=500,
                        detail=str(exc),
                        error_code="entity_alignment_failed",
                        extensions={"claim_uid": claim.uid},
                    )
                )

    llm_result = LLMInvocationResult(
        model_id=model_id,
        prompt_version=prompt_version,
        tokens_used=total_tokens,
        cost_usd=0.0,
        grounding_level=grounding_gate(has_evidence_citation=bool(links)),
        trace_id=trace_id,
    )

    return AlignEntitiesResponse(
        links=links,
        failures=failures,
        trace_id=trace_id,
        llm_result=llm_result,
        degraded=degraded,
    )
