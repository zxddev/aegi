# Author: msq
"""Hallucination gate 测试。

Source: openspec/changes/conversational-analysis-evidence-qa/specs/conversational/spec.md
Evidence:
  - FACT answer without citations is blocked -> 降级为 HYPOTHESIS
  - 证据不足时返回 cannot_answer_reason
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.main import create_app
from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.db.base import Base
from aegi_core.services.answer_renderer import EvidenceCitation, render_answer
from aegi_core.settings import settings


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


# -- 单元测试：grounding_gate + render_answer ---------------------------------


def test_grounding_gate_blocks_fact_without_evidence() -> None:
    """grounding_gate(False) 返回 HYPOTHESIS，不允许 FACT。"""
    assert grounding_gate(False) == GroundingLevel.HYPOTHESIS
    assert grounding_gate(True) == GroundingLevel.FACT


def test_render_answer_downgrades_fact_without_citations() -> None:
    """请求 FACT 但无 citations -> 降级为 HYPOTHESIS + cannot_answer_reason。"""
    answer = render_answer(
        answer_text="Some claim",
        requested_type=GroundingLevel.FACT,
        evidence_citations=[],
        trace_id="test_trace",
    )
    assert answer.answer_type == GroundingLevel.HYPOTHESIS
    assert answer.cannot_answer_reason == "evidence_insufficient"
    assert answer.answer_text == ""


def test_render_answer_allows_fact_with_citations() -> None:
    """请求 FACT 且有 citations -> 保持 FACT。"""
    citation = EvidenceCitation(
        source_claim_uid="sc_001",
        quote="test quote",
        evidence_uid="ev_001",
    )
    answer = render_answer(
        answer_text="Factual answer",
        requested_type=GroundingLevel.FACT,
        evidence_citations=[citation],
        trace_id="test_trace",
    )
    assert answer.answer_type == GroundingLevel.FACT
    assert answer.cannot_answer_reason is None
    assert len(answer.evidence_citations) == 1


def test_render_answer_inference_without_citations_downgrades() -> None:
    """请求 INFERENCE 但无 citations -> 降级为 HYPOTHESIS。"""
    answer = render_answer(
        answer_text="Inferred",
        requested_type=GroundingLevel.INFERENCE,
        evidence_citations=[],
        trace_id="test_trace",
    )
    assert answer.answer_type == GroundingLevel.HYPOTHESIS
    assert answer.cannot_answer_reason == "evidence_insufficient"


# -- 集成测试：API 层 hallucination gate ---------------------------------------


def test_api_chat_no_evidence_returns_cannot_answer() -> None:
    """对空 case 提问 -> cannot_answer_reason 非空，answer_type != FACT。"""
    _ensure_tables()
    client = TestClient(create_app())

    created = client.post(
        "/cases",
        json={"title": "Empty case", "actor_id": "test"},
    )
    case_uid = created.json()["case_uid"]

    resp = client.post(
        f"/cases/{case_uid}/analysis/chat",
        json={"question": "What happened in the Arctic?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_type"] != "FACT"
    assert body["cannot_answer_reason"] == "evidence_insufficient"
    assert body["answer_text"] == ""
    assert body["evidence_citations"] == []
    assert "trace_id" in body
