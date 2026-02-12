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
    "You are a senior intelligence analyst. Your role is to synthesize evidence "
    "into clear, well-sourced assessments.\n"
    "Always cite evidence using [N] notation. Never make claims without evidence support.\n"
    "If evidence is insufficient, explicitly state the limitations.\n\n"
    "Rules:\n"
    "- You MUST inline-cite evidence numbers using [N] format\n"
    "- You MUST NOT fabricate information absent from the provided evidence\n"
    "- If the evidence is insufficient to answer, state this clearly\n\n"
    "Evidence:\n{evidence_context}\n\n"
    "Question: {question}\n"
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

    # 若 LLM 未使用 [N] 引用但有证据，回退：返回全部 citations
    if not cited_citations and index_map:
        cited_citations = list(index_map.values())

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
