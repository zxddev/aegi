# Author: msq
"""QualityGate service tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from aegi_core.db.models.action import Action
from aegi_core.db.models.analysis_memory import AnalysisMemoryRecord
from aegi_core.db.models.case import Case
from aegi_core.db.models.entity_identity_action import EntityIdentityAction
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.relation_fact import RelationFact
from aegi_core.services.quality_gate import QualityGate, QualityMetrics


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
        Action.__table__,
        EntityIdentityAction.__table__,
        Hypothesis.__table__,
        EvidenceAssessment.__table__,
        RelationFact.__table__,
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
    now = datetime.now(timezone.utc)
    session.add(Case(uid=case_uid, title="Quality Case"))
    session.add(Action(uid="act_q", case_uid=case_uid, action_type="seed", trace_id="t"))
    session.add(
        EntityIdentityAction(
            uid="eid_1",
            case_uid=case_uid,
            action_type="merge",
            entity_uids=["ent_a", "ent_b"],
            result_entity_uid="ent_a",
            reason="duplicate",
            performed_by="llm",
            approved=True,
            approved_by="expert",
            status="approved",
            created_by_action_uid="act_q",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        EntityIdentityAction(
            uid="eid_2",
            case_uid=case_uid,
            action_type="merge",
            entity_uids=["ent_c", "ent_d"],
            result_entity_uid="ent_c",
            reason="possible duplicate",
            performed_by="llm",
            approved=False,
            status="pending",
            created_by_action_uid="act_q",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        Hypothesis(
            uid="hyp_q1",
            case_uid=case_uid,
            label="Hypothesis A",
            posterior_probability=0.7,
        )
    )
    session.add(
        Hypothesis(
            uid="hyp_q2",
            case_uid=case_uid,
            label="Hypothesis B",
            posterior_probability=0.3,
        )
    )
    session.add(
        EvidenceAssessment(
            uid="ea_q1",
            case_uid=case_uid,
            hypothesis_uid="hyp_q1",
            evidence_uid="ev1",
            evidence_type="source_claim",
            relation="support",
            strength=0.8,
            likelihood=0.9,
            assessed_by="llm",
            created_at=now,
        )
    )
    session.add(
        EvidenceAssessment(
            uid="ea_q2",
            case_uid=case_uid,
            hypothesis_uid="hyp_q2",
            evidence_uid="ev2",
            evidence_type="source_claim",
            relation="contradict",
            strength=0.7,
            likelihood=0.2,
            assessed_by="llm",
            created_at=now,
        )
    )
    session.add(
        RelationFact(
            uid="rf_q1",
            case_uid=case_uid,
            source_entity_uid="ent_a",
            target_entity_uid="ent_x",
            relation_type="HOSTILE_TO",
            supporting_source_claim_uids=["sc1"],
            evidence_strength=0.8,
            assessed_by="llm",
            conflicts_with=["rf_q2"],
            confidence=0.7,
            created_by_action_uid="act_q",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        RelationFact(
            uid="rf_q2",
            case_uid=case_uid,
            source_entity_uid="ent_a",
            target_entity_uid="ent_x",
            relation_type="ALLIED_WITH",
            supporting_source_claim_uids=["sc2"],
            evidence_strength=0.6,
            assessed_by="llm",
            conflicts_with=["rf_q1"],
            conflict_resolution="pending adjudication",
            confidence=0.4,
            created_by_action_uid="act_q",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        AnalysisMemoryRecord(
            uid="mem_q1",
            case_uid=case_uid,
            scenario_summary="Previous military posture analysis",
            hypotheses=[{"label": "Hypothesis A"}],
            key_evidence=[{"relation": "support"}],
            conclusion="Escalation likely",
            confidence=0.8,
            outcome="confirmed",
            prediction_accuracy=0.82,
            pattern_tags=["military_buildup"],
            created_at=now,
            updated_at=now,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_quality_gate_evaluate(db_engine):
    async with AsyncSession(db_engine, expire_on_commit=False) as session:
        await _seed_case(session, "case_quality")
        gate = QualityGate(session)
        metrics = await gate.evaluate("case_quality")

    assert metrics.entity_resolution_rate == pytest.approx(0.5)
    assert metrics.relation_extraction_coverage == pytest.approx(1.0)
    assert metrics.unresolved_conflicts == 1
    assert metrics.evidence_coverage == pytest.approx(1.0)
    assert metrics.avg_diagnosticity == pytest.approx(0.7)
    assert metrics.historical_accuracy == pytest.approx(0.82)
    assert metrics.avg_evidence_age_hours >= 0.0


@pytest.mark.asyncio
async def test_quality_gate_should_alert():
    gate = QualityGate(db_session=None)  # type: ignore[arg-type]
    alerts = await gate.should_alert(
        QualityMetrics(
            entity_resolution_rate=0.4,
            relation_extraction_coverage=0.2,
            unresolved_conflicts=5,
            evidence_coverage=0.3,
            avg_diagnosticity=0.9,
            historical_accuracy=0.5,
            avg_evidence_age_hours=48.0,
        )
    )
    assert len(alerts) == 3
    assert "证据覆盖率低于 50%" in alerts[0]

