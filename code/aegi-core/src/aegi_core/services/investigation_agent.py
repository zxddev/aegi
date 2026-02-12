# Author: msq
"""自主调研代理 — 监听假设变化，识别证据缺口并主动搜集验证。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.case import Case
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.investigation import Investigation
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.db.models.subscription import Subscription
from aegi_core.db.utils import utcnow
from aegi_core.services.bayesian_ach import BayesianACH
from aegi_core.services.event_bus import AegiEvent, get_event_bus
from aegi_core.services.ingest_helpers import embed_and_index_chunk
from aegi_core.settings import settings

logger = logging.getLogger(__name__)

_CANCEL_EVENTS: dict[str, asyncio.Event] = {}
_CANCEL_LOCK = asyncio.Lock()


async def _register_cancel_event(investigation_uid: str) -> None:
    async with _CANCEL_LOCK:
        _CANCEL_EVENTS[investigation_uid] = asyncio.Event()


async def _unregister_cancel_event(investigation_uid: str) -> None:
    async with _CANCEL_LOCK:
        _CANCEL_EVENTS.pop(investigation_uid, None)


async def cancel_investigation_run(investigation_uid: str) -> bool:
    """向运行中的调研发送取消信号。"""
    async with _CANCEL_LOCK:
        cancel_event = _CANCEL_EVENTS.get(investigation_uid)
        if cancel_event is None:
            return False
        cancel_event.set()
        return True


async def _is_cancelled(investigation_uid: str) -> bool:
    async with _CANCEL_LOCK:
        cancel_event = _CANCEL_EVENTS.get(investigation_uid)
        return bool(cancel_event and cancel_event.is_set())


def _parse_sources(value: str) -> list[str]:
    return [part.strip().lower() for part in value.split(",") if part.strip()]


@dataclass(slots=True)
class InvestigationConfig:
    """调研执行配置。"""

    max_rounds: int = 3
    min_posterior_diff: float = 0.15
    min_change_threshold: float = 0.05
    cooldown_seconds: int = 300
    max_concurrent_investigations: int = 3
    token_budget_per_round: int = 10_000
    search_sources: list[str] = field(default_factory=lambda: ["searxng", "gdelt"])


@dataclass(slots=True)
class InvestigationRound:
    """单轮调研执行记录。"""

    round_number: int
    gap_description: str
    search_queries: list[str]
    results_count: int
    claims_extracted: int
    posterior_change: float


@dataclass(slots=True)
class InvestigationResult:
    """完整调研执行结果。"""

    case_uid: str
    trigger_event: str
    rounds: list[InvestigationRound]
    total_claims: int
    gap_resolved: bool
    final_posteriors: dict[str, float]


class InvestigationQueryPlan(BaseModel):
    queries: list[str] = Field(default_factory=list)


def build_investigation_config() -> InvestigationConfig:
    """从 settings 构建调研配置快照。"""
    sources = _parse_sources(settings.investigation_search_sources)
    if not sources:
        sources = ["searxng"]
    return InvestigationConfig(
        max_rounds=max(1, settings.investigation_max_rounds),
        min_posterior_diff=max(0.0, settings.investigation_min_posterior_diff),
        min_change_threshold=max(0.0, settings.investigation_min_change_threshold),
        cooldown_seconds=max(0, settings.investigation_cooldown_seconds),
        max_concurrent_investigations=max(1, settings.investigation_max_concurrent),
        token_budget_per_round=max(256, settings.investigation_token_budget_per_round),
        search_sources=sources,
    )


class InvestigationAgent:
    """自主调研执行器。"""

    def __init__(
        self,
        db_session: AsyncSession,
        llm: Any,
        searxng: Any,
        gdelt_client: Any,
        qdrant: Any = None,
        *,
        config: InvestigationConfig | None = None,
    ) -> None:
        self._db = db_session
        self._llm = llm
        self._searxng = searxng
        self._gdelt = gdelt_client
        self._qdrant = qdrant
        self._config = config or build_investigation_config()

    async def investigate(
        self,
        case_uid: str,
        trigger_event: AegiEvent,
    ) -> InvestigationResult:
        """执行 hypothesis.updated 触发的一次完整调研循环。"""
        investigation_uid = f"inv_{uuid.uuid4().hex}"
        trigger_event_uid = trigger_event.source_event_uid or f"hyp:{uuid.uuid4().hex}"
        investigation_row = Investigation(
            uid=investigation_uid,
            case_uid=case_uid,
            trigger_event_type=trigger_event.event_type,
            trigger_event_uid=trigger_event_uid,
            status="running",
            config=asdict(self._config),
            rounds=[],
            total_claims_extracted=0,
            gap_resolved=False,
            started_at=utcnow(),
            created_at=utcnow(),
        )
        self._db.add(investigation_row)
        await _register_cancel_event(investigation_uid)
        await self._db.commit()
        rounds: list[InvestigationRound] = []
        total_claims = 0
        gap_resolved = False
        posteriors_before = await self._load_posteriors(case_uid)

        try:
            for round_number in range(1, self._config.max_rounds + 1):
                if await _is_cancelled(investigation_uid):
                    await self._mark_cancelled(
                        investigation_uid,
                        rounds=rounds,
                        total_claims=total_claims,
                    )
                    return InvestigationResult(
                        case_uid=case_uid,
                        trigger_event=trigger_event_uid,
                        rounds=rounds,
                        total_claims=total_claims,
                        gap_resolved=False,
                        final_posteriors=await self._load_posteriors(case_uid),
                    )

                gaps = await self._load_actionable_gaps(case_uid)
                if not gaps:
                    gap_resolved = True
                    break

                case_context = await self._build_case_context(case_uid)
                queries = await self._generate_search_queries(gaps, case_context)
                if not queries:
                    break

                search_results = await self._execute_searches(queries)
                claim_uids = await self._ingest_results(
                    search_results,
                    case_uid=case_uid,
                    investigation_uid=investigation_uid,
                )
                total_claims += len(claim_uids)

                posteriors_after = await self._load_posteriors(case_uid)
                posterior_change = self._posterior_change(
                    before=posteriors_before,
                    after=posteriors_after,
                )
                posteriors_before = posteriors_after

                round_record = InvestigationRound(
                    round_number=round_number,
                    gap_description=gaps[0].get("summary", ""),
                    search_queries=queries,
                    results_count=len(search_results),
                    claims_extracted=len(claim_uids),
                    posterior_change=posterior_change,
                )
                rounds.append(round_record)

                await self._persist_progress(
                    investigation_uid=investigation_uid,
                    rounds=rounds,
                    total_claims=total_claims,
                )

            final_posteriors = await self._load_posteriors(case_uid)
            await self._mark_completed(
                investigation_uid=investigation_uid,
                rounds=rounds,
                total_claims=total_claims,
                gap_resolved=gap_resolved,
            )
            await self._notify_case_subscribers(
                case_uid=case_uid,
                message=(
                    f"自动调研完成：case={case_uid} "
                    f"rounds={len(rounds)} claims={total_claims} "
                    f"gap_resolved={gap_resolved}"
                ),
            )
            return InvestigationResult(
                case_uid=case_uid,
                trigger_event=trigger_event_uid,
                rounds=rounds,
                total_claims=total_claims,
                gap_resolved=gap_resolved,
                final_posteriors=final_posteriors,
            )
        except Exception:
            logger.exception(
                "Investigation failed: case=%s uid=%s", case_uid, investigation_uid
            )
            await self._mark_failed(
                investigation_uid=investigation_uid,
                rounds=rounds,
                total_claims=total_claims,
            )
            raise
        finally:
            await _unregister_cancel_event(investigation_uid)

    async def _generate_search_queries(
        self,
        gaps: list[dict[str, Any]],
        case_context: str,
    ) -> list[str]:
        """把证据缺口转为多角度搜索查询。"""
        if not gaps:
            return []

        gap_lines = []
        for gap in gaps[:3]:
            labels = " vs ".join(gap.get("labels", []))
            gap_lines.append(
                f"- pair={labels}; diff={gap.get('posterior_diff', 0)}; "
                f"suggestions={'; '.join(gap.get('suggestions', [])[:2])}"
            )

        prompt = (
            "你是情报检索策略专家。请把证据缺口转为可执行搜索 query。\n"
            '返回严格 JSON：{"queries": ["..."]}，最多 4 条，避免重复。\n'
            f"Case context:\n{case_context}\n"
            f"Gaps:\n{chr(10).join(gap_lines)}"
        )

        if self._llm and hasattr(self._llm, "invoke_structured"):
            try:
                plan = await self._llm.invoke_structured(
                    prompt,
                    InvestigationQueryPlan,
                    max_tokens=self._config.token_budget_per_round,
                    temperature=0.2,
                )
                queries = [q.strip() for q in plan.queries if q.strip()]
                if queries:
                    return list(dict.fromkeys(queries))[:4]
            except Exception:
                logger.warning(
                    "LLM query generation failed, fallback to rule-based queries",
                    exc_info=True,
                )

        fallback: list[str] = []
        for gap in gaps[:2]:
            labels = " ".join(gap.get("labels", []))
            fallback.append(f"{labels} 最新进展 对比 证据")
            for suggestion in gap.get("suggestions", [])[:1]:
                fallback.append(suggestion)
        return list(dict.fromkeys(q.strip() for q in fallback if q.strip()))[:4]

    async def _execute_searches(self, queries: list[str]) -> list[dict[str, Any]]:
        """执行多源搜索并归一化结果。"""
        if not queries:
            return []

        results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        sources = set(self._config.search_sources)

        if "searxng" in sources and self._searxng is not None:
            for query in queries:
                try:
                    rows = await self._searxng.search(query, limit=5)
                except Exception:
                    logger.warning(
                        "SearXNG search failed: query=%s", query, exc_info=True
                    )
                    continue
                for row in rows:
                    url = (getattr(row, "url", "") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(
                        {
                            "title": getattr(row, "title", ""),
                            "url": url,
                            "snippet": getattr(row, "snippet", ""),
                            "source": "searxng",
                            "engine": getattr(row, "engine", ""),
                        }
                    )

        if "gdelt" in sources and self._gdelt is not None:
            for query in queries:
                try:
                    articles = await self._gdelt.search_articles(
                        query,
                        timespan=settings.gdelt_doc_timespan,
                        max_records=5,
                    )
                except Exception:
                    logger.warning(
                        "GDELT search failed: query=%s", query, exc_info=True
                    )
                    continue
                for article in articles:
                    url = (getattr(article, "url", "") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(
                        {
                            "title": getattr(article, "title", ""),
                            "url": url,
                            "snippet": getattr(article, "source_domain", ""),
                            "source": "gdelt",
                            "engine": "gdelt",
                        }
                    )

        return results

    async def _ingest_results(
        self,
        results: list[dict[str, Any]],
        *,
        case_uid: str,
        investigation_uid: str,
    ) -> list[str]:
        """把搜索结果入库并发出 claim.extracted。"""
        claim_uids: list[str] = []

        for result in results:
            url = (result.get("url") or "").strip()
            title = (result.get("title") or "").strip()
            snippet = (result.get("snippet") or "").strip()
            if not url and not title and not snippet:
                continue

            raw_text = "\n".join(part for part in (title, snippet, url) if part)
            if not raw_text:
                continue

            artifact_identity_uid = f"ai_{uuid.uuid4().hex}"
            artifact_version_uid = f"av_{uuid.uuid4().hex}"
            chunk_uid = f"chk_{uuid.uuid4().hex}"
            evidence_uid = f"ev_{uuid.uuid4().hex}"
            source_claim_uid = f"sc_{uuid.uuid4().hex}"

            self._db.add(
                ArtifactIdentity(
                    uid=artifact_identity_uid,
                    kind="url",
                    canonical_url=url or f"investigation://{source_claim_uid}",
                )
            )
            self._db.add(
                ArtifactVersion(
                    uid=artifact_version_uid,
                    artifact_identity_uid=artifact_identity_uid,
                    case_uid=case_uid,
                    content_sha256=uuid.uuid5(uuid.NAMESPACE_URL, raw_text).hex,
                    content_type="text/plain",
                    source_meta={
                        "source": result.get("source", "investigation"),
                        "engine": result.get("engine", ""),
                        "url": url,
                        "title": title,
                        "investigation_uid": investigation_uid,
                    },
                )
            )
            self._db.add(
                Chunk(
                    uid=chunk_uid,
                    artifact_version_uid=artifact_version_uid,
                    text=raw_text,
                    anchor_set=[
                        {
                            "type": "TextQuoteSelector",
                            "exact": title or snippet or raw_text,
                        },
                        {"type": "LinkSelector", "href": url},
                    ],
                    ordinal=0,
                )
            )
            self._db.add(
                Evidence(
                    uid=evidence_uid,
                    case_uid=case_uid,
                    artifact_version_uid=artifact_version_uid,
                    chunk_uid=chunk_uid,
                    kind="investigation_search",
                )
            )
            self._db.add(
                SourceClaim(
                    uid=source_claim_uid,
                    case_uid=case_uid,
                    artifact_version_uid=artifact_version_uid,
                    chunk_uid=chunk_uid,
                    evidence_uid=evidence_uid,
                    quote=title or snippet or raw_text[:200],
                    selectors=[
                        {
                            "type": "TextQuoteSelector",
                            "exact": title or snippet or raw_text,
                        },
                        {"type": "LinkSelector", "href": url},
                    ],
                    attributed_to=result.get("engine") or result.get("source"),
                    modality="alleged",
                )
            )
            claim_uids.append(source_claim_uid)

            if self._llm is not None and self._qdrant is not None:
                try:
                    await embed_and_index_chunk(
                        chunk_uid=chunk_uid,
                        text=raw_text,
                        llm=self._llm,
                        qdrant=self._qdrant,
                        metadata={
                            "case_uid": case_uid,
                            "source": result.get("source", "investigation"),
                            "investigation_uid": investigation_uid,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Investigation chunk embedding failed: chunk=%s",
                        chunk_uid,
                        exc_info=True,
                    )

        if not claim_uids:
            return []

        await self._db.flush()
        await self._db.commit()
        bus = get_event_bus()
        await bus.emit_and_wait(
            AegiEvent(
                event_type="claim.extracted",
                case_uid=case_uid,
                payload={
                    "summary": (
                        f"Investigation {investigation_uid} extracted "
                        f"{len(claim_uids)} claims"
                    ),
                    "source": "investigation",
                    "investigation_uid": investigation_uid,
                    "claim_count": len(claim_uids),
                    "claim_uids": claim_uids,
                },
                severity="low",
                source_event_uid=f"investigation:{investigation_uid}:{uuid.uuid4().hex}",
            )
        )
        return claim_uids

    async def _build_case_context(self, case_uid: str) -> str:
        self._db.expire_all()
        case = (
            await self._db.execute(sa.select(Case).where(Case.uid == case_uid))
        ).scalar_one_or_none()
        hypotheses = (
            (
                await self._db.execute(
                    sa.select(Hypothesis)
                    .where(Hypothesis.case_uid == case_uid)
                    .order_by(Hypothesis.posterior_probability.desc().nullslast())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )
        title = case.title if case else case_uid
        hyp_lines = [
            f"{hyp.uid}: {hyp.label} (posterior={hyp.posterior_probability or 0:.3f})"
            for hyp in hypotheses
        ]
        return f"Case={title}\nHypotheses:\n" + "\n".join(hyp_lines)

    async def _load_actionable_gaps(self, case_uid: str) -> list[dict[str, Any]]:
        self._db.expire_all()
        bayes = BayesianACH(self._db, self._llm)
        raw_gaps = await bayes.get_evidence_gaps(case_uid)
        gaps = [
            {
                **gap,
                "summary": " / ".join(gap.get("suggestions", [])[:2]),
            }
            for gap in raw_gaps
            if float(gap.get("posterior_diff", 1.0)) < self._config.min_posterior_diff
        ]
        return gaps

    async def _load_posteriors(self, case_uid: str) -> dict[str, float]:
        self._db.expire_all()
        rows = (
            await self._db.execute(
                sa.select(Hypothesis.uid, Hypothesis.posterior_probability).where(
                    Hypothesis.case_uid == case_uid
                )
            )
        ).all()
        return {uid: float(prob or 0.0) for uid, prob in rows}

    @staticmethod
    def _posterior_change(
        *,
        before: dict[str, float],
        after: dict[str, float],
    ) -> float:
        keys = set(before.keys()) | set(after.keys())
        if not keys:
            return 0.0
        return max(abs(after.get(uid, 0.0) - before.get(uid, 0.0)) for uid in keys)

    async def _persist_progress(
        self,
        *,
        investigation_uid: str,
        rounds: list[InvestigationRound],
        total_claims: int,
    ) -> None:
        row = await self._db.get(Investigation, investigation_uid)
        if row is None:
            return
        row.rounds = [asdict(item) for item in rounds]
        row.total_claims_extracted = total_claims
        await self._db.commit()

    async def _mark_completed(
        self,
        *,
        investigation_uid: str,
        rounds: list[InvestigationRound],
        total_claims: int,
        gap_resolved: bool,
    ) -> None:
        row = await self._db.get(Investigation, investigation_uid)
        if row is None:
            return
        row.status = "completed"
        row.rounds = [asdict(item) for item in rounds]
        row.total_claims_extracted = total_claims
        row.gap_resolved = gap_resolved
        row.completed_at = utcnow()
        await self._db.commit()

    async def _mark_failed(
        self,
        *,
        investigation_uid: str,
        rounds: list[InvestigationRound],
        total_claims: int,
    ) -> None:
        row = await self._db.get(Investigation, investigation_uid)
        if row is None:
            return
        row.status = "failed"
        row.rounds = [asdict(item) for item in rounds]
        row.total_claims_extracted = total_claims
        row.completed_at = utcnow()
        await self._db.commit()

    async def _mark_cancelled(
        self,
        investigation_uid: str,
        *,
        rounds: list[InvestigationRound],
        total_claims: int,
    ) -> None:
        row = await self._db.get(Investigation, investigation_uid)
        if row is None:
            return
        row.status = "cancelled"
        row.rounds = [asdict(item) for item in rounds]
        row.total_claims_extracted = total_claims
        row.completed_at = row.completed_at or utcnow()
        row.cancelled_by = row.cancelled_by or "system"
        await self._db.commit()

    async def _notify_case_subscribers(self, *, case_uid: str, message: str) -> None:
        user_rows = (
            await self._db.execute(
                sa.select(sa.distinct(Subscription.user_id)).where(
                    Subscription.enabled.is_(True),
                    sa.or_(
                        sa.and_(
                            Subscription.sub_type == "case",
                            Subscription.sub_target == case_uid,
                        ),
                        Subscription.sub_type == "global",
                    ),
                )
            )
        ).all()
        user_ids = [row[0] for row in user_rows if row and row[0]]
        if not user_ids:
            return

        from aegi_core.openclaw.dispatch import notify_user

        for user_id in user_ids:
            try:
                await notify_user(user_id, message, label="investigation")
            except Exception:
                logger.warning(
                    "Investigation notify_user failed: user=%s case=%s",
                    user_id,
                    case_uid,
                    exc_info=True,
                )


def create_investigation_handler(
    *,
    llm: Any,
    searxng: Any,
    gdelt: Any,
    qdrant: Any = None,
) -> Any:
    """创建 hypothesis.updated 事件处理器。"""
    from aegi_core.db.session import ENGINE

    state_lock = asyncio.Lock()
    running_cases: set[str] = set()
    cooldown_until: dict[str, datetime] = {}
    semaphore = asyncio.Semaphore(max(1, settings.investigation_max_concurrent))

    async def investigation_handler(event: AegiEvent) -> None:
        if event.event_type != "hypothesis.updated":
            return
        if not settings.investigation_enabled:
            return

        case_uid = event.case_uid
        if not case_uid:
            return

        max_change = float(event.payload.get("max_change", 0.0) or 0.0)
        config = build_investigation_config()
        if max_change < config.min_change_threshold:
            return

        now = datetime.now(timezone.utc)
        async with state_lock:
            if case_uid in running_cases:
                logger.debug(
                    "Investigation skipped: case already running (%s)", case_uid
                )
                return
            cooldown_end = cooldown_until.get(case_uid)
            if cooldown_end and now < cooldown_end:
                logger.debug("Investigation skipped by cooldown: case=%s", case_uid)
                return
            running_cases.add(case_uid)
            cooldown_until[case_uid] = now + timedelta(seconds=config.cooldown_seconds)

        try:
            async with semaphore:
                async with AsyncSession(ENGINE, expire_on_commit=False) as session:
                    agent = InvestigationAgent(
                        session,
                        llm=llm,
                        searxng=searxng,
                        gdelt_client=gdelt,
                        qdrant=qdrant,
                        config=config,
                    )
                    await agent.investigate(case_uid=case_uid, trigger_event=event)
        finally:
            async with state_lock:
                running_cases.discard(case_uid)

    investigation_handler.__name__ = "investigation_handler"
    return investigation_handler
