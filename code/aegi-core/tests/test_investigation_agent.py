# Author: msq
"""Investigation agent unit/integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db import session as db_session_module
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.investigation import Investigation
from aegi_core.db.models.probability_update import ProbabilityUpdate
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.searxng_client import SearchResult
from aegi_core.services.bayesian_ach import (
    EvidenceAssessmentRequest,
    EvidenceJudgment,
    create_bayesian_update_handler,
)
from aegi_core.services.event_bus import AegiEvent, get_event_bus, reset_event_bus
from aegi_core.services.investigation_agent import (
    InvestigationAgent,
    InvestigationConfig,
    create_investigation_handler,
)
from aegi_core.settings import settings


class _FakeLLM:
    def __init__(self, hypothesis_uids: list[str]) -> None:
        self._hypothesis_uids = hypothesis_uids

    async def invoke_structured(self, _prompt, response_model, **_kwargs):
        if response_model.__name__ == "InvestigationQueryPlan":
            return response_model(
                queries=[
                    "Iran diplomacy latest evidence",
                    "Iran negotiation contradiction evidence",
                ]
            )
        if response_model is EvidenceAssessmentRequest:
            return EvidenceAssessmentRequest(
                judgments=[
                    EvidenceJudgment(
                        hypothesis_uid=self._hypothesis_uids[0],
                        relation="support",
                        strength=0.9,
                    ),
                    EvidenceJudgment(
                        hypothesis_uid=self._hypothesis_uids[1],
                        relation="contradict",
                        strength=0.7,
                    ),
                ]
            )
        raise AssertionError(f"Unexpected response model: {response_model}")


class _FakeSearxng:
    async def search(self, query: str, **_kwargs) -> list[SearchResult]:
        suffix = query.lower().replace(" ", "-")[:20]
        return [
            SearchResult(
                title=f"Report for {query}",
                url=f"https://example.com/{suffix}",
                snippet=f"evidence snippet for {query}",
                engine="duckduckgo",
            )
        ]


class _FakeGdelt:
    async def search_articles(self, *_args, **_kwargs) -> list[object]:
        return []


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
        ArtifactIdentity.__table__,
        ArtifactVersion.__table__,
        Chunk.__table__,
        Evidence.__table__,
        SourceClaim.__table__,
        Hypothesis.__table__,
        EvidenceAssessment.__table__,
        ProbabilityUpdate.__table__,
        Investigation.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(
                lambda sync_conn, tbl=table: tbl.create(sync_conn, checkfirst=True)
            )
    yield engine
    await engine.dispose()


async def _seed_case(engine, case_uid: str) -> list[str]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Case(uid=case_uid, title="Investigation Test Case"))
        h1 = f"hyp_{uuid4().hex[:8]}"
        h2 = f"hyp_{uuid4().hex[:8]}"
        session.add(
            Hypothesis(
                uid=h1,
                case_uid=case_uid,
                label="Scenario A",
                prior_probability=0.5,
                posterior_probability=0.5,
            )
        )
        session.add(
            Hypothesis(
                uid=h2,
                case_uid=case_uid,
                label="Scenario B",
                prior_probability=0.5,
                posterior_probability=0.5,
            )
        )
        await session.commit()
    return [h1, h2]


@pytest.mark.asyncio
async def test_investigation_agent_persists_rounds_and_claims(db_engine):
    case_uid = f"case_{uuid4().hex[:8]}"
    hypothesis_uids = await _seed_case(db_engine, case_uid)

    event = AegiEvent(
        event_type="hypothesis.updated",
        case_uid=case_uid,
        payload={"max_change": 0.2, "summary": "manual trigger"},
    )
    llm = _FakeLLM(hypothesis_uids)
    config = InvestigationConfig(
        max_rounds=1,
        min_posterior_diff=0.2,
        min_change_threshold=0.05,
        cooldown_seconds=0,
        max_concurrent_investigations=1,
        token_budget_per_round=2048,
        search_sources=["searxng"],
    )

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        agent = InvestigationAgent(
            session,
            llm=llm,
            searxng=_FakeSearxng(),
            gdelt_client=_FakeGdelt(),
            qdrant=None,
            config=config,
        )
        with patch.object(
            InvestigationAgent,
            "_notify_case_subscribers",
            new=AsyncMock(return_value=None),
        ):
            result = await agent.investigate(case_uid=case_uid, trigger_event=event)

    assert result.case_uid == case_uid
    assert result.total_claims > 0
    assert len(result.rounds) == 1

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        inv_count = (
            await session.execute(sa.select(sa.func.count()).select_from(Investigation))
        ).scalar_one()
        sc_count = (
            await session.execute(sa.select(sa.func.count()).select_from(SourceClaim))
        ).scalar_one()
    assert inv_count == 1
    assert sc_count >= 1


@pytest.mark.asyncio
async def test_event_chain_hypothesis_updated_to_bayesian_update(
    db_engine, monkeypatch
):
    case_uid = f"case_{uuid4().hex[:8]}"
    hypothesis_uids = await _seed_case(db_engine, case_uid)
    llm = _FakeLLM(hypothesis_uids)

    monkeypatch.setattr(settings, "investigation_enabled", True)
    monkeypatch.setattr(settings, "investigation_max_rounds", 1)
    monkeypatch.setattr(settings, "investigation_min_posterior_diff", 0.2)
    monkeypatch.setattr(settings, "investigation_min_change_threshold", 0.05)
    monkeypatch.setattr(settings, "investigation_cooldown_seconds", 0)
    monkeypatch.setattr(settings, "investigation_max_concurrent", 1)
    monkeypatch.setattr(settings, "investigation_search_sources", "searxng")

    original_engine = db_session_module._engine
    db_session_module._engine = db_engine
    try:
        bus = get_event_bus()
        bus.on("claim.extracted", create_bayesian_update_handler(llm=llm))
        bus.on(
            "hypothesis.updated",
            create_investigation_handler(
                llm=llm,
                searxng=_FakeSearxng(),
                gdelt=_FakeGdelt(),
                qdrant=None,
            ),
        )

        event = AegiEvent(
            event_type="hypothesis.updated",
            case_uid=case_uid,
            payload={
                "max_change": 0.2,
                "summary": "trigger investigation",
                "updates": [],
            },
        )
        with patch.object(
            InvestigationAgent,
            "_notify_case_subscribers",
            new=AsyncMock(return_value=None),
        ):
            await bus.emit_and_wait(event)
    finally:
        db_session_module._engine = original_engine

    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        inv_status = (
            await session.execute(sa.select(Investigation.status))
        ).scalar_one()
        assessment_count = (
            await session.execute(
                sa.select(sa.func.count()).select_from(EvidenceAssessment)
            )
        ).scalar_one()
        prob_updates = (
            await session.execute(
                sa.select(sa.func.count()).select_from(ProbabilityUpdate)
            )
        ).scalar_one()

    assert inv_status == "completed"
    assert assessment_count > 0
    assert prob_updates > 0
