# Author: msq
"""Claim extraction service.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (1.1–1.3)
Evidence:
  - SourceClaim extraction MUST preserve quote selectors (spec.md).
  - Empty selectors MUST be rejected (design.md: LLM Strategy #3).
  - All LLM calls MUST use LLMInvocationRequest/BudgetContext (parallel-ai-execution-protocol.md §5.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.llm_governance import (
    BudgetContext,
    DegradedOutput,
    DegradedReason,
    LLMInvocationRequest,
    LLMInvocationResult,
    grounding_gate,
)
from aegi_core.contracts.schemas import Modality, SourceClaimV1


class LLMBackend(Protocol):
    """Protocol for LLM invocation (allows test injection)."""

    async def invoke(self, request: LLMInvocationRequest, prompt: str) -> list[dict]:
        """Return raw claim dicts extracted by the LLM."""
        ...


PROMPT_VERSION = "claim_extract_v1"


async def extract_from_chunk(
    *,
    chunk_uid: str,
    chunk_text: str,
    anchor_set: list[dict],
    artifact_version_uid: str,
    evidence_uid: str,
    case_uid: str,
    llm: LLMBackend,
    budget: BudgetContext,
    model_id: str = "default",
    trace_id: str | None = None,
) -> tuple[
    list[SourceClaimV1], ActionV1, ToolTraceV1, LLMInvocationResult | DegradedOutput
]:
    """Extract SourceClaimV1 instances from a single chunk.

    Args:
        chunk_uid: Unique identifier of the chunk.
        chunk_text: Raw text content of the chunk.
        anchor_set: Anchor selectors from the chunk.
        artifact_version_uid: Parent artifact version.
        evidence_uid: Evidence record this chunk belongs to.
        case_uid: Owning case.
        llm: LLM backend (injectable).
        budget: Token/cost budget for this invocation.
        model_id: Model identifier for governance.
        trace_id: Distributed trace id.

    Returns:
        Tuple of (claims, action, tool_trace, llm_result_or_degraded).

    Raises:
        Nothing – validation failures are returned as empty list with
        the action recording the rejection reason.
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

    prompt = (
        f"Extract factual claims from the following text. "
        f"For each claim return: quote, selectors (TextQuoteSelector with exact match), "
        f"attributed_to (if identifiable).\n\n"
        f"Text:\n{chunk_text}"
    )

    start_ms = _now_ms()
    try:
        raw_claims: list[dict] = await llm.invoke(invocation_req, prompt)
    except Exception as exc:
        duration = _now_ms() - start_ms
        degraded = DegradedOutput(
            reason=DegradedReason.MODEL_UNAVAILABLE,
            detail=str(exc),
        )
        action = ActionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_type="claim_extract",
            rationale=f"LLM call failed: {exc}",
            inputs={"chunk_uid": chunk_uid},
            outputs={"error": str(exc)},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_uid=action.uid,
            tool_name="llm_claim_extract",
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

    # 过滤：空 selectors 直接拒收 (task 1.2)
    valid_claims: list[SourceClaimV1] = []
    rejected_count = 0
    for raw in raw_claims:
        selectors = raw.get("selectors", [])
        if not selectors:
            rejected_count += 1
            continue
        claim = SourceClaimV1(
            uid=raw.get("uid", uuid.uuid4().hex),
            case_uid=case_uid,
            artifact_version_uid=artifact_version_uid,
            chunk_uid=chunk_uid,
            evidence_uid=evidence_uid,
            quote=raw.get("quote", ""),
            selectors=selectors,
            attributed_to=raw.get("attributed_to"),
            modality=Modality.TEXT,
            created_at=now,
        )
        valid_claims.append(claim)

    has_evidence = len(valid_claims) > 0
    grounding = grounding_gate(has_evidence)

    llm_result = LLMInvocationResult(
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        tokens_used=0,
        cost_usd=0.0,
        grounding_level=grounding,
        evidence_citation_uids=[c.evidence_uid for c in valid_claims],
        trace_id=_trace_id,
    )

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="claim_extract",
        rationale=f"Extracted {len(valid_claims)} claims, rejected {rejected_count} (empty selectors)",
        inputs={"chunk_uid": chunk_uid, "artifact_version_uid": artifact_version_uid},
        outputs={"source_claim_uids": [c.uid for c in valid_claims]},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="llm_claim_extract",
        request=invocation_req.model_dump(),
        response={"claim_count": len(valid_claims), "rejected": rejected_count},
        status="ok",
        duration_ms=duration,
        policy={"model_id": model_id, "prompt_version": PROMPT_VERSION},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return valid_claims, action, tool_trace, llm_result


def _now_ms() -> int:
    from time import monotonic_ns

    return monotonic_ns() // 1_000_000
