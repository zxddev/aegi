# Author: msq
"""结构化分析记忆系统。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.analysis_memory import AnalysisMemoryRecord
from aegi_core.db.models.evidence_assessment import EvidenceAssessment
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.settings import settings

logger = logging.getLogger(__name__)

_TAG_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")


class AnalysisMemorySynthesis(BaseModel):
    scenario_summary: str
    conclusion: str
    pattern_tags: list[str] = Field(default_factory=list)


class AnalysisMemoryEntry(BaseModel):
    """单条分析记忆。"""

    uid: str
    case_uid: str
    created_at: datetime
    scenario_summary: str
    scenario_embedding: list[float] | None = None
    hypotheses: list[dict] = Field(default_factory=list)
    key_evidence: list[dict] = Field(default_factory=list)
    conclusion: str
    confidence: float
    outcome: str | None = None
    prediction_accuracy: float | None = None
    lessons_learned: str | None = None
    pattern_tags: list[str] = Field(default_factory=list)


class AnalysisMemory:
    """分析记忆服务。"""

    def __init__(
        self,
        db_session: AsyncSession,
        qdrant: object | None,
        llm: object | None,
    ) -> None:
        self._db = db_session
        self._qdrant = qdrant
        self._llm = llm

    async def record(self, case_uid: str) -> AnalysisMemoryEntry:
        """从 case 当前状态生成一条分析记忆。"""
        hypotheses = await self._load_hypotheses(case_uid)
        key_evidence = await self._load_key_evidence(case_uid)
        synthesis = await self._summarize(
            case_uid=case_uid,
            hypotheses=hypotheses,
            key_evidence=key_evidence,
        )

        uid = f"mem_{uuid4().hex}"
        row = AnalysisMemoryRecord(
            uid=uid,
            case_uid=case_uid,
            scenario_summary=synthesis.scenario_summary,
            hypotheses=hypotheses,
            key_evidence=key_evidence,
            conclusion=synthesis.conclusion,
            confidence=_derive_confidence(hypotheses),
            pattern_tags=normalize_tags(synthesis.pattern_tags),
        )
        self._db.add(row)
        await self._db.commit()

        embedding: list[float] | None = None
        if self._llm is not None and self._qdrant is not None:
            embedding = await self._upsert_vector(
                memory_uid=uid,
                case_uid=case_uid,
                summary=synthesis.scenario_summary,
                tags=row.pattern_tags,
            )

        return _to_entry(row, scenario_embedding=embedding)

    async def recall(self, scenario: str, top_k: int = 5) -> list[AnalysisMemoryEntry]:
        """检索历史上类似的分析案例。"""
        if top_k <= 0:
            return []

        vector_hits = await self._recall_by_vector(scenario, top_k=top_k)
        if vector_hits:
            return vector_hits

        return await self._recall_by_keyword(scenario, top_k=top_k)

    async def update_outcome(
        self,
        memory_uid: str,
        outcome: str,
        accuracy: float,
        lessons_learned: str | None = None,
    ) -> AnalysisMemoryEntry:
        """更新记忆条目的事后验证结果。"""
        row = await self._db.get(AnalysisMemoryRecord, memory_uid)
        if row is None:
            raise ValueError(f"AnalysisMemoryRecord not found: {memory_uid}")

        row.outcome = outcome
        row.prediction_accuracy = max(0.0, min(1.0, accuracy))
        row.lessons_learned = lessons_learned
        row.updated_at = datetime.now(timezone.utc)
        await self._db.commit()
        return _to_entry(row)

    async def get_pattern_stats(self, pattern_tag: str) -> dict:
        """统计某个模式标签的历史预测准确率。"""
        rows = (
            (
                await self._db.execute(
                    sa.select(AnalysisMemoryRecord).order_by(
                        AnalysisMemoryRecord.created_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        matched = [row for row in rows if pattern_tag in (row.pattern_tags or [])]
        accuracies = [
            float(row.prediction_accuracy)
            for row in matched
            if row.prediction_accuracy is not None
        ]
        recent = matched[0] if matched else None
        return {
            "pattern_tag": pattern_tag,
            "count": len(matched),
            "avg_accuracy": (sum(accuracies) / len(accuracies)) if accuracies else None,
            "recent_case": (
                {
                    "uid": recent.uid,
                    "case_uid": recent.case_uid,
                    "conclusion": recent.conclusion,
                    "prediction_accuracy": recent.prediction_accuracy,
                    "created_at": recent.created_at.isoformat(),
                }
                if recent
                else None
            ),
        }

    async def enhance_analysis(
        self,
        case_uid: str,
        current_hypotheses: list[dict],
    ) -> dict:
        """用历史记忆增强当前分析。"""
        hypothesis_text = "; ".join(
            str(item.get("label") or item.get("hypothesis_text") or "")
            for item in current_hypotheses
            if item
        ).strip()
        scenario = (
            f"case={case_uid}; hypotheses={hypothesis_text}"
            if hypothesis_text
            else f"case={case_uid}; hypotheses=unknown"
        )

        similar = await self.recall(scenario, top_k=settings.analysis_memory_recall_top_k)

        outcome_distribution: dict[str, int] = {}
        evidence_type_count: dict[str, int] = {}
        blindspot_candidates: dict[str, int] = {}
        for item in similar:
            if item.outcome:
                outcome_distribution[item.outcome] = (
                    outcome_distribution.get(item.outcome, 0) + 1
                )
            for ev in item.key_evidence:
                ev_type = str(
                    ev.get("relation")
                    or ev.get("evidence_type")
                    or ev.get("kind")
                    or "unknown"
                )
                evidence_type_count[ev_type] = evidence_type_count.get(ev_type, 0) + 1
            for tag in item.pattern_tags:
                blindspot_candidates[tag] = blindspot_candidates.get(tag, 0) + 1

        recommended_evidence_types = sorted(
            evidence_type_count,
            key=evidence_type_count.get,
            reverse=True,
        )[:3]
        potential_blindspots = sorted(
            blindspot_candidates,
            key=blindspot_candidates.get,
            reverse=True,
        )[:3]
        similar_cases = [
            {
                "uid": item.uid,
                "case_uid": item.case_uid,
                "scenario_summary": item.scenario_summary,
                "conclusion": item.conclusion,
                "confidence": item.confidence,
                "prediction_accuracy": item.prediction_accuracy,
                "pattern_tags": item.pattern_tags,
            }
            for item in similar
        ]
        return {
            "similar_cases": similar_cases,
            "outcome_distribution": outcome_distribution,
            "recommended_evidence_types": recommended_evidence_types,
            "potential_blindspots": potential_blindspots,
        }

    async def _load_hypotheses(self, case_uid: str) -> list[dict]:
        rows = (
            (
                await self._db.execute(
                    sa.select(Hypothesis)
                    .where(Hypothesis.case_uid == case_uid)
                    .order_by(
                        Hypothesis.posterior_probability.desc().nullslast(),
                        Hypothesis.confidence.desc().nullslast(),
                    )
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "uid": row.uid,
                "label": row.label,
                "prior_probability": row.prior_probability,
                "posterior_probability": row.posterior_probability,
                "confidence": row.confidence,
                "coverage_score": row.coverage_score,
            }
            for row in rows
        ]

    async def _load_key_evidence(self, case_uid: str) -> list[dict]:
        rows = (
            (
                await self._db.execute(
                    sa.select(EvidenceAssessment)
                    .where(EvidenceAssessment.case_uid == case_uid)
                    .order_by(
                        EvidenceAssessment.created_at.desc(),
                        EvidenceAssessment.strength.desc(),
                    )
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        ranked = [
            {
                "evidence_uid": row.evidence_uid,
                "hypothesis_uid": row.hypothesis_uid,
                "relation": row.relation,
                "strength": float(row.strength),
                "likelihood": float(row.likelihood),
                "diagnosticity": abs(float(row.likelihood) - 0.5) * 2.0,
                "assessed_by": row.assessed_by,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
        ranked.sort(
            key=lambda item: (item["diagnosticity"], item["strength"]),
            reverse=True,
        )
        return ranked[:10]

    async def _summarize(
        self,
        *,
        case_uid: str,
        hypotheses: list[dict],
        key_evidence: list[dict],
    ) -> AnalysisMemorySynthesis:
        if self._llm is None or not hasattr(self._llm, "invoke_structured"):
            return _fallback_synthesis(case_uid, hypotheses, key_evidence)

        hyp_lines = [
            f"- {item.get('label', '')} (posterior={item.get('posterior_probability')})"
            for item in hypotheses[:5]
        ]
        ev_lines = [
            f"- {item.get('relation')} {item.get('evidence_uid')} "
            f"(diagnosticity={item.get('diagnosticity'):.2f})"
            for item in key_evidence[:5]
        ]
        prompt = (
            "你是情报分析复盘助手。根据当前分析状态生成可检索记忆。\n"
            '返回严格 JSON：{"scenario_summary":"", "conclusion":"", "pattern_tags":[""]}\n'
            f"case_uid={case_uid}\n"
            f"Hypotheses:\n{chr(10).join(hyp_lines) or '- none'}\n"
            f"Evidence:\n{chr(10).join(ev_lines) or '- none'}\n"
            "要求：pattern_tags 使用简短英文蛇形命名，最多 6 个。"
        )
        try:
            synthesis = await self._llm.invoke_structured(
                prompt,
                AnalysisMemorySynthesis,
                max_tokens=1024,
                temperature=0.1,
            )
            return AnalysisMemorySynthesis(
                scenario_summary=synthesis.scenario_summary.strip() or f"Case {case_uid}",
                conclusion=synthesis.conclusion.strip() or "No clear conclusion",
                pattern_tags=normalize_tags(synthesis.pattern_tags),
            )
        except Exception:
            logger.warning("AnalysisMemory LLM summarize failed, fallback to rule-based")
            return _fallback_synthesis(case_uid, hypotheses, key_evidence)

    async def _upsert_vector(
        self,
        *,
        memory_uid: str,
        case_uid: str,
        summary: str,
        tags: list[str],
    ) -> list[float] | None:
        if self._llm is None or self._qdrant is None:
            return None
        try:
            embedding = await self._llm.embed(summary)
            await self._qdrant.upsert(
                memory_uid,
                embedding,
                summary,
                metadata={
                    "kind": "analysis_memory",
                    "memory_uid": memory_uid,
                    "case_uid": case_uid,
                    "pattern_tags": tags,
                },
            )
            return embedding
        except Exception:
            logger.warning("AnalysisMemory vector upsert failed", exc_info=True)
            return None

    async def _recall_by_vector(
        self,
        scenario: str,
        *,
        top_k: int,
    ) -> list[AnalysisMemoryEntry]:
        if self._llm is None or self._qdrant is None:
            return []
        try:
            embedding = await self._llm.embed(scenario)
            hits = await self._qdrant.search(embedding, limit=max(top_k * 4, top_k))
        except Exception:
            logger.warning("AnalysisMemory vector recall failed", exc_info=True)
            return []

        uid_order: list[str] = []
        for hit in hits:
            metadata = getattr(hit, "metadata", {}) or {}
            if metadata.get("kind") not in {None, "analysis_memory"}:
                continue
            uid = str(metadata.get("memory_uid") or getattr(hit, "chunk_uid", ""))
            if uid and uid not in uid_order:
                uid_order.append(uid)
        if not uid_order:
            return []

        rows = (
            (
                await self._db.execute(
                    sa.select(AnalysisMemoryRecord).where(
                        AnalysisMemoryRecord.uid.in_(uid_order)
                    )
                )
            )
            .scalars()
            .all()
        )
        row_by_uid = {row.uid: row for row in rows}
        return [_to_entry(row_by_uid[uid]) for uid in uid_order if uid in row_by_uid][
            :top_k
        ]

    async def _recall_by_keyword(
        self,
        scenario: str,
        *,
        top_k: int,
    ) -> list[AnalysisMemoryEntry]:
        tokens = [tok for tok in re.findall(r"\w+", scenario.lower()) if len(tok) >= 3]
        stmt = sa.select(AnalysisMemoryRecord).order_by(
            AnalysisMemoryRecord.created_at.desc()
        )
        if tokens:
            conditions = [
                AnalysisMemoryRecord.scenario_summary.ilike(f"%{token}%")
                for token in tokens[:6]
            ]
            stmt = stmt.where(sa.or_(*conditions))
        rows = (await self._db.execute(stmt.limit(top_k))).scalars().all()
        return [_to_entry(row) for row in rows]


def normalize_tags(pattern_tags: list[str]) -> list[str]:
    """清洗标签，统一为 snake_case。"""
    tags: list[str] = []
    for raw in pattern_tags:
        normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized and _TAG_TOKEN_RE.fullmatch(normalized):
            tags.append(normalized)
    return list(dict.fromkeys(tags))[:8]


def _derive_confidence(hypotheses: list[dict]) -> float:
    if not hypotheses:
        return 0.0
    values = []
    for item in hypotheses:
        prob = item.get("posterior_probability")
        conf = item.get("confidence")
        value = prob if prob is not None else conf
        if value is not None:
            values.append(float(value))
    return max(values) if values else 0.0


def _fallback_synthesis(
    case_uid: str,
    hypotheses: list[dict],
    key_evidence: list[dict],
) -> AnalysisMemorySynthesis:
    top_hypothesis = hypotheses[0]["label"] if hypotheses else "No dominant hypothesis"
    scenario_summary = f"Case {case_uid}: {top_hypothesis[:160]}"
    conclusion = f"Most probable hypothesis: {top_hypothesis[:200]}"
    token_source = " ".join(str(item.get("label", "")) for item in hypotheses[:5]).lower()
    tokens = _TAG_TOKEN_RE.findall(token_source)
    tags = list(dict.fromkeys(token.replace("-", "_") for token in tokens))[:4]
    if not tags and key_evidence:
        tags = [str(key_evidence[0].get("relation", "evidence"))]
    return AnalysisMemorySynthesis(
        scenario_summary=scenario_summary,
        conclusion=conclusion,
        pattern_tags=normalize_tags(tags),
    )


def _to_entry(
    row: AnalysisMemoryRecord,
    *,
    scenario_embedding: list[float] | None = None,
) -> AnalysisMemoryEntry:
    return AnalysisMemoryEntry(
        uid=row.uid,
        case_uid=row.case_uid,
        created_at=row.created_at,
        scenario_summary=row.scenario_summary,
        scenario_embedding=scenario_embedding,
        hypotheses=row.hypotheses or [],
        key_evidence=row.key_evidence or [],
        conclusion=row.conclusion,
        confidence=float(row.confidence),
        outcome=row.outcome,
        prediction_accuracy=row.prediction_accuracy,
        lessons_learned=row.lessons_learned,
        pattern_tags=row.pattern_tags or [],
    )

