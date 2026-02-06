# Author: msq
"""Tests for claim extraction pipeline.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (4.3)
Evidence:
  - extract_from_chunk MUST return SourceClaimV1[] with valid selectors.
  - Empty selectors MUST be rejected (design.md LLM Strategy #3).
  - claim_grounding_rate >= 0.97 (design.md Acceptance #1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegi_core.contracts.llm_governance import BudgetContext, DegradedOutput, LLMInvocationResult
from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.services.claim_extractor import extract_from_chunk

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"


class FakeLLM:
    """Fake LLM that returns claims from fixture data."""

    def __init__(self, claims: list[dict]) -> None:
        self._claims = claims

    async def invoke(self, request: object, prompt: str) -> list[dict]:
        return self._claims


class FakeLLMWithInvalid:
    """Fake LLM that returns some claims with empty selectors."""

    def __init__(self, valid: list[dict], invalid_count: int = 1) -> None:
        self._valid = valid
        self._invalid_count = invalid_count

    async def invoke(self, request: object, prompt: str) -> list[dict]:
        invalid = [
            {"uid": f"bad_{i}", "quote": "no selectors", "selectors": []}
            for i in range(self._invalid_count)
        ]
        return self._valid + invalid


class FailingLLM:
    """Fake LLM that raises an exception."""

    async def invoke(self, request: object, prompt: str) -> list[dict]:
        raise RuntimeError("model unavailable")


def _load_fixture(name: str) -> dict:
    fixture_dir = FIXTURES / name
    chunks = json.loads((fixture_dir / "chunks.json").read_text())
    source_claims = json.loads((fixture_dir / "source_claims.json").read_text())
    return {"chunks": chunks["chunks"], "source_claims": source_claims["source_claims"]}


@pytest.mark.asyncio
async def test_extract_normal_scenario() -> None:
    """defgeo-claim-001: normal extraction produces valid claims with selectors."""
    fixture = _load_fixture("defgeo-claim-001")
    chunk = fixture["chunks"][0]
    expected_claims = fixture["source_claims"]

    llm_output = [
        {
            "uid": sc["source_claim_uid"],
            "quote": sc["quote"],
            "selectors": sc["selectors"],
            "attributed_to": sc.get("attributed_to"),
        }
        for sc in expected_claims
    ]

    claims, action, tool_trace, llm_result = await extract_from_chunk(
        chunk_uid=chunk["chunk_uid"],
        chunk_text=chunk.get("text", ""),
        anchor_set=chunk["anchor_set"],
        artifact_version_uid="av_test_001",
        evidence_uid="ev_test_001",
        case_uid="case_test_001",
        llm=FakeLLM(llm_output),
        budget=BudgetContext(max_tokens=4096, max_cost_usd=0.10),
    )

    assert len(claims) == len(expected_claims)
    for claim in claims:
        assert isinstance(claim, SourceClaimV1)
        assert len(claim.selectors) > 0, "selectors must not be empty"
        assert claim.quote != ""
        assert claim.evidence_uid == "ev_test_001"

    assert action.action_type == "claim_extract"
    assert action.trace_id is not None
    assert tool_trace.status == "ok"
    assert isinstance(llm_result, LLMInvocationResult)


@pytest.mark.asyncio
async def test_extract_rejects_empty_selectors() -> None:
    """Claims with empty selectors MUST be rejected (task 1.2)."""
    fixture = _load_fixture("defgeo-claim-001")
    chunk = fixture["chunks"][0]
    valid_claim = {
        "uid": "sc_valid",
        "quote": "valid quote",
        "selectors": [{"type": "TextQuoteSelector", "exact": "valid quote"}],
    }

    claims, action, tool_trace, llm_result = await extract_from_chunk(
        chunk_uid=chunk["chunk_uid"],
        chunk_text=chunk.get("text", ""),
        anchor_set=chunk["anchor_set"],
        artifact_version_uid="av_test_001",
        evidence_uid="ev_test_001",
        case_uid="case_test_001",
        llm=FakeLLMWithInvalid([valid_claim], invalid_count=2),
        budget=BudgetContext(max_tokens=4096, max_cost_usd=0.10),
    )

    assert len(claims) == 1
    assert claims[0].uid == "sc_valid"
    assert "rejected 2" in action.rationale


@pytest.mark.asyncio
async def test_extract_llm_failure_returns_degraded() -> None:
    """LLM failure MUST return DegradedOutput, not raise."""
    claims, action, tool_trace, result = await extract_from_chunk(
        chunk_uid="chunk_fail",
        chunk_text="some text",
        anchor_set=[],
        artifact_version_uid="av_fail",
        evidence_uid="ev_fail",
        case_uid="case_fail",
        llm=FailingLLM(),
        budget=BudgetContext(max_tokens=4096, max_cost_usd=0.10),
    )

    assert claims == []
    assert isinstance(result, DegradedOutput)
    assert result.reason.value == "model_unavailable"
    assert tool_trace.status == "error"


@pytest.mark.asyncio
async def test_grounding_rate() -> None:
    """claim_grounding_rate >= 0.97 (Acceptance #1).

    With fixture defgeo-claim-001, all claims have valid selectors,
    so grounding rate = valid / total = 1.0 >= 0.97.
    """
    fixture = _load_fixture("defgeo-claim-001")
    all_claims: list[SourceClaimV1] = []

    for chunk in fixture["chunks"]:
        matching = [
            sc
            for sc in fixture["source_claims"]
            if any(sel.get("exact") in chunk.get("text", "") for sel in sc.get("selectors", []))
        ]
        if not matching:
            matching = fixture["source_claims"][:1]

        llm_output = [
            {
                "uid": sc["source_claim_uid"],
                "quote": sc["quote"],
                "selectors": sc["selectors"],
                "attributed_to": sc.get("attributed_to"),
            }
            for sc in matching
        ]

        claims, *_ = await extract_from_chunk(
            chunk_uid=chunk["chunk_uid"],
            chunk_text=chunk.get("text", ""),
            anchor_set=chunk["anchor_set"],
            artifact_version_uid="av_test",
            evidence_uid="ev_test",
            case_uid="case_test",
            llm=FakeLLM(llm_output),
            budget=BudgetContext(max_tokens=4096, max_cost_usd=0.10),
        )
        all_claims.extend(claims)

    grounded = sum(1 for c in all_claims if c.selectors)
    rate = grounded / len(all_claims) if all_claims else 0
    assert rate >= 0.97, f"claim_grounding_rate={rate} < 0.97"
