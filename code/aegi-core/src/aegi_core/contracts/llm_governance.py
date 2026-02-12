# Author: msq
"""LLM 治理契约 (Gate-0)。

来源: openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
约束:
  - LLM 调用必须受版本化策略管控 (model_id, prompt_version, budget_context)。
  - 无依据的输出不得标记为 FACT。
  - 预算和失败路径必须是确定性的。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# -- Grounding 门控 (task 2.2) -------------------------------------------------


class GroundingLevel(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


def grounding_gate(has_evidence_citation: bool) -> GroundingLevel:
    """返回允许的最高 grounding 级别。

    没有可验证的证据引用时，输出不得标记为 FACT。
    """
    if has_evidence_citation:
        return GroundingLevel.FACT
    return GroundingLevel.HYPOTHESIS


# -- 预算上下文 (LLMInvocationRequest 使用) -----------------------------


class BudgetContext(BaseModel):
    max_tokens: int
    max_cost_usd: float
    remaining_tokens: int | None = None
    remaining_cost_usd: float | None = None


# -- LLM 调用请求 (task 2.1) -----------------------------------------


class LLMInvocationRequest(BaseModel):
    model_id: str
    prompt_version: str
    budget_context: BudgetContext
    trace_id: str | None = None
    fallback_model_id: str | None = None


# -- LLM 调用结果 -----------------------------------------------------


class LLMInvocationResult(BaseModel):
    model_id: str
    prompt_version: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    grounding_level: GroundingLevel
    evidence_citation_uids: list[str] = Field(default_factory=list)
    trace_id: str | None = None


# -- 降级输出 (task 2.3) ------------------------------------------------


class DegradedReason(str, Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"


class DegradedOutput(BaseModel):
    reason: DegradedReason
    detail: str
    fallback_model_id: str | None = None
    partial_result: dict | None = None
