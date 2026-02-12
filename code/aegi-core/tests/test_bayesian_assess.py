"""贝叶斯证据评估测试 — 3 个测试，mock LLM。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db.base import Base
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.probability_update import ProbabilityUpdate
from aegi_core.services.bayesian_ach import (
    BayesianACH,
    EvidenceAssessmentRequest,
    EvidenceJudgment,
)


@pytest.fixture()
async def db_session():
    """内存 SQLite 异步 session — JSONB 渲染为 JSON (TEXT)。"""
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import JSON

    # 让 JSONB 在 SQLite 上编译为 JSON
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    _orig = (
        SQLiteTypeCompiler.visit_JSONB
        if hasattr(SQLiteTypeCompiler, "visit_JSONB")
        else None
    )

    def _visit_jsonb(self, type_, **kw):
        return self.visit_JSON(type_, **kw)

    SQLiteTypeCompiler.visit_JSONB = _visit_jsonb

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from aegi_core.db.models.case import Case

    tables = [
        Case.__table__,
        Hypothesis.__table__,
        EvidenceAssessment.__table__,
        ProbabilityUpdate.__table__,
    ]

    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(
                lambda sync_conn, t=table: t.create(sync_conn, checkfirst=True)
            )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()

    # 恢复
    if _orig:
        SQLiteTypeCompiler.visit_JSONB = _orig
    elif hasattr(SQLiteTypeCompiler, "visit_JSONB"):
        delattr(SQLiteTypeCompiler, "visit_JSONB")


def _make_mock_llm(judgments: list[EvidenceJudgment]) -> MagicMock:
    llm = MagicMock()
    llm.invoke_structured = AsyncMock(
        return_value=EvidenceAssessmentRequest(judgments=judgments)
    )
    return llm


async def _seed_case_and_hyps(session: AsyncSession, case_uid: str, hyp_count: int = 3):
    """插入 case + 假设，返回假设 uid 列表。"""
    from aegi_core.db.models.case import Case

    session.add(Case(uid=case_uid, title="test case"))
    uids = []
    for i in range(hyp_count):
        uid = f"hyp_{uuid4().hex[:8]}"
        session.add(
            Hypothesis(
                uid=uid,
                case_uid=case_uid,
                label=f"Hypothesis {i}",
                prior_probability=1.0 / hyp_count,
                posterior_probability=1.0 / hyp_count,
            )
        )
        uids.append(uid)
    await session.flush()
    return uids


@pytest.mark.asyncio
async def test_assess_evidence_creates_records(db_session):
    """assess_evidence() 为每个假设创建一条 EvidenceAssessment。"""
    case_uid = "case_test1"
    uids = await _seed_case_and_hyps(db_session, case_uid, 3)

    judgments = [
        EvidenceJudgment(hypothesis_uid=uids[0], relation="support", strength=0.8),
        EvidenceJudgment(hypothesis_uid=uids[1], relation="contradict", strength=0.6),
        EvidenceJudgment(hypothesis_uid=uids[2], relation="irrelevant", strength=0.5),
    ]
    llm = _make_mock_llm(judgments)
    engine = BayesianACH(db_session, llm)

    results = await engine.assess_evidence(case_uid, "ev_001", "some evidence text")
    assert len(results) == 3

    rows = (
        (
            await db_session.execute(
                sa.select(EvidenceAssessment).where(
                    EvidenceAssessment.case_uid == case_uid
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_assess_evidence_idempotent(db_session):
    """同一 evidence_uid 评估两次 → 不产生重复记录（upsert）。"""
    case_uid = "case_test2"
    uids = await _seed_case_and_hyps(db_session, case_uid, 2)

    judgments = [
        EvidenceJudgment(hypothesis_uid=uids[0], relation="support", strength=0.7),
        EvidenceJudgment(hypothesis_uid=uids[1], relation="irrelevant", strength=0.5),
    ]
    llm = _make_mock_llm(judgments)
    engine = BayesianACH(db_session, llm)

    await engine.assess_evidence(case_uid, "ev_dup", "text")
    await engine.assess_evidence(case_uid, "ev_dup", "text again")

    rows = (
        (
            await db_session.execute(
                sa.select(EvidenceAssessment).where(
                    EvidenceAssessment.case_uid == case_uid,
                    EvidenceAssessment.evidence_uid == "ev_dup",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2  # 每个假设一条，不重复


@pytest.mark.asyncio
async def test_assess_evidence_llm_failure_graceful(db_session):
    """LLM 失败 → 返回空列表，不崩溃。"""
    case_uid = "case_test3"
    await _seed_case_and_hyps(db_session, case_uid, 2)

    llm = MagicMock()
    llm.invoke_structured = AsyncMock(side_effect=RuntimeError("LLM down"))
    engine = BayesianACH(db_session, llm)

    results = await engine.assess_evidence(case_uid, "ev_fail", "text")
    assert results == []
