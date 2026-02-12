# Author: msq
"""GDELT Monitor 服务单元测试（mock client + DB）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.gdelt_client import GDELTArticle
from aegi_core.services.gdelt_monitor import GDELTMonitor, _parse_seendate, _gdelt_id


# ── 辅助 ──────────────────────────────────────────────────────


def _make_article(
    url: str = "https://example.com/a1",
    title: str = "Test Article",
    **kwargs,
) -> GDELTArticle:
    return GDELTArticle(
        url=url,
        title=title,
        source_domain=kwargs.get("source_domain", "example.com"),
        language=kwargs.get("language", "English"),
        seendate=kwargs.get("seendate", "20260211T120000Z"),
        tone=kwargs.get("tone", -1.0),
        domain_country=kwargs.get("domain_country", "US"),
    )


def _make_subscription(
    uid: str = "sub_1",
    sub_type: str = "topic",
    sub_target: str = "ukraine",
    event_types: list[str] | None = None,
    interest_text: str | None = None,
    match_rules: dict | None = None,
) -> SimpleNamespace:
    """用 SimpleNamespace 模拟 Subscription，避免 SQLAlchemy instrumentation。"""
    return SimpleNamespace(
        uid=uid,
        user_id="user_1",
        sub_type=sub_type,
        sub_target=sub_target,
        event_types=event_types or [],
        interest_text=interest_text,
        match_rules=match_rules or {},
        enabled=True,
        priority_threshold=0,
        embedding_synced=False,
    )


def _make_gdelt_event(**overrides) -> SimpleNamespace:
    """用 SimpleNamespace 模拟 GdeltEvent。"""
    defaults = dict(
        uid="ge_test",
        gdelt_id="abc123",
        case_uid=None,
        title="Test",
        url="https://example.com/test",
        source_domain="example.com",
        language="English",
        published_at=None,
        cameo_code=None,
        goldstein_scale=None,
        actor1=None,
        actor2=None,
        geo_country="US",
        geo_name=None,
        tone=-1.0,
        status="new",
        matched_subscription_uids=["sub_1"],
        raw_data={},
        created_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── 测试 ──────────────────────────────────────────────────────


def test_parse_seendate_normal() -> None:
    dt = _parse_seendate("20260211T153000Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 11
    assert dt.hour == 15


def test_parse_seendate_empty() -> None:
    assert _parse_seendate("") is None


def test_gdelt_id_deterministic() -> None:
    id1 = _gdelt_id("https://example.com/a")
    id2 = _gdelt_id("https://example.com/a")
    assert id1 == id2
    assert len(id1) == 32


@pytest.mark.asyncio
async def test_poll_discovers_new_events() -> None:
    """有订阅 + 有文章 → 创建 GdeltEvent。"""
    mock_client = AsyncMock()
    mock_client.search_articles = AsyncMock(
        return_value=[
            _make_article(title="Ukraine conflict update"),
        ]
    )

    mock_session = AsyncMock()
    sub = _make_subscription(sub_type="topic", sub_target="ukraine")

    sub_result = MagicMock()
    sub_result.scalars.return_value.all.return_value = [sub]

    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(side_effect=[sub_result, dedup_result])

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
        events = await monitor.poll()

    assert len(events) == 1
    assert events[0].title == "Ukraine conflict update"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_poll_deduplicates() -> None:
    """已存在的文章 → 跳过。"""
    mock_client = AsyncMock()
    mock_client.search_articles = AsyncMock(
        return_value=[
            _make_article(url="https://example.com/dup"),
        ]
    )

    mock_session = AsyncMock()
    sub = _make_subscription()

    sub_result = MagicMock()
    sub_result.scalars.return_value.all.return_value = [sub]

    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = "ge_existing"

    mock_session.execute = AsyncMock(side_effect=[sub_result, dedup_result])

    monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
    events = await monitor.poll()

    assert len(events) == 0
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_poll_matches_subscriptions() -> None:
    """文章标题包含 sub_target → matched_subscription_uids 非空。"""
    mock_client = AsyncMock()
    mock_client.search_articles = AsyncMock(
        return_value=[
            _make_article(title="Ukraine peace talks resume"),
        ]
    )

    mock_session = AsyncMock()
    sub = _make_subscription(uid="sub_ukr", sub_type="topic", sub_target="ukraine")

    sub_result = MagicMock()
    sub_result.scalars.return_value.all.return_value = [sub]

    dedup_result = MagicMock()
    dedup_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(side_effect=[sub_result, dedup_result])
    mock_session.add = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus_fn.return_value = AsyncMock()
        monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
        events = await monitor.poll()

    assert len(events) == 1
    assert "sub_ukr" in events[0].matched_subscription_uids


@pytest.mark.asyncio
async def test_poll_matches_subscriptions_by_match_rules() -> None:
    """match_rules.keywords/countries 任一命中即匹配。"""
    mock_client = AsyncMock()
    mock_client.search_articles = AsyncMock(
        return_value=[
            _make_article(
                title="Iran nuclear update",
                domain_country="IR",
            ),
        ]
    )

    mock_session = AsyncMock()
    sub = _make_subscription(
        uid="sub_rule",
        sub_type="topic",
        sub_target="*",
        match_rules={"keywords": ["nuclear"], "countries": ["IR"]},
    )

    sub_result = AsyncMock()
    sub_result.scalars.return_value.all.return_value = [sub]

    dedup_result = AsyncMock()
    dedup_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(side_effect=[sub_result, dedup_result])
    mock_session.add = AsyncMock()
    mock_session.commit = AsyncMock()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus_fn.return_value = AsyncMock()
        monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
        events = await monitor.poll()

    assert len(events) == 1
    assert "sub_rule" in events[0].matched_subscription_uids


@pytest.mark.asyncio
async def test_poll_no_subscriptions_skips() -> None:
    """无订阅 → 直接返回空。"""
    mock_client = AsyncMock()
    mock_session = AsyncMock()

    sub_result = MagicMock()
    sub_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=sub_result)

    monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
    events = await monitor.poll()

    assert events == []
    mock_client.search_articles.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_event_emits_claim_extracted() -> None:
    """ingest_event → 生成 Evidence/SourceClaim + emit claim.extracted。"""
    mock_client = AsyncMock()
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    ev = _make_gdelt_event()

    with patch("aegi_core.services.gdelt_monitor.get_event_bus") as mock_bus_fn:
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        monitor = GDELTMonitor(gdelt=mock_client, db_session=mock_session)
        await monitor.ingest_event(ev, "case_123")

    assert ev.status == "ingested"
    assert ev.case_uid == "case_123"
    assert mock_session.add.call_count == 5
    added_rows = [c.args[0] for c in mock_session.add.call_args_list]
    assert any(isinstance(row, ArtifactIdentity) for row in added_rows)
    assert any(isinstance(row, ArtifactVersion) for row in added_rows)
    assert any(isinstance(row, Chunk) for row in added_rows)
    assert any(isinstance(row, Evidence) for row in added_rows)
    assert any(isinstance(row, SourceClaim) for row in added_rows)
    mock_session.flush.assert_called_once()

    mock_bus.emit.assert_called_once()
    emitted = mock_bus.emit.call_args[0][0]
    assert emitted.event_type == "claim.extracted"
    assert emitted.case_uid == "case_123"
    assert emitted.payload["claim_count"] == 1
    assert len(emitted.payload["claim_uids"]) == 1
