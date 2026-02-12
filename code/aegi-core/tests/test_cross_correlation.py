# Author: msq
"""CrossCorrelationEngine tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db import session as db_session_module
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.gdelt_event import GdeltEvent
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.cross_correlation import (
    CrossCorrelationEngine,
    create_cross_correlation_handler,
)
from aegi_core.services.event_bus import AegiEvent, get_event_bus, reset_event_bus
from aegi_core.settings import settings


class _FakeLLM:
    async def embed(self, text: str) -> list[float]:
        return [float(len(text) % 5), 0.2]

    async def invoke_structured(self, _prompt, response_model, **_kwargs):
        if response_model.__name__ == "PatternEvaluation":
            return response_model(
                is_significant=True,
                description="Coordinated cross-event signal",
                score=0.83,
                suggested_hypothesis="Potential coordinated influence campaign",
            )
        raise AssertionError(f"Unexpected response model: {response_model}")


@dataclass
class _Hit:
    chunk_uid: str
    text: str
    score: float
    metadata: dict


class _FakeQdrant:
    def __init__(self, hits: list[_Hit]):
        self._hits = hits

    async def search(
        self,
        _embedding: list[float],
        *,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[_Hit]:
        out = []
        for hit in self._hits:
            if score_threshold is not None and hit.score < score_threshold:
                continue
            out.append(hit)
        return out[:limit]


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


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        Case.__table__,
        GdeltEvent.__table__,
        ArtifactIdentity.__table__,
        ArtifactVersion.__table__,
        Chunk.__table__,
        Evidence.__table__,
        SourceClaim.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(
                lambda sync_conn, tbl=table: tbl.create(sync_conn, checkfirst=True)
            )
    yield engine
    await engine.dispose()


async def _seed_case_with_gdelt(session: AsyncSession, case_uid: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    session.add(Case(uid=case_uid, title="Cross Correlation Case"))
    new_uid = "gd_new"
    old_uid = "gd_old"
    session.add(
        GdeltEvent(
            uid=new_uid,
            gdelt_id="g_new",
            case_uid=case_uid,
            title="Iran moves battalion near border",
            url="https://source-a.test/new",
            source_domain="source-a.test",
            language="en",
            published_at=now,
            actor1="Iran",
            actor2="Army",
            geo_country="IRN",
            goldstein_scale=-7.0,
            status="new",
            raw_data={},
        )
    )
    session.add(
        GdeltEvent(
            uid=old_uid,
            gdelt_id="g_old",
            case_uid=case_uid,
            title="Iran and USA diplomatic friction rises",
            url="https://source-b.test/old",
            source_domain="source-b.test",
            language="en",
            published_at=now - timedelta(hours=24),
            actor1="Iran",
            actor2="USA",
            geo_country="IRN",
            goldstein_scale=-2.0,
            status="new",
            raw_data={},
        )
    )
    await session.commit()
    return new_uid, old_uid


@pytest.mark.asyncio
async def test_detects_entity_and_spatiotemporal_patterns(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        new_uid, _ = await _seed_case_with_gdelt(session, "case_corr")
        engine = CrossCorrelationEngine(
            db_session=session,
            llm=_FakeLLM(),
            qdrant=None,
            neo4j=None,
        )
        patterns = await engine.analyze_batch("case_corr", [new_uid])

    types = {pattern.pattern_type for pattern in patterns}
    assert "entity_cooccurrence" in types
    assert "spatiotemporal" in types


@pytest.mark.asyncio
async def test_detects_semantic_pattern_from_qdrant_hits(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        session.add(Case(uid="case_sem", title="Semantic Correlation Case"))
        now = datetime.now(timezone.utc)
        session.add(
            GdeltEvent(
                uid="gd_sem_new",
                gdelt_id="g_sem_new",
                case_uid="case_sem",
                title="Border radar activity surge",
                url="https://same-domain.test/new",
                source_domain="same-domain.test",
                language="en",
                published_at=now,
                actor1="StateA",
                actor2="StateB",
                geo_country="AAA",
                status="new",
                raw_data={},
            )
        )
        session.add(
            ArtifactIdentity(
                uid="ai_sem",
                kind="url",
                canonical_url="https://other-domain.test/old",
            )
        )
        session.add(
            ArtifactVersion(
                uid="av_sem",
                artifact_identity_uid="ai_sem",
                case_uid="case_sem",
                source_meta={
                    "source_domain": "other-domain.test",
                    "url": "https://other-domain.test/old",
                },
            )
        )
        session.add(
            Chunk(
                uid="chunk_sem",
                artifact_version_uid="av_sem",
                text="Satellite imagery indicates military logistics",
                anchor_set=[],
                ordinal=0,
            )
        )
        session.add(
            Evidence(
                uid="ev_sem",
                case_uid="case_sem",
                artifact_version_uid="av_sem",
                chunk_uid="chunk_sem",
                kind="article",
            )
        )
        session.add(
            SourceClaim(
                uid="sc_sem",
                case_uid="case_sem",
                artifact_version_uid="av_sem",
                chunk_uid="chunk_sem",
                evidence_uid="ev_sem",
                quote="Satellite imagery indicates military logistics",
                selectors=[],
                attributed_to="other-domain.test",
                modality="alleged",
            )
        )
        await session.commit()

        engine = CrossCorrelationEngine(
            db_session=session,
            llm=_FakeLLM(),
            qdrant=_FakeQdrant(
                [
                    _Hit(
                        chunk_uid="chunk_sem",
                        text="Satellite imagery indicates military logistics",
                        score=0.91,
                        metadata={
                            "case_uid": "case_sem",
                            "source_domain": "other-domain.test",
                            "url": "https://other-domain.test/old",
                        },
                    )
                ]
            ),
            neo4j=None,
        )
        patterns = await engine.analyze_batch("case_sem", ["gd_sem_new"])

    assert any(pattern.pattern_type == "semantic" for pattern in patterns)


@pytest.mark.asyncio
async def test_handler_emits_pattern_discovered_event(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "cross_correlation_enabled", True)
    monkeypatch.setattr(settings, "cross_correlation_batch_size", 1)
    monkeypatch.setattr(settings, "cross_correlation_batch_window_seconds", 600)
    monkeypatch.setattr(settings, "cross_correlation_significance_threshold", 0.0)
    monkeypatch.setattr(settings, "analysis_memory_enabled", False)

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        new_uid, _ = await _seed_case_with_gdelt(session, "case_handler")

    original_engine = db_session_module._engine
    db_session_module._engine = db_engine
    try:
        bus = get_event_bus()
        captured: list[AegiEvent] = []

        async def _capture(event: AegiEvent) -> None:
            captured.append(event)

        handler = create_cross_correlation_handler(
            llm=_FakeLLM(),
            qdrant=None,
            neo4j=None,
        )
        bus.on("gdelt.event_detected", handler)
        bus.on("pattern.discovered", _capture)

        await bus.emit_and_wait(
            AegiEvent(
                event_type="gdelt.event_detected",
                case_uid="case_handler",
                payload={"gdelt_event_uid": new_uid},
            )
        )
    finally:
        db_session_module._engine = original_engine

    assert captured
    assert captured[0].event_type == "pattern.discovered"

