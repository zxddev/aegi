# Author: msq
"""ACH 假设引擎 — 支持/反驳/缺口分析。

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (2.1, 2.3)
        openspec/changes/ach-hypothesis-analysis/design.md
Evidence:
  - 每个假设 MUST 输出支持证据、反证与缺口说明 (spec.md)
  - 输出覆盖率与冲突解释 (design.md: Decisions #2)
  - 所有 LLM 调用 MUST 使用 LLMInvocationRequest/BudgetContext
  - 无证据支持的结论 MUST 调用 grounding_gate(False) 强制降级
"""

from __future__ import annotations

import json as _json
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel

from aegi_core.infra.llm_client import LLMClient

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
    """LLM 调用协议（允许测试注入）。"""

    async def invoke(
        self, request: LLMInvocationRequest, prompt: str
    ) -> list[dict]: ...


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


# ── LLM structured output ACH 分析 ──────────────────────────────


class AssertionJudgment(BaseModel):
    """LLM 对单个 assertion 与假设关系的判断。"""

    assertion_uid: str
    relation: Literal["support", "contradict", "irrelevant"]
    reason: str


class ACHAnalysisResult(BaseModel):
    """LLM ACH 分析的 structured output。"""

    hypothesis_text: str
    judgments: list[AssertionJudgment]


_ACH_SYSTEM_PROMPT = """\
你是一名情报分析师，执行 ACH（竞争性假设分析）。
给定一个假设和一组情报断言（assertions），对每个 assertion 判断：
- support：该 assertion 支持假设
- contradict：该 assertion 反驳假设
- irrelevant：该 assertion 与假设无关

返回严格 JSON，schema 如下：
{schema}
"""


def _build_ach_prompt(
    hypothesis_text: str,
    assertions: list[AssertionV1],
) -> str:
    """构建 ACH 分析 prompt。"""
    schema = ACHAnalysisResult.model_json_schema()
    system = _ACH_SYSTEM_PROMPT.format(schema=_json.dumps(schema, ensure_ascii=False))
    evidence = "\n".join(f"- uid={a.uid}: {a.value}" for a in assertions[:30])
    return (
        f"{system}\n\n"
        f"假设：{hypothesis_text}\n\n"
        f"Assertions:\n{evidence}\n\n"
        f"请返回 JSON："
    )


def _parse_ach_result(text: str) -> ACHAnalysisResult:
    """从 LLM 输出解析 ACHAnalysisResult。"""
    text = text.strip()
    if "```" in text:
        for block in text.split("```"):
            block = block.strip().removeprefix("json").strip()
            if block.startswith("{"):
                text = block
                break
    return ACHAnalysisResult.model_validate_json(text)


async def analyze_hypothesis_llm(
    hypothesis_text: str,
    assertions: list[AssertionV1],
    *,
    llm: LLMClient,
) -> ACHResult:
    """用 LLM structured output 执行 ACH 分析。

    Args:
        hypothesis_text: 假设文本。
        assertions: 可用 assertion 列表。
        llm: LLM 客户端。

    Returns:
        ACHResult，judgments 来自 LLM。
    """
    if not assertions:
        return ACHResult(
            hypothesis_text=hypothesis_text,
            grounding_level=grounding_gate(False),
        )

    prompt = _build_ach_prompt(hypothesis_text, assertions)
    try:
        parsed = await llm.invoke_structured(
            prompt,
            ACHAnalysisResult,
            max_tokens=4096,
            max_retries=2,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "ACH structured output failed for hypothesis %r, returning degraded result",
            hypothesis_text[:60],
            exc_info=True,
            extra={"degraded": True, "component": "hypothesis_engine"},
        )
        return ACHResult(
            hypothesis_text=hypothesis_text,
            grounding_level=grounding_gate(False),
        )

    # 从 judgments 计算 supporting/contradicting/gap
    uid_set = {a.uid for a in assertions}
    supporting = [
        j.assertion_uid
        for j in parsed.judgments
        if j.relation == "support" and j.assertion_uid in uid_set
    ]
    contradicting = [
        j.assertion_uid
        for j in parsed.judgments
        if j.relation == "contradict" and j.assertion_uid in uid_set
    ]
    judged = {j.assertion_uid for j in parsed.judgments}
    gap_list = [
        f"assertion {a.uid} not evaluated" for a in assertions if a.uid not in judged
    ]

    coverage = _compute_coverage(supporting, contradicting, len(assertions))
    confidence = _compute_confidence(len(supporting), len(contradicting))
    grounding = grounding_gate(len(supporting) > 0)

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
    llm: LLMClient,
    budget: BudgetContext,
    model_id: str = "default",
    trace_id: str | None = None,
    context: dict | None = None,
    llm_client: LLMClient | None = None,
) -> tuple[
    list[ACHResult], ActionV1, ToolTraceV1, LLMInvocationResult | DegradedOutput
]:
    """用 LLM 生成假设并执行 ACH 分析。

    Args:
        assertions: 输入 assertion 列表。
        source_claims: 输入 source claim 列表。
        case_uid: 所属 case。
        llm: LLM 客户端。
        budget: Token/cost 预算。
        model_id: 模型标识。
        trace_id: 分布式追踪 ID。
        context: 可选上下文。
        llm_client: 用于 ACH 分析的 LLM 客户端（默认复用 llm）。

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
        raw: list[dict] = await llm.invoke_as_backend(invocation_req, prompt)
    except Exception as exc:
        duration = _now_ms() - start_ms
        degraded = DegradedOutput(
            reason=DegradedReason.MODEL_UNAVAILABLE, detail=str(exc)
        )
        action = ActionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_type="ach_generate",
            rationale=f"LLM call failed: {exc}",
            inputs={"assertion_count": len(assertions)},
            outputs={"error": str(exc)},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_uid=action.uid,
            tool_name="llm_ach_generate",
            request=invocation_req.model_dump(),
            response={"error": str(exc)},
            status="error",
            duration_ms=duration,
            error=str(exc),
            policy={"model_id": model_id, "prompt_version": PROMPT_VERSION},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        return [], action, tool_trace, degraded

    duration = _now_ms() - start_ms

    _llm_client = llm_client or llm
    results: list[ACHResult] = []
    for item in raw:
        h_text = item.get("hypothesis_text", "")
        if not h_text:
            continue
        result = await analyze_hypothesis_llm(h_text, assertions, llm=_llm_client)
        results.append(result)

    all_supporting = [uid for r in results for uid in r.supporting_assertion_uids]
    has_evidence = len(all_supporting) > 0
    grounding = grounding_gate(has_evidence)

    llm_result = LLMInvocationResult(
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        tokens_used=0,
        cost_usd=0.0,
        grounding_level=grounding,
        evidence_citation_uids=[sc.uid for sc in source_claims],
        trace_id=_trace_id,
    )

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="ach_generate",
        rationale=f"Generated {len(results)} hypotheses from {len(assertions)} assertions",
        inputs={
            "assertion_count": len(assertions),
            "source_claim_count": len(source_claims),
        },
        outputs={"hypothesis_count": len(results)},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="llm_ach_generate",
        request=invocation_req.model_dump(),
        response={"hypothesis_count": len(results)},
        status="ok",
        duration_ms=duration,
        policy={"model_id": model_id, "prompt_version": PROMPT_VERSION},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return results, action, tool_trace, llm_result


def _now_ms() -> int:
    from time import monotonic_ns

    return monotonic_ns() // 1_000_000
