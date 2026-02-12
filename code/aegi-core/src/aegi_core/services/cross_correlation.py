# Author: msq
"""多源交叉关联引擎。"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.artifact import ArtifactVersion
from aegi_core.db.models.gdelt_event import GdeltEvent
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.analysis_memory import AnalysisMemory
from aegi_core.services.event_bus import AegiEvent, get_event_bus
from aegi_core.settings import settings

logger = logging.getLogger(__name__)

_ENTITY_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")


class CorrelationPattern(BaseModel):
    """发现的关联模式。"""

    pattern_uid: str
    pattern_type: str
    event_uids: list[str]
    claim_uids: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    description: str
    significance_score: float
    confidence: float
    suggested_hypothesis: str | None = None


class PatternEvaluation(BaseModel):
    is_significant: bool
    description: str
    score: float
    suggested_hypothesis: str | None = None


@dataclass(slots=True)
class CorrelationEvent:
    uid: str
    case_uid: str
    title: str
    text: str
    published_at: datetime | None = None
    geo_country: str | None = None
    source_domain: str | None = None
    url: str | None = None
    goldstein_scale: float | None = None
    entities: list[str] = field(default_factory=list)
    claim_uids: list[str] = field(default_factory=list)


class CrossCorrelationEngine:
    """发现不同事件之间的隐含关联。"""

    def __init__(
        self,
        db_session: AsyncSession,
        llm: object | None,
        qdrant: object | None,
        neo4j: object | None,
        *,
        memory: AnalysisMemory | None = None,
    ) -> None:
        self._db = db_session
        self._llm = llm
        self._qdrant = qdrant
        self._neo4j = neo4j
        self._memory = memory

    async def analyze_batch(
        self,
        case_uid: str,
        new_event_uids: list[str],
    ) -> list[CorrelationPattern]:
        """对一批新事件做交叉关联分析。"""
        new_events = await self._load_events(case_uid, new_event_uids)
        if not new_events:
            return []

        historical_events = await self._load_historical_events(
            case_uid=case_uid,
            exclude_uids={event.uid for event in new_events},
        )

        patterns: list[CorrelationPattern] = []
        patterns.extend(await self._entity_cooccurrence(new_events, historical_events))
        patterns.extend(
            await self._spatiotemporal_proximity(
                new_events,
                time_window_hours=settings.cross_correlation_time_window_hours,
            )
        )
        patterns.extend(
            await self._semantic_pattern(
                new_events,
                top_k=settings.cross_correlation_semantic_top_k,
            )
        )
        deduped = _dedupe_patterns(patterns)
        deduped.sort(key=lambda item: item.significance_score, reverse=True)

        if self._memory is not None:
            await self._augment_with_memory(deduped)
        return deduped[:30]

    async def _entity_cooccurrence(
        self,
        new_events: list[CorrelationEvent],
        historical_events: list[CorrelationEvent],
    ) -> list[CorrelationPattern]:
        """实体共现关联：不同事件涉及相同实体。"""
        patterns: list[CorrelationPattern] = []
        for new_event in new_events:
            for historical in historical_events:
                if new_event.uid == historical.uid:
                    continue
                shared_entities = sorted(
                    set(new_event.entities) & set(historical.entities)
                )
                if not shared_entities:
                    continue

                significance = min(1.0, 0.35 + 0.12 * len(shared_entities))
                confidence = min(1.0, 0.45 + 0.1 * len(shared_entities))
                description = (
                    f"{new_event.title} 与 {historical.title} 共享实体："
                    f"{', '.join(shared_entities[:4])}"
                )
                suggested_hypothesis = None
                if significance >= 0.55:
                    is_sig, llm_desc, llm_score, llm_hypothesis = (
                        await self._llm_evaluate_pattern([new_event, historical])
                    )
                    if not is_sig:
                        continue
                    description = llm_desc
                    significance = max(significance, llm_score)
                    suggested_hypothesis = llm_hypothesis

                patterns.append(
                    CorrelationPattern(
                        pattern_uid=f"pat_{uuid4().hex}",
                        pattern_type="entity_cooccurrence",
                        event_uids=[new_event.uid, historical.uid],
                        claim_uids=_merge_uids(
                            new_event.claim_uids,
                            historical.claim_uids,
                        ),
                        entities=shared_entities,
                        description=description,
                        significance_score=min(1.0, significance),
                        confidence=min(1.0, confidence),
                        suggested_hypothesis=suggested_hypothesis,
                    )
                )
        return patterns

    async def _spatiotemporal_proximity(
        self,
        new_events: list[CorrelationEvent],
        time_window_hours: int = 72,
    ) -> list[CorrelationPattern]:
        """时空邻近关联：时间窗口内、同一地区的事件。"""
        patterns: list[CorrelationPattern] = []
        if time_window_hours <= 0:
            return patterns

        for new_event in new_events:
            if not new_event.geo_country or not new_event.published_at:
                continue

            window = timedelta(hours=time_window_hours)
            stmt = sa.select(GdeltEvent).where(
                GdeltEvent.case_uid == new_event.case_uid,
                GdeltEvent.uid != new_event.uid,
                GdeltEvent.geo_country == new_event.geo_country,
                GdeltEvent.published_at.is_not(None),
                GdeltEvent.published_at >= (new_event.published_at - window),
                GdeltEvent.published_at <= (new_event.published_at + window),
            )
            historical_rows = (await self._db.execute(stmt.limit(50))).scalars().all()
            for row in historical_rows:
                historical = _gdelt_to_event(row)
                hours_apart = abs(
                    (historical.published_at - new_event.published_at).total_seconds()
                    / 3600
                )
                time_score = max(0.0, 1 - (hours_apart / float(time_window_hours)))
                goldstein_delta = 0.0
                if (
                    new_event.goldstein_scale is not None
                    and historical.goldstein_scale is not None
                ):
                    goldstein_delta = abs(
                        float(new_event.goldstein_scale)
                        - float(historical.goldstein_scale)
                    )
                anomaly_score = min(0.3, goldstein_delta / 10.0)
                significance = min(1.0, 0.35 + (0.5 * time_score) + anomaly_score)
                confidence = min(1.0, 0.45 + (0.35 * time_score))
                description = (
                    f"{new_event.geo_country} {time_window_hours}h 窗口内出现相邻事件："
                    f"{new_event.title} ↔ {historical.title}"
                )
                suggested_hypothesis = None
                if significance >= 0.55:
                    is_sig, llm_desc, llm_score, llm_hypothesis = (
                        await self._llm_evaluate_pattern([new_event, historical])
                    )
                    if not is_sig:
                        continue
                    description = llm_desc
                    significance = max(significance, llm_score)
                    suggested_hypothesis = llm_hypothesis

                patterns.append(
                    CorrelationPattern(
                        pattern_uid=f"pat_{uuid4().hex}",
                        pattern_type="spatiotemporal",
                        event_uids=[new_event.uid, historical.uid],
                        claim_uids=[],
                        entities=_merge_uids(
                            [new_event.geo_country],
                            [historical.geo_country] if historical.geo_country else [],
                        ),
                        description=description,
                        significance_score=min(1.0, significance),
                        confidence=min(1.0, confidence),
                        suggested_hypothesis=suggested_hypothesis,
                    )
                )
        return patterns

    async def _semantic_pattern(
        self,
        new_events: list[CorrelationEvent],
        top_k: int = 20,
    ) -> list[CorrelationPattern]:
        """语义模式关联：用 embedding 找语义相似但表面不同的事件。"""
        if self._llm is None or self._qdrant is None or top_k <= 0:
            return []
        if not hasattr(self._llm, "embed") or not hasattr(self._qdrant, "search"):
            return []

        patterns: list[CorrelationPattern] = []
        for event in new_events:
            query_text = (event.text or event.title).strip()
            if not query_text:
                continue

            try:
                embedding = await self._llm.embed(query_text)
                hits = await self._qdrant.search(
                    embedding,
                    limit=top_k,
                    score_threshold=0.45,
                )
            except Exception:
                logger.warning("Cross-correlation semantic search failed", exc_info=True)
                continue

            chunk_uids = [hit.chunk_uid for hit in hits if getattr(hit, "chunk_uid", "")]
            if not chunk_uids:
                continue

            rows = (
                await self._db.execute(
                    sa.select(SourceClaim, ArtifactVersion)
                    .join(
                        ArtifactVersion,
                        SourceClaim.artifact_version_uid == ArtifactVersion.uid,
                    )
                    .where(
                        SourceClaim.case_uid == event.case_uid,
                        SourceClaim.chunk_uid.in_(chunk_uids),
                    )
                )
            ).all()
            claim_map: dict[str, tuple[SourceClaim, ArtifactVersion]] = {}
            for source_claim, artifact_version in rows:
                claim_map[source_claim.chunk_uid] = (source_claim, artifact_version)

            for hit in hits:
                if hit.chunk_uid not in claim_map:
                    continue
                source_claim, artifact_version = claim_map[hit.chunk_uid]
                source_meta = artifact_version.source_meta or {}
                candidate_url = str(source_meta.get("url") or "")
                candidate_domain = str(
                    source_meta.get("source_domain")
                    or source_meta.get("domain")
                    or source_claim.attributed_to
                    or ""
                )

                # 过滤同源候选，避免把同一来源重复发布当成模式。
                if candidate_url and event.url and candidate_url == event.url:
                    continue
                if (
                    candidate_domain
                    and event.source_domain
                    and candidate_domain == event.source_domain
                ):
                    continue

                significance = min(1.0, max(0.0, float(hit.score)))
                confidence = min(1.0, 0.4 + significance * 0.5)
                description = (
                    f"语义相似事件：{event.title} ↔ "
                    f"{(source_claim.quote or '')[:80]}"
                )
                suggested_hypothesis = None
                if significance >= 0.55:
                    synthetic_event = CorrelationEvent(
                        uid=f"claim:{source_claim.uid}",
                        case_uid=source_claim.case_uid,
                        title=(source_claim.quote or "")[:120],
                        text=source_claim.quote or "",
                        published_at=source_claim.created_at,
                        source_domain=candidate_domain or None,
                        url=candidate_url or None,
                        entities=_extract_claim_entities(source_claim),
                        claim_uids=[source_claim.uid],
                    )
                    is_sig, llm_desc, llm_score, llm_hypothesis = (
                        await self._llm_evaluate_pattern([event, synthetic_event])
                    )
                    if not is_sig:
                        continue
                    description = llm_desc
                    significance = max(significance, llm_score)
                    suggested_hypothesis = llm_hypothesis

                patterns.append(
                    CorrelationPattern(
                        pattern_uid=f"pat_{uuid4().hex}",
                        pattern_type="semantic",
                        event_uids=[event.uid, f"claim:{source_claim.uid}"],
                        claim_uids=_merge_uids(event.claim_uids, [source_claim.uid]),
                        entities=_merge_uids(
                            event.entities, _extract_claim_entities(source_claim)
                        ),
                        description=description,
                        significance_score=min(1.0, significance),
                        confidence=min(1.0, confidence),
                        suggested_hypothesis=suggested_hypothesis,
                    )
                )

        return patterns

    async def _llm_evaluate_pattern(
        self,
        events: list[CorrelationEvent],
    ) -> tuple[bool, str, float, str | None]:
        """用 LLM 判断事件组合是否构成显著模式。"""
        if self._llm is None or not hasattr(self._llm, "invoke_structured"):
            return _heuristic_pattern_eval(events)

        event_payload = [
            {
                "uid": event.uid,
                "title": event.title,
                "text": event.text[:400],
                "published_at": (
                    event.published_at.isoformat() if event.published_at else None
                ),
                "geo_country": event.geo_country,
                "entities": event.entities[:8],
            }
            for event in events
        ]
        prompt = (
            "你是跨事件关联分析助手。判断以下事件组合是否构成值得关注的模式。\n"
            '返回 JSON: {"is_significant":bool, "description":"", "score":0~1, '
            '"suggested_hypothesis":"optional"}\n'
            f"events={event_payload}"
        )
        try:
            result = await self._llm.invoke_structured(
                prompt,
                PatternEvaluation,
                max_tokens=1024,
                temperature=0.1,
            )
            return (
                bool(result.is_significant),
                result.description.strip() or "Detected a meaningful cross-event pattern",
                max(0.0, min(1.0, float(result.score))),
                (result.suggested_hypothesis or None),
            )
        except Exception:
            logger.warning("LLM pattern evaluation failed, fallback to heuristic")
            return _heuristic_pattern_eval(events)

    async def _load_events(
        self,
        case_uid: str,
        event_uids: list[str],
    ) -> list[CorrelationEvent]:
        if not event_uids:
            return []
        unique_ids = list(dict.fromkeys(uid for uid in event_uids if uid))

        gdelt_rows = (
            (
                await self._db.execute(
                    sa.select(GdeltEvent).where(
                        GdeltEvent.case_uid == case_uid,
                        GdeltEvent.uid.in_(unique_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        found_gdelt_uids = {row.uid for row in gdelt_rows}
        claim_candidate_uids = [uid for uid in unique_ids if uid not in found_gdelt_uids]

        claim_rows: list[tuple[SourceClaim, ArtifactVersion]] = []
        if claim_candidate_uids:
            claim_rows = (
                await self._db.execute(
                    sa.select(SourceClaim, ArtifactVersion)
                    .join(
                        ArtifactVersion,
                        SourceClaim.artifact_version_uid == ArtifactVersion.uid,
                    )
                    .where(
                        SourceClaim.case_uid == case_uid,
                        SourceClaim.uid.in_(claim_candidate_uids),
                    )
                )
            ).all()

        events = [_gdelt_to_event(row) for row in gdelt_rows]
        events.extend(_claim_to_event(sc, av) for sc, av in claim_rows)
        return events

    async def _load_historical_events(
        self,
        *,
        case_uid: str,
        exclude_uids: set[str],
    ) -> list[CorrelationEvent]:
        gdelt_stmt = (
            sa.select(GdeltEvent)
            .where(GdeltEvent.case_uid == case_uid)
            .order_by(GdeltEvent.published_at.desc().nullslast())
            .limit(300)
        )
        gdelt_rows = (await self._db.execute(gdelt_stmt)).scalars().all()

        claim_stmt = (
            sa.select(SourceClaim, ArtifactVersion)
            .join(ArtifactVersion, SourceClaim.artifact_version_uid == ArtifactVersion.uid)
            .where(SourceClaim.case_uid == case_uid)
            .order_by(SourceClaim.created_at.desc())
            .limit(200)
        )
        claim_rows = (await self._db.execute(claim_stmt)).all()

        events: list[CorrelationEvent] = []
        for row in gdelt_rows:
            if row.uid in exclude_uids:
                continue
            events.append(_gdelt_to_event(row))
        for source_claim, artifact_version in claim_rows:
            synthetic_uid = f"claim:{source_claim.uid}"
            if source_claim.uid in exclude_uids or synthetic_uid in exclude_uids:
                continue
            events.append(_claim_to_event(source_claim, artifact_version))
        return events

    async def _augment_with_memory(self, patterns: list[CorrelationPattern]) -> None:
        if not patterns:
            return
        for pattern in patterns[:10]:
            try:
                recall_rows = await self._memory.recall(pattern.description, top_k=1)
            except Exception:
                logger.warning("AnalysisMemory recall failed in correlation engine")
                continue
            if not recall_rows:
                continue
            best = recall_rows[0]
            if best.prediction_accuracy is not None:
                pattern.confidence = min(
                    1.0,
                    (pattern.confidence + float(best.prediction_accuracy)) / 2.0,
                )
            pattern.description = (
                f"{pattern.description} "
                f"(historical_ref={best.uid}, case={best.case_uid})"
            )


def create_cross_correlation_handler(
    *,
    llm: object | None,
    qdrant: object | None,
    neo4j: object | None,
    memory_qdrant: object | None = None,
) -> object:
    """创建 claim.extracted / gdelt.event_detected 处理器。"""
    from aegi_core.db.session import ENGINE

    state_lock = asyncio.Lock()
    pending_by_case: dict[str, set[str]] = {}
    batch_start_by_case: dict[str, datetime] = {}
    running_cases: set[str] = set()

    async def _emit_patterns(
        case_uid: str,
        event_uids: list[str],
    ) -> None:
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            memory = None
            if settings.analysis_memory_enabled:
                memory = AnalysisMemory(
                    db_session=session,
                    qdrant=memory_qdrant or qdrant,
                    llm=llm,
                )
            engine = CrossCorrelationEngine(
                db_session=session,
                llm=llm,
                qdrant=qdrant,
                neo4j=neo4j,
                memory=memory,
            )
            patterns = await engine.analyze_batch(case_uid, event_uids)

        threshold = max(
            0.0,
            min(1.0, settings.cross_correlation_significance_threshold),
        )
        bus = get_event_bus()
        for pattern in patterns:
            if pattern.significance_score < threshold:
                continue
            severity = (
                "high"
                if pattern.significance_score >= 0.8
                else "medium"
                if pattern.significance_score >= 0.65
                else "low"
            )
            await bus.emit_and_wait(
                AegiEvent(
                    event_type="pattern.discovered",
                    case_uid=case_uid,
                    payload=pattern.model_dump(),
                    entities=pattern.entities,
                    severity=severity,
                    source_event_uid=f"pattern:{pattern.pattern_uid}",
                )
            )

    async def cross_correlation_handler(event: AegiEvent) -> None:
        if not settings.cross_correlation_enabled:
            return
        if event.event_type not in {"claim.extracted", "gdelt.event_detected"}:
            return
        case_uid = event.case_uid
        if not case_uid:
            return

        event_uids: list[str] = []
        if event.event_type == "gdelt.event_detected":
            gdelt_uid = str(event.payload.get("gdelt_event_uid") or "").strip()
            if gdelt_uid:
                event_uids.append(gdelt_uid)
        else:
            claim_uids = event.payload.get("claim_uids", []) or []
            event_uids.extend(str(uid) for uid in claim_uids if uid)
            gdelt_uid = str(event.payload.get("gdelt_event_uid") or "").strip()
            if gdelt_uid:
                event_uids.append(gdelt_uid)

        if not event_uids:
            return

        now = datetime.now(timezone.utc)
        batch_size = max(1, settings.cross_correlation_batch_size)
        batch_window = timedelta(
            seconds=max(1, settings.cross_correlation_batch_window_seconds)
        )
        should_run = False
        run_uids: list[str] = []
        async with state_lock:
            pending = pending_by_case.setdefault(case_uid, set())
            pending.update(event_uids)
            batch_start_by_case.setdefault(case_uid, now)
            batch_age = now - batch_start_by_case[case_uid]
            if (
                case_uid not in running_cases
                and (len(pending) >= batch_size or batch_age >= batch_window)
            ):
                run_uids = sorted(pending)
                pending.clear()
                batch_start_by_case.pop(case_uid, None)
                running_cases.add(case_uid)
                should_run = True

        if not should_run:
            return

        try:
            await _emit_patterns(case_uid, run_uids)
        except Exception:
            logger.exception(
                "Cross-correlation handler failed: case=%s event_uids=%s",
                case_uid,
                run_uids,
            )
        finally:
            async with state_lock:
                running_cases.discard(case_uid)

    cross_correlation_handler.__name__ = "cross_correlation_handler"
    return cross_correlation_handler


def _gdelt_to_event(row: GdeltEvent) -> CorrelationEvent:
    entities = [
        value
        for value in [
            row.actor1,
            row.actor2,
            row.actor1_country,
            row.actor2_country,
            row.geo_country,
        ]
        if value
    ]
    text = " ".join(part for part in [row.title, row.url, row.geo_name or ""] if part)
    return CorrelationEvent(
        uid=row.uid,
        case_uid=row.case_uid or "",
        title=row.title,
        text=text,
        published_at=row.published_at,
        geo_country=row.geo_country,
        source_domain=row.source_domain,
        url=row.url,
        goldstein_scale=row.goldstein_scale,
        entities=list(dict.fromkeys(entities)),
    )


def _claim_to_event(
    source_claim: SourceClaim,
    artifact_version: ArtifactVersion,
) -> CorrelationEvent:
    source_meta = artifact_version.source_meta or {}
    source_domain = str(
        source_meta.get("source_domain")
        or source_meta.get("domain")
        or source_claim.attributed_to
        or ""
    )
    url = str(source_meta.get("url") or "")
    title = (source_claim.quote or "")[:140] or f"Claim {source_claim.uid}"
    entities = _extract_claim_entities(source_claim)
    return CorrelationEvent(
        uid=f"claim:{source_claim.uid}",
        case_uid=source_claim.case_uid,
        title=title,
        text=source_claim.quote or "",
        published_at=source_claim.created_at,
        geo_country=(source_meta.get("geo_country") or None),
        source_domain=source_domain or None,
        url=url or None,
        entities=entities,
        claim_uids=[source_claim.uid],
    )


def _extract_claim_entities(source_claim: SourceClaim) -> list[str]:
    tokens = _ENTITY_TOKEN_RE.findall(source_claim.quote or "")
    if source_claim.attributed_to:
        tokens.append(source_claim.attributed_to)
    return list(dict.fromkeys(token.strip() for token in tokens if token.strip()))[:8]


def _heuristic_pattern_eval(
    events: list[CorrelationEvent],
) -> tuple[bool, str, float, str | None]:
    shared_entities: set[str] | None = None
    for event in events:
        event_entities = set(event.entities)
        if shared_entities is None:
            shared_entities = event_entities
        else:
            shared_entities &= event_entities
    shared_count = len(shared_entities or set())
    score = min(1.0, 0.35 + (0.2 * shared_count) + (0.08 * max(0, len(events) - 1)))
    is_significant = score >= 0.55
    description = (
        f"Detected cross-event signal across {len(events)} events; "
        f"shared_entities={sorted(shared_entities or set())[:5]}"
    )
    hypothesis = (
        "Recurring actors may indicate a coordinated campaign."
        if is_significant
        else None
    )
    return is_significant, description, score, hypothesis


def _merge_uids(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*left, *right]))


def _dedupe_patterns(patterns: list[CorrelationPattern]) -> list[CorrelationPattern]:
    deduped: dict[tuple[str, tuple[str, ...], tuple[str, ...]], CorrelationPattern] = {}
    for pattern in patterns:
        key = (
            pattern.pattern_type,
            tuple(sorted(pattern.event_uids)),
            tuple(sorted(pattern.claim_uids)),
        )
        current = deduped.get(key)
        if current is None or pattern.significance_score > current.significance_score:
            deduped[key] = pattern
    return list(deduped.values())
