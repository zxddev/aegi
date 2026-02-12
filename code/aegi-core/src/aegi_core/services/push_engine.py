"""AEGI 事件驱动层的推送决策引擎。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.services.event_bus import AegiEvent, SEVERITY_RANK

logger = logging.getLogger(__name__)


@dataclass
class PushCandidate:
    """单条匹配结果。"""

    user_id: str
    subscription_uid: str | None
    match_method: str  # rule | semantic | llm
    match_score: float  # 0.0 ~ 1.0
    match_reason: str


class PushEngine:
    """推送决策引擎。

    1. 规则匹配 — 查询 subscriptions 表
    2. 语义匹配 — 事件 embedding vs 专家画像 embedding (Qdrant)
    3. 合并去重
    4. 限流检查
    5. LLM 重排序（可选，暂未实现）
    6. 投递 — 调用 dispatch.notify_user()
    """

    def __init__(
        self,
        db_session: AsyncSession,
        *,
        qdrant: Any | None = None,
        llm: Any | None = None,
        max_push_per_hour: int = 10,
        semantic_threshold: float = 0.65,
    ) -> None:
        self._db = db_session
        self._qdrant = qdrant  # 独立的 QdrantStore，用于 expert_profiles
        self._llm = llm
        self._max_push_per_hour = max_push_per_hour
        self._semantic_threshold = semantic_threshold

    async def process_event(self, event: AegiEvent) -> int:
        """处理一个事件，返回实际推送数。"""
        from aegi_core.db.models.event_log import EventLog

        # 1. 去重：检查 source_event_uid
        existing = (
            await self._db.execute(
                sa.select(EventLog.uid).where(
                    EventLog.source_event_uid == event.source_event_uid
                )
            )
        ).scalar_one_or_none()
        if existing:
            logger.debug("事件 %s 已处理过，跳过", event.source_event_uid)
            return 0

        # 2. 持久化事件
        event_uid = uuid.uuid4().hex
        row = EventLog(
            uid=event_uid,
            event_type=event.event_type,
            case_uid=event.case_uid,
            payload=event.payload,
            entities=event.entities,
            regions=event.regions,
            topics=event.topics,
            severity=event.severity,
            source_event_uid=event.source_event_uid,
            status="processing",
        )
        self._db.add(row)
        await self._db.flush()

        # 3. 规则匹配
        candidates = await self._rule_match(event)

        # 4. 语义匹配
        if self._qdrant and self._llm:
            sem_candidates = await self._semantic_match(event)
            candidates.extend(sem_candidates)

        # 5. 合并去重（同一 user_id → 保留最高分）
        merged = self._merge_candidates(candidates)

        # 6. 限流 + 投递
        pushed = 0
        for cand in merged:
            throttled = await self._is_throttled(cand.user_id, event.severity)
            status = "throttled" if throttled else "delivered"
            error = None

            if not throttled:
                try:
                    await self._deliver(cand.user_id, event)
                    pushed += 1
                except Exception as exc:
                    status = "failed"
                    error = str(exc)
                    logger.warning("推送失败 user %s: %s", cand.user_id, exc)

            # 7. 记录推送日志
            await self._record_push(
                event_uid=event_uid,
                candidate=cand,
                status=status,
                error=error,
            )

        # 更新事件状态
        row.status = "done"
        row.push_count = pushed
        await self._db.commit()
        return pushed

    # ── 规则匹配 ────────────────────────────────────────────────

    async def _rule_match(self, event: AegiEvent) -> list[PushCandidate]:
        from aegi_core.db.models.subscription import Subscription

        severity_rank = SEVERITY_RANK.get(event.severity, 1)

        conditions = [
            sa.and_(
                Subscription.sub_type == "case",
                Subscription.sub_target == event.case_uid,
            ),
            Subscription.sub_type == "global",
        ]
        if event.entities:
            conditions.append(
                sa.and_(
                    Subscription.sub_type == "entity",
                    Subscription.sub_target.in_(event.entities),
                )
            )
        if event.regions:
            conditions.append(
                sa.and_(
                    Subscription.sub_type == "region",
                    Subscription.sub_target.in_(event.regions),
                )
            )
        if event.topics:
            conditions.append(
                sa.and_(
                    Subscription.sub_type == "topic",
                    Subscription.sub_target.in_(event.topics),
                )
            )

        stmt = sa.select(Subscription).where(
            Subscription.enabled == True,  # noqa: E712
            Subscription.priority_threshold <= severity_rank,
            sa.or_(*conditions),
        )
        rows = (await self._db.execute(stmt)).scalars().all()

        candidates = []
        for sub in rows:
            if sub.event_types and event.event_type not in sub.event_types:
                continue
            reason = f"{sub.sub_type}:{sub.sub_target}"
            candidates.append(
                PushCandidate(
                    user_id=sub.user_id,
                    subscription_uid=sub.uid,
                    match_method="rule",
                    match_score=1.0,
                    match_reason=reason,
                )
            )
        return candidates

    # ── 语义匹配（独立 QdrantStore）────

    async def _semantic_match(self, event: AegiEvent) -> list[PushCandidate]:
        """用事件摘要 embedding 在 Qdrant 的 expert_profiles 集合中搜索。"""
        summary = f"[{event.event_type}] {event.payload.get('summary', '')}"
        if event.entities:
            summary += f" entities: {', '.join(event.entities[:5])}"
        if event.topics:
            summary += f" topics: {', '.join(event.topics[:5])}"

        try:
            embedding = await self._llm.embed(summary)
        except Exception:
            logger.warning("事件摘要 embedding 失败，跳过语义匹配")
            return []

        results = await self._qdrant.search(
            query_embedding=embedding,
            limit=20,
            score_threshold=self._semantic_threshold,
        )

        candidates = []
        for hit in results:
            user_id = hit.metadata.get("user_id", "")
            if not user_id:
                continue
            candidates.append(
                PushCandidate(
                    user_id=user_id,
                    subscription_uid=hit.metadata.get("subscription_uid"),
                    match_method="semantic",
                    match_score=hit.score,
                    match_reason=f"semantic similarity={hit.score:.3f}",
                )
            )
        return candidates

    # ── 合并、限流、投递 ──────────────────────────────────

    @staticmethod
    def _merge_candidates(candidates: list[PushCandidate]) -> list[PushCandidate]:
        best: dict[str, PushCandidate] = {}
        for c in candidates:
            existing = best.get(c.user_id)
            if existing is None or c.match_score > existing.match_score:
                best[c.user_id] = c
        return list(best.values())

    async def _is_throttled(self, user_id: str, severity: str) -> bool:
        if severity == "critical":
            return False
        from aegi_core.db.models.push_log import PushLog

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count = (
            await self._db.execute(
                sa.select(sa.func.count())
                .select_from(PushLog)
                .where(
                    PushLog.user_id == user_id,
                    PushLog.status == "delivered",
                    PushLog.created_at >= one_hour_ago,
                )
            )
        ).scalar_one()
        return count >= self._max_push_per_hour

    async def _deliver(self, user_id: str, event: AegiEvent) -> None:
        """调用 dispatch.notify_user() 投递推送。"""
        from aegi_core.openclaw.dispatch import notify_user

        summary = event.payload.get("summary", event.event_type)
        message = f"[{event.severity.upper()}] {summary}"
        if event.case_uid:
            message += f"\n案例: {event.case_uid}"

        await notify_user(user_id, message, label="event_push")

    async def _record_push(
        self,
        *,
        event_uid: str,
        candidate: PushCandidate,
        status: str,
        error: str | None,
    ) -> None:
        from aegi_core.db.models.push_log import PushLog

        row = PushLog(
            uid=uuid.uuid4().hex,
            event_uid=event_uid,
            user_id=candidate.user_id,
            subscription_uid=candidate.subscription_uid,
            match_method=candidate.match_method,
            match_score=candidate.match_score,
            match_reason=candidate.match_reason,
            status=status,
            error=error,
        )
        self._db.add(row)


# ── 工厂：为 EventBus 创建 EventHandler ─────────────────────


def create_push_handler(
    *,
    qdrant: Any | None = None,
    llm: Any | None = None,
) -> Callable[[AegiEvent], Awaitable[None]]:
    """创建 EventHandler，每个事件获取独立 DB session。"""
    from aegi_core.settings import settings

    async def handler(event: AegiEvent) -> None:
        from aegi_core.db.session import ENGINE

        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            engine = PushEngine(
                session,
                qdrant=qdrant,
                llm=llm,
                max_push_per_hour=settings.event_push_max_per_hour,
                semantic_threshold=settings.event_push_semantic_threshold,
            )
            pushed = await engine.process_event(event)
            logger.info(
                "PushEngine: event=%s case=%s 推送=%d",
                event.event_type,
                event.case_uid,
                pushed,
            )

    handler.__name__ = "push_engine_handler"
    return handler
