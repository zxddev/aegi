# Author: msq
"""GDELT 监控服务。

定期轮询 GDELT DOC API，发现新文章后去重入库并 emit 事件。
关键词来源于 Subscription 的 sub_target / interest_text。
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.gdelt_event import GdeltEvent
from aegi_core.db.models.subscription import Subscription
from aegi_core.infra.gdelt_client import GDELTArticle, GDELTClient
from aegi_core.services.event_bus import AegiEvent, get_event_bus

logger = logging.getLogger(__name__)


def _parse_seendate(s: str) -> datetime | None:
    """解析 GDELT seendate 格式，如 '20260211T153000Z'。"""
    s = s.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # 备选：纯日期
    try:
        return datetime.strptime(s[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _gdelt_id(url: str) -> str:
    """URL → sha256 前 32 字符作为去重 ID。"""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _split_interest(text: str | None) -> list[str]:
    """将 interest_text 按逗号/空格分割为关键词列表。"""
    if not text:
        return []
    return [w.strip() for w in re.split(r"[,\s]+", text) if w.strip()]


def _extract_match_rule_list(
    sub: Subscription,
    key: str,
) -> list[str]:
    """从 Subscription.match_rules 中提取字符串列表。"""
    rules = getattr(sub, "match_rules", None)
    if not isinstance(rules, dict):
        return []
    values = rules.get(key, [])
    if not isinstance(values, list):
        return []
    return [v.strip() for v in values if isinstance(v, str) and v.strip()]


async def _maybe_await(value: Any) -> Any:
    """兼容真实 SQLAlchemy 返回值和测试中 AsyncMock 返回值。"""
    if inspect.isawaitable(value):
        return await value
    return value


class GDELTMonitor:
    """GDELT 轮询监控器。"""

    def __init__(
        self,
        gdelt: GDELTClient,
        db_session: AsyncSession | None,
    ) -> None:
        self._gdelt = gdelt
        self._db = db_session

    async def poll(self) -> list[GdeltEvent]:
        """执行一次轮询，若未绑定 session 则内部临时创建。"""
        if self._db is not None:
            return await self._poll_once(self._db)

        from aegi_core.db.session import ENGINE

        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            return await self._poll_once(session)

    def _require_db_session(self) -> AsyncSession:
        if self._db is None:
            raise RuntimeError("GDELTMonitor requires a bound db session")
        return self._db

    async def _poll_once(self, db: AsyncSession) -> list[GdeltEvent]:
        """执行一次轮询：加载订阅 → 搜索 → 去重 → 入库 → emit 事件。"""
        subs = await self._load_subscriptions(db)
        if not subs:
            logger.info("GDELT poll: 无匹配订阅，跳过")
            return []

        # 提取搜索关键词和国家过滤
        keywords: list[str] = []
        countries: list[str] = []
        for sub in subs:
            match_rule_keywords = _extract_match_rule_list(sub, "keywords")
            match_rule_countries = _extract_match_rule_list(sub, "countries")

            keywords.extend(match_rule_keywords)
            countries.extend(match_rule_countries)

            # 向后兼容现有 sub_type/sub_target 方案
            if sub.sub_type == "topic" and sub.sub_target and sub.sub_target != "*":
                keywords.append(sub.sub_target)
            if sub.sub_type == "region" and sub.sub_target and sub.sub_target != "*":
                countries.append(sub.sub_target)
            keywords.extend(_split_interest(sub.interest_text))

        # 去重关键词
        keywords = list(dict.fromkeys(k for k in keywords if k))
        if not keywords and not countries:
            logger.info("GDELT poll: 无有效关键词，跳过")
            return []

        # 逐关键词搜索
        all_articles: list[GDELTArticle] = []
        from aegi_core.settings import settings

        for kw in keywords:
            articles = await self._gdelt.search_articles(
                kw,
                max_records=settings.gdelt_max_articles_per_query,
            )
            all_articles.extend(articles)
            if len(keywords) > 1:
                await asyncio.sleep(5)

        # 按国家搜索（用通配关键词 + sourcecountry 过滤）
        for country in countries:
            articles = await self._gdelt.search_articles(
                "*",
                source_country=country,
                max_records=settings.gdelt_max_articles_per_query,
            )
            all_articles.extend(articles)
            await asyncio.sleep(5)

        # 去重 + 入库
        new_events: list[GdeltEvent] = []
        seen_ids: set[str] = set()

        for article in all_articles:
            if not article.url:
                continue
            gid = _gdelt_id(article.url)
            if gid in seen_ids:
                continue
            seen_ids.add(gid)

            # DB 去重
            existing = await _maybe_await(
                (
                    await db.execute(
                        select(GdeltEvent.uid).where(GdeltEvent.gdelt_id == gid)
                    )
                ).scalar_one_or_none()
            )
            if existing:
                continue

            matched_uids = self._match_subscriptions(article, subs)
            published = _parse_seendate(article.seendate)

            from uuid import uuid4

            event = GdeltEvent(
                uid=uuid4().hex,
                gdelt_id=gid,
                title=article.title,
                url=article.url,
                source_domain=article.source_domain,
                language=article.language,
                published_at=published,
                tone=article.tone if article.tone else None,
                geo_country=article.domain_country or None,
                status="new",
                matched_subscription_uids=matched_uids,
                raw_data={
                    "socialimage": article.socialimage,
                    "domain_country": article.domain_country,
                },
            )
            await _maybe_await(db.add(event))
            new_events.append(event)

        if new_events:
            await db.commit()
            # emit 事件
            bus = get_event_bus()
            for ev in new_events:
                await bus.emit(
                    AegiEvent(
                        event_type="gdelt.event_detected",
                        case_uid=ev.case_uid or "",
                        payload={
                            "gdelt_event_uid": ev.uid,
                            "title": ev.title,
                            "url": ev.url,
                            "source_domain": ev.source_domain,
                            "tone": ev.tone,
                        },
                        regions=[ev.geo_country] if ev.geo_country else [],
                    )
                )

        logger.info("GDELT poll: 发现 %d 篇新文章", len(new_events))
        return new_events

    async def ingest_event(self, event: GdeltEvent, case_uid: str) -> None:
        """将 GDELT 事件转为 Evidence + SourceClaim，并 emit claim.extracted。"""
        from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
        from aegi_core.db.models.chunk import Chunk
        from aegi_core.db.models.evidence import Evidence
        from aegi_core.db.models.source_claim import SourceClaim

        db = self._require_db_session()

        try:
            raw_text = f"{event.title}\n{event.url}".strip()
            content_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            artifact_identity_uid = uuid4().hex
            artifact_version_uid = uuid4().hex
            chunk_uid = uuid4().hex
            evidence_uid = uuid4().hex
            source_claim_uid = uuid4().hex

            await _maybe_await(
                db.add(
                    ArtifactIdentity(
                        uid=artifact_identity_uid,
                        kind="url",
                        canonical_url=event.url,
                    )
                )
            )
            await _maybe_await(
                db.add(
                    ArtifactVersion(
                        uid=artifact_version_uid,
                        artifact_identity_uid=artifact_identity_uid,
                        case_uid=case_uid,
                        content_sha256=content_sha,
                        content_type="text/plain",
                        source_meta={
                            "source": "gdelt",
                            "gdelt_event_uid": event.uid,
                            "url": event.url,
                            "title": event.title,
                            "source_domain": event.source_domain,
                            "language": event.language,
                        },
                    )
                )
            )
            await _maybe_await(
                db.add(
                    Chunk(
                        uid=chunk_uid,
                        artifact_version_uid=artifact_version_uid,
                        ordinal=0,
                        text=raw_text,
                        anchor_set=[
                            {"type": "TextQuoteSelector", "exact": event.title},
                            {"type": "LinkSelector", "href": event.url},
                        ],
                    )
                )
            )
            await _maybe_await(
                db.add(
                    Evidence(
                        uid=evidence_uid,
                        case_uid=case_uid,
                        artifact_version_uid=artifact_version_uid,
                        chunk_uid=chunk_uid,
                        kind="gdelt_article",
                    )
                )
            )
            await _maybe_await(
                db.add(
                    SourceClaim(
                        uid=source_claim_uid,
                        case_uid=case_uid,
                        artifact_version_uid=artifact_version_uid,
                        chunk_uid=chunk_uid,
                        evidence_uid=evidence_uid,
                        quote=event.title,
                        selectors=[
                            {"type": "TextQuoteSelector", "exact": event.title},
                            {"type": "LinkSelector", "href": event.url},
                        ],
                        attributed_to=event.source_domain or None,
                        modality="alleged",
                    )
                )
            )
            await _maybe_await(db.flush())

            event.case_uid = case_uid
            event.status = "ingested"
            await db.commit()

            bus = get_event_bus()
            await bus.emit(
                AegiEvent(
                    event_type="claim.extracted",
                    case_uid=case_uid,
                    payload={
                        "source": "gdelt",
                        "gdelt_event_uid": event.uid,
                        "title": event.title,
                        "url": event.url,
                        "claim_count": 1,
                        "claim_uids": [source_claim_uid],
                        "summary": f"Extracted 1 claim from gdelt event {event.uid}",
                        "chunk_uid": chunk_uid,
                    },
                )
            )
        except Exception as exc:
            logger.exception("GDELT ingest 失败: %s", exc)
            try:
                await db.rollback()
            except Exception:
                logger.exception("GDELT ingest 回滚失败")
            event.status = "error"
            await db.commit()
            raise

    async def _load_subscriptions(self, db: AsyncSession) -> list[Subscription]:
        """加载启用的、匹配 GDELT 事件类型的订阅。"""
        result = await db.execute(
            select(Subscription).where(Subscription.enabled.is_(True))
        )
        scalars = await _maybe_await(result.scalars())
        subs = list(await _maybe_await(scalars.all()))
        # 过滤：event_types 含 gdelt.event_detected 或为空
        return [
            s
            for s in subs
            if not s.event_types or "gdelt.event_detected" in s.event_types
        ]

    def _match_subscriptions(
        self,
        article: GDELTArticle,
        subs: list[Subscription],
    ) -> list[str]:
        """判断文章匹配哪些订阅，返回订阅 UID 列表。"""
        matched: list[str] = []
        title_lower = (article.title or "").lower()
        country = (article.domain_country or "").upper()

        for sub in subs:
            if sub.sub_type == "global":
                if sub.uid not in matched:
                    matched.append(sub.uid)
                continue

            keywords = _extract_match_rule_list(sub, "keywords")
            countries = [c.upper() for c in _extract_match_rule_list(sub, "countries")]

            # 向后兼容 sub_type/sub_target
            if sub.sub_type == "topic":
                target = (sub.sub_target or "").strip()
                if target and target != "*":
                    keywords.append(target)
            if sub.sub_type == "region":
                target = (sub.sub_target or "").upper()
                if target and target != "*":
                    countries.append(target)

            keywords.extend(_split_interest(sub.interest_text))

            keyword_hit = any(kw.lower() in title_lower for kw in keywords if kw)
            country_hit = any(c and c == country for c in countries)

            # 任一条件命中即匹配
            if keyword_hit or country_hit:
                if sub.uid not in matched:
                    matched.append(sub.uid)

        return matched
