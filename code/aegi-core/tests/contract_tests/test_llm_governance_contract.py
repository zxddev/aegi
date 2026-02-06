# Author: msq
"""Contract tests for LLM governance (task 5.3).

Evidence: openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
  - LLM calls MUST be governed by versioned policy.
  - Ungrounded outputs MUST NOT be emitted as FACT.
  - Budget and failure paths MUST be deterministic.
"""

from aegi_core.contracts.llm_governance import (
    BudgetContext,
    DegradedOutput,
    DegradedReason,
    GroundingLevel,
    LLMInvocationRequest,
    LLMInvocationResult,
    grounding_gate,
)


# -- Grounding gate (task 2.2) -------------------------------------------------


def test_grounding_gate_with_evidence_returns_fact():
    assert grounding_gate(True) == GroundingLevel.FACT


def test_grounding_gate_without_evidence_returns_hypothesis():
    assert grounding_gate(False) == GroundingLevel.HYPOTHESIS


def test_grounding_gate_no_fact_without_citation():
    """Ungrounded outputs MUST NOT be emitted as FACT."""
    level = grounding_gate(False)
    assert level != GroundingLevel.FACT


# -- LLMInvocationRequest (task 2.1) -------------------------------------------


def test_llm_invocation_request_fields():
    req = LLMInvocationRequest(
        model_id="gpt-4",
        prompt_version="v1.0",
        budget_context=BudgetContext(max_tokens=1000, max_cost_usd=0.05),
        trace_id="t-1",
    )
    assert req.model_id == "gpt-4"
    assert req.prompt_version == "v1.0"
    assert req.budget_context.max_tokens == 1000
    assert req.trace_id == "t-1"


# -- LLMInvocationResult -------------------------------------------------------


def test_llm_invocation_result_roundtrip():
    res = LLMInvocationResult(
        model_id="gpt-4",
        prompt_version="v1.0",
        tokens_used=500,
        cost_usd=0.02,
        grounding_level=GroundingLevel.FACT,
        evidence_citation_uids=["ev-1"],
        trace_id="t-1",
    )
    data = res.model_dump()
    res2 = LLMInvocationResult.model_validate(data)
    assert res2 == res


# -- Degraded output (task 2.3) ------------------------------------------------


def test_degraded_output_budget_exceeded():
    d = DegradedOutput(
        reason=DegradedReason.BUDGET_EXCEEDED,
        detail="token limit reached",
    )
    assert d.reason == DegradedReason.BUDGET_EXCEEDED
    assert d.partial_result is None


def test_degraded_output_model_unavailable():
    d = DegradedOutput(
        reason=DegradedReason.MODEL_UNAVAILABLE,
        detail="upstream timeout",
        fallback_model_id="gpt-3.5-turbo",
    )
    assert d.reason == DegradedReason.MODEL_UNAVAILABLE
    assert d.fallback_model_id == "gpt-3.5-turbo"


def test_degraded_output_timeout():
    d = DegradedOutput(
        reason=DegradedReason.TIMEOUT,
        detail="30s exceeded",
    )
    assert d.reason == DegradedReason.TIMEOUT


def test_degraded_reason_enum_values():
    assert set(DegradedReason) == {
        DegradedReason.BUDGET_EXCEEDED,
        DegradedReason.MODEL_UNAVAILABLE,
        DegradedReason.TIMEOUT,
    }
