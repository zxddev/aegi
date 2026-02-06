"""LLM governance contracts (Gate-0).

Source: openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
Evidence:
  - LLM calls MUST be governed by versioned policy (model_id, prompt_version, budget_context).
  - Ungrounded outputs MUST NOT be emitted as FACT.
  - Budget and failure paths MUST be deterministic.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# -- Grounding gate (task 2.2) -------------------------------------------------

class GroundingLevel(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


def grounding_gate(has_evidence_citation: bool) -> GroundingLevel:
    """Return the maximum allowed grounding level.

    If there is no verifiable evidence citation the output MUST NOT be FACT.
    """
    if has_evidence_citation:
        return GroundingLevel.FACT
    return GroundingLevel.HYPOTHESIS


# -- Budget context (used by LLMInvocationRequest) -----------------------------

class BudgetContext(BaseModel):
    max_tokens: int
    max_cost_usd: float
    remaining_tokens: Optional[int] = None
    remaining_cost_usd: Optional[float] = None


# -- LLM invocation request (task 2.1) -----------------------------------------

class LLMInvocationRequest(BaseModel):
    model_id: str
    prompt_version: str
    budget_context: BudgetContext
    trace_id: Optional[str] = None
    fallback_model_id: Optional[str] = None


# -- LLM invocation result -----------------------------------------------------

class LLMInvocationResult(BaseModel):
    model_id: str
    prompt_version: str
    tokens_used: int = 0
    cost_usd: float = 0.0
    grounding_level: GroundingLevel
    evidence_citation_uids: list[str] = Field(default_factory=list)
    trace_id: Optional[str] = None


# -- Degraded output (task 2.3) ------------------------------------------------

class DegradedReason(str, Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    MODEL_UNAVAILABLE = "model_unavailable"
    TIMEOUT = "timeout"


class DegradedOutput(BaseModel):
    reason: DegradedReason
    detail: str
    fallback_model_id: Optional[str] = None
    partial_result: Optional[dict] = None
