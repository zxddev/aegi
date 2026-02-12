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

    def __init__(self, gdelt: GDELTClient, db_session: AsyncSession) -> None:
        self._gdelt = gdelt
        self._db = db_session

    async def poll(self) -> list[GdeltEvent]:
        """执行一次轮询：加载订阅 → 搜索 → 去重 → 入库 → emit 事件。"""
        subs = await self._load_subscriptions()
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
            existing = (
                await _maybe_await(
                    (
                        await self._db.execute(
                            select(GdeltEvent.uid).where(GdeltEvent.gdelt_id == gid)
                        )
                    ).scalar_one_or_none()
                )
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
            await _maybe_await(self._db.add(event))
            new_events.append(event)

        if new_events:
            await self._db.commit()
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
        """将 GDELT 事件标记为已 ingest 并 emit claim.extracted。

        Phase 1 骨架：仅更新状态 + emit 事件，实际 ingest 逻辑后续补充。
        """
        try:
            event.case_uid = case_uid
            event.status = "ingested"
            await self._db.commit()

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
                    },
                )
            )
        except Exception as exc:
            logger.error("GDELT ingest 失败: %s", exc)
            event.status = "error"
            await self._db.commit()
            raise

    async def _load_subscriptions(self) -> list[Subscription]:
        """加载启用的、匹配 GDELT 事件类型的订阅。"""
        result = await self._db.execute(
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
