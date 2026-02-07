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

import re
from typing import TYPE_CHECKING

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


class EvidenceCitation(BaseModel):
    source_claim_uid: str
    quote: str = ""
    evidence_uid: str = ""
    artifact_version_uid: str = ""


class AnswerV1(BaseModel):
    answer_text: str
    answer_type: GroundingLevel
    evidence_citations: list[EvidenceCitation] = Field(default_factory=list)
    trace_id: str
    cannot_answer_reason: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)


GROUNDED_QA_PROMPT = (
    "你是一位防务与地缘政治情报分析师。基于以下编号证据回答用户问题。\n"
    "规则：\n"
    "- 必须用 [N] 格式内联引用证据编号\n"
    "- 不得编造证据中没有的信息\n"
    "- 若证据不足以回答，明确说明\n\n"
    "证据：\n{evidence_context}\n\n"
    "问题：{question}\n"
)

PROMPT_VERSION = "grounded_qa_v1"


def format_evidence_context(
    citations: list[EvidenceCitation],
) -> tuple[str, dict[int, EvidenceCitation]]:
    """将 citations 格式化为编号证据上下文。

    Returns:
        (formatted_string, index_to_citation_mapping)
        索引从 1 开始。
    """
    index_map: dict[int, EvidenceCitation] = {}
    lines: list[str] = []
    for i, c in enumerate(citations, 1):
        index_map[i] = c
        lines.append(f"[{i}] {c.quote}")
    return "\n".join(lines), index_map


def _extract_cited_indices(text: str) -> set[int]:
    """从回答文本中提取 [N] 引用编号。"""
    return {int(m) for m in re.findall(r"\[(\d+)\]", text)}


async def generate_grounded_answer(
    question: str,
    evidence_context: str,
    index_map: dict[int, EvidenceCitation],
    llm: "LLMClient",
    trace_id: str,
) -> AnswerV1:
    """调用 LLM 生成 grounded 回答，提取引用，执行 hallucination gate。"""
    prompt = GROUNDED_QA_PROMPT.format(
        evidence_context=evidence_context,
        question=question,
    )
    result = await llm.invoke(prompt)
    answer_text = result["text"].strip()

    # 提取实际引用的编号，映射回 EvidenceCitation
    cited_indices = _extract_cited_indices(answer_text)
    cited_citations = [index_map[i] for i in sorted(cited_indices) if i in index_map]

    has_citations = len(cited_citations) > 0
    requested_type = GroundingLevel.FACT if has_citations else GroundingLevel.HYPOTHESIS

    return render_answer(
        answer_text=answer_text,
        requested_type=requested_type,
        evidence_citations=cited_citations,
        trace_id=trace_id,
    )


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
