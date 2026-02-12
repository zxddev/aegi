"""OSINT 采集服务测试 — 所有外部依赖都用 mock。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegi_core.infra.searxng_client import SearchResult
from aegi_core.services.osint_collector import (
    CollectionResult,
    OSINTCollector,
    search_preview,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_search_results(n: int = 2) -> list[SearchResult]:
    return [
        SearchResult(
            title=f"Result {i}",
            url=f"https://example{i}.com/article/{i}",
            snippet=f"Snippet for result {i}",
            engine="google",
        )
        for i in range(n)
    ]


def _make_mock_db_session() -> AsyncMock:
    """创建一个 mock 异步 DB session，带 execute/flush/add/commit。"""
    session = AsyncMock()

    # execute() 返回的 result proxy 的 scalar_one_or_none() 返回 None
    # （没找到重复）
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_search_and_ingest():
    """Mock SearXNG 返回 2 条结果，验证 urls_found 和 urls_ingested。"""
    searxng = AsyncMock()
    searxng.search = AsyncMock(return_value=_make_search_results(2))

    llm = AsyncMock()
    qdrant = AsyncMock()
    db_session = _make_mock_db_session()

    collector = OSINTCollector(
        searxng=searxng,
        llm=llm,
        qdrant=qdrant,
        db_session=db_session,
    )

    # Mock _process_url 模拟成功入库
    async def fake_process_url(sr, case_uid, result):
        result.urls_ingested += 1
        av_uid = f"av_fake_{sr.url}"
        result.artifact_version_uids.append(av_uid)
        return av_uid

    # Mock _extract_claims_for_artifact 返回空（不需要 LLM）
    async def fake_extract_claims(av_uid, case_uid):
        return []

    with (
        patch.object(collector, "_process_url", side_effect=fake_process_url),
        patch.object(
            collector, "_extract_claims_for_artifact", side_effect=fake_extract_claims
        ),
    ):
        result = await collector.collect("test query", "case_001")

    await collector.close()

    assert result.urls_found == 2
    assert result.urls_ingested == 2
    assert len(result.artifact_version_uids) == 2


@pytest.mark.asyncio
async def test_collect_empty_search():
    """SearXNG 返回空列表 -> result.urls_found == 0。"""
    searxng = AsyncMock()
    searxng.search = AsyncMock(return_value=[])

    db_session = _make_mock_db_session()

    collector = OSINTCollector(
        searxng=searxng,
        llm=None,
        qdrant=None,
        db_session=db_session,
    )
    result = await collector.collect("empty query", "case_002")
    await collector.close()

    assert result.urls_found == 0
    assert result.urls_ingested == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_search_preview():
    """Mock SearXNG，验证输出里有可信度评分。"""
    searxng = AsyncMock()
    searxng.search = AsyncMock(
        return_value=[
            SearchResult(
                title="Reuters Article",
                url="https://www.reuters.com/world/article",
                snippet="Breaking news",
                engine="google",
            ),
            SearchResult(
                title="Random Blog",
                url="https://random.xyz/blog/post",
                snippet="Some blog post",
                engine="bing",
            ),
        ]
    )

    results = await search_preview(searxng, "test query", limit=5)

    assert len(results) == 2

    # 第一条: reuters.com -> 高可信度
    assert results[0]["title"] == "Reuters Article"
    assert results[0]["credibility"]["domain"] == "reuters.com"
    assert results[0]["credibility"]["score"] == 0.9
    assert results[0]["credibility"]["tier"] == "high"

    # 第二条: random.xyz -> 未知
    assert results[1]["credibility"]["domain"] == "random.xyz"
    assert results[1]["credibility"]["score"] == 0.5
    assert results[1]["credibility"]["tier"] == "unknown"


@pytest.mark.asyncio
async def test_collect_fetch_error_graceful():
    """Mock _process_url 抛异常，验证错误被捕获但不崩溃。"""
    searxng = AsyncMock()
    searxng.search = AsyncMock(return_value=_make_search_results(1))

    db_session = _make_mock_db_session()

    collector = OSINTCollector(
        searxng=searxng,
        llm=None,
        qdrant=None,
        db_session=db_session,
    )

    # 让 _process_url 抛异常
    async def failing_process_url(sr, case_uid, result):
        raise ConnectionError("Network timeout")

    with patch.object(collector, "_process_url", side_effect=failing_process_url):
        result = await collector.collect("failing query", "case_003")

    await collector.close()

    assert result.urls_found == 1
    assert result.urls_ingested == 0
    assert len(result.errors) == 1
    assert "Network timeout" in result.errors[0]
