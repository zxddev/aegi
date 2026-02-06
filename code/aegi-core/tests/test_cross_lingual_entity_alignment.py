# Author: msq
"""Tests for cross-lingual entity alignment.

Source: openspec/changes/multilingual-evidence-chain/tasks.md (task 4.3)
Evidence:
  - 对齐输出必须可追溯到 source_claim_uid。
  - 低置信对齐结果 MUST 标记为 uncertain。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.services.entity_alignment import (
    AlignEntitiesResponse,
    EntityLinkV1,
    UNCERTAINTY_THRESHOLD,
    align_entities,
)


def _make_claim(uid: str, quote: str) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid="case-1",
        artifact_version_uid="av-1",
        chunk_uid="ch-1",
        evidence_uid="ev-1",
        quote=quote,
        created_at=datetime.now(timezone.utc),
    )


def _budget() -> BudgetContext:
    return BudgetContext(max_tokens=1000, max_cost_usd=1.0, remaining_cost_usd=1.0)


@pytest.mark.asyncio
async def test_align_single_claim() -> None:
    resp = await align_entities([_make_claim("c1", "unique entity")], _budget())
    assert isinstance(resp, AlignEntitiesResponse)
    assert len(resp.links) == 1
    assert resp.links[0].source_claim_uid == "c1"
    assert resp.links[0].confidence == 1.0
    assert resp.links[0].uncertain is False


@pytest.mark.asyncio
async def test_align_two_same_quotes() -> None:
    claims = [_make_claim("c1", "same entity"), _make_claim("c2", "same entity")]
    resp = await align_entities(claims, _budget())
    assert len(resp.links) == 2
    assert resp.links[0].canonical_id == resp.links[1].canonical_id


@pytest.mark.asyncio
async def test_align_different_quotes_not_merged() -> None:
    claims = [_make_claim("c1", "entity A"), _make_claim("c2", "entity B")]
    resp = await align_entities(claims, _budget())
    ids = {link.canonical_id for link in resp.links}
    assert len(ids) == 2


@pytest.mark.asyncio
async def test_align_ambiguous_marks_uncertain() -> None:
    """3+ 候选时置信度低于阈值，标记 uncertain。"""
    claims = [
        _make_claim("c1", "ambiguous name"),
        _make_claim("c2", "ambiguous name"),
        _make_claim("c3", "ambiguous name"),
    ]
    resp = await align_entities(claims, _budget())
    for link in resp.links:
        assert link.uncertain is True
        assert link.confidence < UNCERTAINTY_THRESHOLD


@pytest.mark.asyncio
async def test_align_evidence_traceability() -> None:
    """每个 EntityLinkV1 必须可追溯到 source_claim_uid。"""
    claims = [_make_claim("c1", "traced entity"), _make_claim("c2", "traced entity")]
    resp = await align_entities(claims, _budget())
    for link in resp.links:
        assert link.source_claim_uid in ("c1", "c2")
        assert link.canonical_id
        assert link.alias_text


@pytest.mark.asyncio
async def test_align_budget_exceeded() -> None:
    budget = BudgetContext(max_tokens=0, max_cost_usd=0.0, remaining_cost_usd=0.0)
    resp = await align_entities([_make_claim("c1", "entity")], budget)
    assert resp.degraded is not None
    assert resp.degraded.reason.value == "budget_exceeded"
    assert resp.links == []


@pytest.mark.asyncio
async def test_align_llm_audit_info() -> None:
    claims = [_make_claim("c1", "audit entity"), _make_claim("c2", "audit entity")]
    resp = await align_entities(claims, _budget())
    assert resp.llm_result is not None
    assert resp.llm_result.model_id
    assert resp.llm_result.trace_id == resp.trace_id


@pytest.mark.asyncio
async def test_entity_link_v1_fields() -> None:
    """验证 EntityLinkV1 最小字段完整性（design.md）。"""
    link = EntityLinkV1(
        canonical_id="can-1",
        alias_text="alias",
        language="zh",
        source_claim_uid="sc-1",
        confidence=0.9,
    )
    assert link.canonical_id == "can-1"
    assert link.language == "zh"
    assert link.source_claim_uid == "sc-1"
    assert link.uncertain is False
