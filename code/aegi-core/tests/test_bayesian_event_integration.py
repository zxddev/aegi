"""贝叶斯事件驱动集成测试 — 5 个测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.probability_update import ProbabilityUpdate
from aegi_core.services.bayesian_ach import (
    BayesianACH,
    EvidenceAssessmentRequest,
    EvidenceJudgment,
    create_bayesian_update_handler,
)
from aegi_core.services.event_bus import AegiEvent, EventBus, reset_event_bus


@pytest.fixture(autouse=True)
def _jsonb_sqlite():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    _orig = getattr(SQLiteTypeCompiler, "visit_JSONB", None)
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: self.visit_JSON(
        type_, **kw
    )
    yield
    if _orig:
        SQLiteTypeCompiler.visit_JSONB = _orig
    elif hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        delattr(SQLiteTypeCompiler, "visit_JSONB")


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture()
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from aegi_core.db.models.case import Case
    from aegi_core.db.models.source_claim import SourceClaim
    from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
    from aegi_core.db.models.evidence import Evidence as EvidenceModel
    from aegi_core.db.models.chunk import Chunk

    tables = [
        Case.__table__,
        ArtifactIdentity.__table__,
        ArtifactVersion.__table__,
        EvidenceModel.__table__,
        Chunk.__table__,
        SourceClaim.__table__,
        Hypothesis.__table__,
        EvidenceAssessment.__table__,
        ProbabilityUpdate.__table__,
    ]
    async with engine.begin() as conn:
        for t in tables:
            await conn.run_sync(lambda sc, tbl=t: tbl.create(sc, checkfirst=True))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


async def _seed(session, case_uid="case_ev1", n=3):
    from aegi_core.db.models.case import Case

    session.add(Case(uid=case_uid, title="test"))
    uids = []
    for i in range(n):
        uid = f"hyp_{uuid4().hex[:8]}"
        session.add(
            Hypothesis(
                uid=uid,
                case_uid=case_uid,
                label=f"H{i}",
                prior_probability=1.0 / n,
                posterior_probability=1.0 / n,
            )
        )
        uids.append(uid)
    await session.flush()
    return uids


async def _seed_source_claim(session, case_uid, sc_uid, quote="test"):
    from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
    from aegi_core.db.models.evidence import Evidence as EvidenceModel
    from aegi_core.db.models.chunk import Chunk
    from aegi_core.db.models.source_claim import SourceClaim

    ai, av, ev, ch = [f"{p}_{uuid4().hex[:6]}" for p in ("ai", "av", "ev", "ch")]
    session.add(ArtifactIdentity(uid=ai, kind="doc"))
    await session.flush()
    session.add(ArtifactVersion(uid=av, artifact_identity_uid=ai, case_uid=case_uid))
    await session.flush()
    session.add(Chunk(uid=ch, artifact_version_uid=av, ordinal=0, text="t"))
    await session.flush()
    session.add(
        EvidenceModel(
            uid=ev,
            case_uid=case_uid,
            artifact_version_uid=av,
            chunk_uid=ch,
            kind="document",
        )
    )
    await session.flush()
    session.add(
        SourceClaim(
            uid=sc_uid,
            case_uid=case_uid,
            artifact_version_uid=av,
            chunk_uid=ch,
            evidence_uid=ev,
            quote=quote,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_claim_extracted_triggers_update(db_session):
    """评估 + 更新 → 后验正确变化。"""
    case_uid = "case_ev1"
    uids = await _seed(db_session, case_uid, 3)

    judgments = [
        EvidenceJudgment(hypothesis_uid=uids[0], relation="support", strength=0.8),
        EvidenceJudgment(hypothesis_uid=uids[1], relation="contradict", strength=0.6),
        EvidenceJudgment(hypothesis_uid=uids[2], relation="irrelevant", strength=0.5),
    ]
    mock_llm = MagicMock()
    mock_llm.invoke_structured = AsyncMock(
        return_value=EvidenceAssessmentRequest(judgments=judgments)
    )

    eng = BayesianACH(db_session, mock_llm)
    await eng.assess_evidence(case_uid, "sc1", "Iran resumes talks", "source_claim")
    result = await eng.update(case_uid, "sc1")

    assert result.posterior_distribution[uids[0]] > 1.0 / 3
    assert result.posterior_distribution[uids[1]] < 1.0 / 3
    assert abs(sum(result.posterior_distribution.values()) - 1.0) < 1e-10


@pytest.mark.asyncio
async def test_no_hypotheses_skips(db_session):
    """没有假设 → handler 直接返回，不调用 LLM。"""
    from aegi_core.db.models.case import Case

    db_session.add(Case(uid="case_empty", title="empty"))
    await db_session.flush()

    mock_llm = MagicMock()
    handler = create_bayesian_update_handler(llm=mock_llm)

    with patch("aegi_core.services.bayesian_ach.AsyncSession") as MS:
        MS.return_value.__aenter__ = AsyncMock(return_value=db_session)
        MS.return_value.__aexit__ = AsyncMock(return_value=False)
        await handler(
            AegiEvent(
                event_type="claim.extracted",
                case_uid="case_empty",
                payload={"claim_uids": ["sc_x"]},
            )
        )

    mock_llm.invoke_structured.assert_not_called()


@pytest.mark.asyncio
async def test_threshold_emits_hypothesis_updated(db_session):
    """变化 > 5% → 发出 hypothesis.updated 事件。"""
    case_uid = "case_thresh"
    uids = await _seed(db_session, case_uid, 2)
    await _seed_source_claim(db_session, case_uid, "sc_thresh", "Strong evidence")
    await db_session.commit()

    judgments = [
        EvidenceJudgment(hypothesis_uid=uids[0], relation="support", strength=0.95),
        EvidenceJudgment(hypothesis_uid=uids[1], relation="contradict", strength=0.8),
    ]
    mock_llm = MagicMock()
    mock_llm.invoke_structured = AsyncMock(
        return_value=EvidenceAssessmentRequest(judgments=judgments)
    )

    emitted: list[AegiEvent] = []

    async def capture_emit(self, event):
        emitted.append(event)

    handler = create_bayesian_update_handler(llm=mock_llm)
    with (
        patch("aegi_core.services.bayesian_ach.AsyncSession") as MS,
        patch.object(EventBus, "emit", capture_emit),
    ):
        MS.return_value.__aenter__ = AsyncMock(return_value=db_session)
        MS.return_value.__aexit__ = AsyncMock(return_value=False)
        await handler(
            AegiEvent(
                event_type="claim.extracted",
                case_uid=case_uid,
                payload={"claim_uids": ["sc_thresh"]},
            )
        )

    hyp_ev = [e for e in emitted if e.event_type == "hypothesis.updated"]
    assert len(hyp_ev) == 1
    assert hyp_ev[0].payload["max_change"] >= 0.05


@pytest.mark.asyncio
async def test_below_threshold_no_emit(db_session):
    """变化 < 5% → 不发出 hypothesis.updated。"""
    case_uid = "case_below"
    uids = await _seed(db_session, case_uid, 2)
    await _seed_source_claim(db_session, case_uid, "sc_below", "Weak evidence")
    await db_session.commit()

    judgments = [
        EvidenceJudgment(hypothesis_uid=uids[0], relation="support", strength=0.05),
        EvidenceJudgment(hypothesis_uid=uids[1], relation="irrelevant", strength=0.5),
    ]
    mock_llm = MagicMock()
    mock_llm.invoke_structured = AsyncMock(
        return_value=EvidenceAssessmentRequest(judgments=judgments)
    )

    emitted: list[AegiEvent] = []

    async def capture_emit(self, event):
        emitted.append(event)

    handler = create_bayesian_update_handler(llm=mock_llm)
    with (
        patch("aegi_core.services.bayesian_ach.AsyncSession") as MS,
        patch.object(EventBus, "emit", capture_emit),
    ):
        MS.return_value.__aenter__ = AsyncMock(return_value=db_session)
        MS.return_value.__aexit__ = AsyncMock(return_value=False)
        await handler(
            AegiEvent(
                event_type="claim.extracted",
                case_uid=case_uid,
                payload={"claim_uids": ["sc_below"]},
            )
        )

    assert not [e for e in emitted if e.event_type == "hypothesis.updated"]


@pytest.mark.asyncio
async def test_handler_ignores_non_claim_events():
    """非 claim.extracted 事件被忽略。"""
    mock_llm = MagicMock()
    handler = create_bayesian_update_handler(llm=mock_llm)
    await handler(AegiEvent(event_type="other", case_uid="x", payload={}))
    mock_llm.invoke_structured.assert_not_called()
