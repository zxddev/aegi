# Author: msq
"""质量门禁 — 用量化指标评估分析质量。"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.analysis_memory import AnalysisMemoryRecord
from aegi_core.db.models.entity_identity_action import EntityIdentityAction
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.relation_fact import RelationFact
from aegi_core.db.models.source_claim import SourceClaim


class QualityMetrics(BaseModel):
    entity_resolution_rate: float
    relation_extraction_coverage: float
    unresolved_conflicts: int
    evidence_coverage: float
    avg_diagnosticity: float
    historical_accuracy: float | None
    avg_evidence_age_hours: float


class QualityGate:
    """按 case 计算核心质量指标。"""

    def __init__(self, db_session: AsyncSession):
        self._db = db_session

    async def evaluate(self, case_uid: str) -> QualityMetrics:
        """评估 case 的分析质量。"""
        entity_resolution_rate = await self._entity_resolution_rate(case_uid)
        relation_extraction_coverage, unresolved_conflicts = (
            await self._relation_metrics(case_uid)
        )
        evidence_coverage, avg_diagnosticity = await self._evidence_metrics(case_uid)
        historical_accuracy = await self._historical_accuracy(case_uid)
        avg_evidence_age_hours = await self._avg_evidence_age_hours(case_uid)
        return QualityMetrics(
            entity_resolution_rate=entity_resolution_rate,
            relation_extraction_coverage=relation_extraction_coverage,
            unresolved_conflicts=unresolved_conflicts,
            evidence_coverage=evidence_coverage,
            avg_diagnosticity=avg_diagnosticity,
            historical_accuracy=historical_accuracy,
            avg_evidence_age_hours=avg_evidence_age_hours,
        )

    async def should_alert(self, metrics: QualityMetrics) -> list[str]:
        """根据指标判断是否需要告警。"""
        alerts: list[str] = []
        if metrics.evidence_coverage < 0.5:
            alerts.append("证据覆盖率低于 50%，建议补充证据")
        if metrics.unresolved_conflicts > 3:
            alerts.append(f"有 {metrics.unresolved_conflicts} 个未解决的关系冲突")
        if metrics.avg_diagnosticity < 1.5:
            alerts.append("证据诊断性偏低，难以区分假设")
        return alerts

    async def _entity_resolution_rate(self, case_uid: str) -> float:
        rows = (
            (
                await self._db.execute(
                    sa.select(EntityIdentityAction).where(
                        EntityIdentityAction.case_uid == case_uid
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return 1.0
        resolved = sum(
            1
            for row in rows
            if row.approved or row.status in {"approved", "merged", "completed"}
        )
        return resolved / len(rows)

    async def _relation_metrics(self, case_uid: str) -> tuple[float, int]:
        rows = (
            (
                await self._db.execute(
                    sa.select(RelationFact).where(RelationFact.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0.0, 0

        unique_entities: set[str] = set()
        unique_pairs: set[tuple[str, str]] = set()
        unresolved_conflicts = 0
        for row in rows:
            unique_entities.add(row.source_entity_uid)
            unique_entities.add(row.target_entity_uid)
            pair = tuple(sorted([row.source_entity_uid, row.target_entity_uid]))
            unique_pairs.add(pair)
            if row.conflicts_with and not row.conflict_resolution:
                unresolved_conflicts += 1

        n_entities = len(unique_entities)
        possible_pairs = n_entities * (n_entities - 1) / 2
        if possible_pairs <= 0:
            coverage = 1.0
        else:
            coverage = len(unique_pairs) / possible_pairs
        return min(1.0, coverage), unresolved_conflicts

    async def _evidence_metrics(self, case_uid: str) -> tuple[float, float]:
        hypothesis_rows = (
            (
                await self._db.execute(
                    sa.select(Hypothesis.uid).where(Hypothesis.case_uid == case_uid)
                )
            )
            .scalars()
            .all()
        )
        hypothesis_uids = set(hypothesis_rows)
        if not hypothesis_uids:
            return 0.0, 0.0

        assessment_rows = (
            (
                await self._db.execute(
                    sa.select(EvidenceAssessment).where(
                        EvidenceAssessment.case_uid == case_uid
                    )
                )
            )
            .scalars()
            .all()
        )
        if not assessment_rows:
            return 0.0, 0.0

        covered_hypotheses = {
            row.hypothesis_uid for row in assessment_rows if row.hypothesis_uid
        }
        evidence_coverage = len(covered_hypotheses & hypothesis_uids) / len(
            hypothesis_uids
        )
        diagnosticity_values = [
            abs(float(row.likelihood) - 0.5) * 2.0 for row in assessment_rows
        ]
        avg_diagnosticity = sum(diagnosticity_values) / len(diagnosticity_values)
        return evidence_coverage, avg_diagnosticity

    async def _historical_accuracy(self, case_uid: str) -> float | None:
        rows = (
            (
                await self._db.execute(
                    sa.select(AnalysisMemoryRecord.prediction_accuracy).where(
                        AnalysisMemoryRecord.case_uid == case_uid,
                        AnalysisMemoryRecord.prediction_accuracy.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        values = [float(value) for value in rows if value is not None]
        if not values:
            return None
        return sum(values) / len(values)

    async def _avg_evidence_age_hours(self, case_uid: str) -> float:
        now = datetime.now(timezone.utc)
        try:
            claim_rows = (
                (
                    await self._db.execute(
                        sa.select(SourceClaim.created_at).where(
                            SourceClaim.case_uid == case_uid
                        )
                    )
                )
                .scalars()
                .all()
            )
        except Exception:
            claim_rows = []

        timestamps = [value for value in claim_rows if value is not None]
        if not timestamps:
            assessment_rows = (
                (
                    await self._db.execute(
                        sa.select(EvidenceAssessment.created_at).where(
                            EvidenceAssessment.case_uid == case_uid
                        )
                    )
                )
                .scalars()
                .all()
            )
            timestamps = [value for value in assessment_rows if value is not None]

        if not timestamps:
            return 0.0

        normalized = [
            ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            for ts in timestamps
        ]
        ages = [(now - ts).total_seconds() / 3600 for ts in normalized]
        return sum(ages) / len(ages)
