# Author: msq
"""AnalysisMemory service tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db.models.analysis_memory import AnalysisMemoryRecord
from aegi_core.db.models.case import Case
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.services.analysis_memory import AnalysisMemory


class _FakeLLM:
    async def embed(self, text: str) -> list[float]:
        return [float(len(text) % 7), 0.1, 0.2]

    async def invoke_structured(self, _prompt, response_model, **_kwargs):
        return response_model(
            scenario_summary="Scenario: military escalation signals",
            conclusion="Escalation likely in 72 hours",
            pattern_tags=["military_buildup", "diplomatic_withdrawal"],
        )


@dataclass
class _Hit:
    chunk_uid: str
    text: str
    score: float
    metadata: dict


class _FakeQdrant:
    def __init__(self) -> None:
        self._points: dict[str, dict] = {}

    async def upsert(
        self,
        chunk_uid: str,
        embedding: list[float],
        text: str,
        metadata: dict | None = None,
    ) -> None:
        self._points[chunk_uid] = {
            "embedding": embedding,
            "text": text,
            "metadata": metadata or {},
        }

    async def search(
        self,
        _query_embedding: list[float],
        *,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[_Hit]:
        hits = []
        for uid, point in self._points.items():
            score = 0.92
            if score_threshold is not None and score < score_threshold:
                continue
            hits.append(
                _Hit(
                    chunk_uid=uid,
                    text=point["text"],
                    score=score,
                    metadata=point["metadata"],
                )
            )
        return hits[:limit]


@pytest.fixture(autouse=True)
def _jsonb_sqlite():
    original = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: self.visit_JSON(
        type_, **kw
    )
    yield
    if original:
        SQLiteTypeCompiler.visit_JSONB = original
    elif hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        delattr(SQLiteTypeCompiler, "visit_JSONB")


@pytest.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Case.__table__,
        Hypothesis.__table__,
        EvidenceAssessment.__table__,
        AnalysisMemoryRecord.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(
                lambda sync_conn, tbl=table: tbl.create(sync_conn, checkfirst=True)
            )
    yield engine
    await engine.dispose()


async def _seed_case(session: AsyncSession, case_uid: str) -> None:
    session.add(Case(uid=case_uid, title="Memory Test Case"))
    session.add(
        Hypothesis(
            uid="hyp_1",
            case_uid=case_uid,
            label="Escalation near border",
            prior_probability=0.5,
            posterior_probability=0.78,
            confidence=0.74,
        )
    )
    session.add(
        Hypothesis(
            uid="hyp_2",
            case_uid=case_uid,
            label="Diplomatic de-escalation",
            prior_probability=0.5,
            posterior_probability=0.22,
            confidence=0.35,
        )
    )
    now = datetime.now(timezone.utc)
    session.add(
        EvidenceAssessment(
            uid="ea_1",
            case_uid=case_uid,
            hypothesis_uid="hyp_1",
            evidence_uid="sc_1",
            evidence_type="source_claim",
            relation="support",
            strength=0.9,
            likelihood=0.9,
            assessed_by="llm",
            created_at=now,
        )
    )
    session.add(
        EvidenceAssessment(
            uid="ea_2",
            case_uid=case_uid,
            hypothesis_uid="hyp_2",
            evidence_uid="sc_2",
            evidence_type="source_claim",
            relation="contradict",
            strength=0.7,
            likelihood=0.2,
            assessed_by="llm",
            created_at=now,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_record_and_recall(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await _seed_case(session, "case_mem")
        service = AnalysisMemory(session, qdrant=_FakeQdrant(), llm=_FakeLLM())

        entry = await service.record("case_mem")
        assert entry.case_uid == "case_mem"
        assert entry.scenario_summary
        assert "military_buildup" in entry.pattern_tags

        recalled = await service.recall("military escalation", top_k=3)
        assert len(recalled) >= 1
        assert recalled[0].uid == entry.uid


@pytest.mark.asyncio
async def test_update_outcome_and_pattern_stats(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await _seed_case(session, "case_stats")
        service = AnalysisMemory(session, qdrant=_FakeQdrant(), llm=_FakeLLM())
        entry = await service.record("case_stats")

        updated = await service.update_outcome(
            entry.uid,
            outcome="confirmed_escalation",
            accuracy=0.82,
            lessons_learned="watch logistics signals",
        )
        assert updated.prediction_accuracy == pytest.approx(0.82)
        assert updated.outcome == "confirmed_escalation"

        stats = await service.get_pattern_stats("military_buildup")
        assert stats["count"] == 1
        assert stats["avg_accuracy"] == pytest.approx(0.82)
        assert stats["recent_case"]["uid"] == entry.uid


@pytest.mark.asyncio
async def test_enhance_analysis_returns_hints(db_engine):
    qdrant = _FakeQdrant()
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await _seed_case(session, "case_hint")
        service = AnalysisMemory(session, qdrant=qdrant, llm=_FakeLLM())
        entry = await service.record("case_hint")
        await service.update_outcome(entry.uid, outcome="confirmed", accuracy=0.75)

        hints = await service.enhance_analysis(
            "case_new",
            current_hypotheses=[
                {"label": "Escalation near border", "posterior_probability": 0.6}
            ],
        )
        assert hints["similar_cases"]
        assert "confirmed" in hints["outcome_distribution"]
        assert hints["recommended_evidence_types"]
