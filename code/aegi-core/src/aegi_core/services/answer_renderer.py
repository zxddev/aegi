# Author: msq
"""回答渲染：AnswerV1 + FACT/INFERENCE/HYPOTHESIS 分级 + hallucination gate。

Source: openspec/changes/conversational-analysis-evidence-qa/design.md
Evidence:
  - 输出 AnswerV1：answer_text, answer_type, evidence_citations[], trace_id
  - 无证据引用时 answer_type 不得为 FACT（hallucination gate）
  - 引用失效时输出 cannot_answer_reason
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate


class EvidenceCitation(BaseModel):
    source_claim_uid: str
    quote: str = ""
    evidence_uid: str = ""


class AnswerV1(BaseModel):
    answer_text: str
    answer_type: GroundingLevel
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
    trace_id: str
    cannot_answer_reason: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)


def render_answer(
    answer_text: str,
    requested_type: GroundingLevel,
    evidence_citations: list[EvidenceCitation],
    trace_id: str,
    *,
    follow_up_questions: list[str] | None = None,
) -> AnswerV1:
    """渲染回答，强制执行 hallucination gate。

    若 requested_type 为 FACT 但无有效证据引用，grounding_gate 会降级为 HYPOTHESIS。
    若完全无证据，返回 cannot_answer。
    """
    has_citations = len(evidence_citations) > 0
    max_allowed = grounding_gate(has_citations)

    # 降级逻辑：requested_type 不得超过 max_allowed
    level_order = [
        GroundingLevel.HYPOTHESIS,
        GroundingLevel.INFERENCE,
        GroundingLevel.FACT,
    ]
    req_idx = level_order.index(requested_type)
    max_idx = level_order.index(max_allowed)
    actual_type = level_order[min(req_idx, max_idx)]

    cannot_answer_reason: str | None = None
    if not has_citations:
        cannot_answer_reason = "evidence_insufficient"
        answer_text = ""
        actual_type = GroundingLevel.HYPOTHESIS

    return AnswerV1(
        answer_text=answer_text,
        answer_type=actual_type,
        evidence_citations=evidence_citations,
        trace_id=trace_id,
        cannot_answer_reason=cannot_answer_reason,
        follow_up_questions=follow_up_questions or [],
    )
