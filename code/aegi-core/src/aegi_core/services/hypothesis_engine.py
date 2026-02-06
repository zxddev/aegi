# Author: msq
"""ACH hypothesis engine – support/contradict/gap analysis.

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (2.1, 2.3)
        openspec/changes/ach-hypothesis-analysis/design.md
Evidence:
  - 每个假设 MUST 输出支持证据、反证与缺口说明 (spec.md)
  - 输出覆盖率与冲突解释 (design.md: Decisions #2)
  - 所有 LLM 调用 MUST 使用 LLMInvocationRequest/BudgetContext
  - 无证据支持的结论 MUST 调用 grounding_gate(False) 强制降级
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.llm_governance import (
    BudgetContext,
    DegradedOutput,
    DegradedReason,
    GroundingLevel,
    LLMInvocationRequest,
    LLMInvocationResult,
    grounding_gate,
)
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1


class LLMBackend(Protocol):
    """Protocol for LLM invocation (allows test injection)."""

    async def invoke(self, request: LLMInvocationRequest, prompt: str) -> list[dict]: ...


PROMPT_VERSION = "ach_hypothesis_v1"


@dataclass
class ACHResult:
    """单个假设的 ACH 分析结果。"""

    hypothesis_text: str
    supporting_assertion_uids: list[str] = field(default_factory=list)
    contradicting_assertion_uids: list[str] = field(default_factory=list)
    coverage_score: float = 0.0
    confidence: float = 0.0
    gap_list: list[str] = field(default_factory=list)
    grounding_level: GroundingLevel = GroundingLevel.HYPOTHESIS


def _compute_coverage(
    supporting: list[str],
    contradicting: list[str],
    total_assertions: int,
) -> float:
    """覆盖率 = (支持 + 反证涉及的 assertion 数) / 总 assertion 数。"""
    if total_assertions == 0:
        return 0.0
    covered = len(set(supporting) | set(contradicting))
    return min(covered / total_assertions, 1.0)


def _compute_confidence(supporting: int, contradicting: int) -> float:
    """置信度 = 支持数 / (支持数 + 反证数)；无证据时为 0。"""
    total = supporting + contradicting
    if total == 0:
        return 0.0
    return supporting / total


def analyze_hypothesis(
    hypothesis_text: str,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
) -> ACHResult:
    """对单个假设执行支持/反证/缺口分析（纯规则，无 LLM）。

    Args:
        hypothesis_text: 假设文本。
        assertions: 可用 assertion 列表。
        source_claims: 可用 source claim 列表。

    Returns:
        ACHResult 包含支持/反证/缺口/覆盖率/置信度。
    """
    h_lower = hypothesis_text.lower()

    supporting: list[str] = []
    contradicting: list[str] = []

    for a in assertions:
        # 基于 assertion value 中的关键词匹配判断支持/反证
        val_str = str(a.value).lower()
        quote_texts = []
        for sc_uid in a.source_claim_uids:
            for sc in source_claims:
                if sc.uid == sc_uid:
                    quote_texts.append(sc.quote.lower())

        combined = val_str + " " + " ".join(quote_texts)

        deny_keywords = {"denied", "rejected", "refuted", "disputed", "contradicts", "against"}
        support_keywords = {"confirmed", "affirmed", "verified", "supports", "consistent"}

        has_deny = any(k in combined for k in deny_keywords)
        has_support = any(k in combined for k in support_keywords)

        # 如果 assertion 的 source_claim 引用文本与假设有词汇重叠，视为相关
        relevance = any(
            word in combined for word in h_lower.split() if len(word) > 3
        )

        if not relevance:
            continue

        if has_deny and not has_support:
            contradicting.append(a.uid)
        else:
            supporting.append(a.uid)

    # 缺口：没有被任何 supporting/contradicting 覆盖的 assertion
    covered = set(supporting) | set(contradicting)
    gap_list = [
        f"assertion {a.uid} not evaluated"
        for a in assertions
        if a.uid not in covered
    ]

    coverage = _compute_coverage(supporting, contradicting, len(assertions))
    confidence = _compute_confidence(len(supporting), len(contradicting))

    has_evidence = len(supporting) > 0
    grounding = grounding_gate(has_evidence)

    return ACHResult(
        hypothesis_text=hypothesis_text,
        supporting_assertion_uids=supporting,
        contradicting_assertion_uids=contradicting,
        coverage_score=coverage,
        confidence=confidence,
        gap_list=gap_list,
        grounding_level=grounding,
    )


async def generate_hypotheses(
    *,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
    case_uid: str,
    llm: LLMBackend,
    budget: BudgetContext,
    model_id: str = "default",
    trace_id: str | None = None,
    context: dict | None = None,
) -> tuple[list[ACHResult], ActionV1, ToolTraceV1, LLMInvocationResult | DegradedOutput]:
    """生成假设并执行 ACH 分析。

    Args:
        assertions: 输入 assertion 列表。
        source_claims: 输入 source claim 列表。
        case_uid: 所属 case。
        llm: LLM 后端（可注入）。
        budget: Token/cost 预算。
        model_id: 模型标识。
        trace_id: 分布式追踪 ID。
        context: 可选上下文（时间窗、地域）。

    Returns:
        Tuple of (ach_results, action, tool_trace, llm_result_or_degraded).
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    invocation_req = LLMInvocationRequest(
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        budget_context=budget,
        trace_id=_trace_id,
    )

    claims_summary = "; ".join(sc.quote[:80] for sc in source_claims[:10])
    prompt = (
        f"Given these evidence claims:\n{claims_summary}\n\n"
        f"Generate competing hypotheses that could explain the evidence. "
        f"Return a JSON list of objects with 'hypothesis_text' field."
    )

    start_ms = _now_ms()
    try:
        raw: list[dict] = await llm.invoke(invocation_req, prompt)
    except Exception as exc:
        duration = _now_ms() - start_ms
        degraded = DegradedOutput(
            reason=DegradedReason.MODEL_UNAVAILABLE, detail=str(exc)
        )
        action = ActionV1(
            uid=uuid.uuid4().hex, case_uid=case_uid, action_type="ach_generate",
            rationale=f"LLM call failed: {exc}",
            inputs={"assertion_count": len(assertions)},
            outputs={"error": str(exc)},
            trace_id=_trace_id, span_id=_span_id, created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex, case_uid=case_uid, action_uid=action.uid,
            tool_name="llm_ach_generate", request=invocation_req.model_dump(),
            response={"error": str(exc)}, status="error",
            duration_ms=duration, error=str(exc),
            policy={"model_id": model_id, "prompt_version": PROMPT_VERSION},
            trace_id=_trace_id, span_id=_span_id, created_at=now,
        )
        return [], action, tool_trace, degraded

    duration = _now_ms() - start_ms

    results: list[ACHResult] = []
    for item in raw:
        h_text = item.get("hypothesis_text", "")
        if not h_text:
            continue
        result = analyze_hypothesis(h_text, assertions, source_claims)
        results.append(result)

    all_supporting = [uid for r in results for uid in r.supporting_assertion_uids]
    has_evidence = len(all_supporting) > 0
    grounding = grounding_gate(has_evidence)

    llm_result = LLMInvocationResult(
        model_id=model_id, prompt_version=PROMPT_VERSION,
        tokens_used=0, cost_usd=0.0, grounding_level=grounding,
        evidence_citation_uids=[sc.uid for sc in source_claims],
        trace_id=_trace_id,
    )

    action = ActionV1(
        uid=uuid.uuid4().hex, case_uid=case_uid, action_type="ach_generate",
        rationale=f"Generated {len(results)} hypotheses from {len(assertions)} assertions",
        inputs={"assertion_count": len(assertions), "source_claim_count": len(source_claims)},
        outputs={"hypothesis_count": len(results)},
        trace_id=_trace_id, span_id=_span_id, created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex, case_uid=case_uid, action_uid=action.uid,
        tool_name="llm_ach_generate", request=invocation_req.model_dump(),
        response={"hypothesis_count": len(results)}, status="ok",
        duration_ms=duration,
        policy={"model_id": model_id, "prompt_version": PROMPT_VERSION},
        trace_id=_trace_id, span_id=_span_id, created_at=now,
    )

    return results, action, tool_trace, llm_result


def _now_ms() -> int:
    from time import monotonic_ns
    return monotonic_ns() // 1_000_000
