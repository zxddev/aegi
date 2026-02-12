"""OSINT 集成测试 — 需要真实 SearXNG（端口 8888）。

跑真实 SearXNG 实例，验证完整 OSINT 管道。
SearXNG 不可用时自动跳过。
"""

import pytest

from conftest import requires_searxng, requires_postgres

pytestmark = [requires_searxng]


@pytest.fixture
def searxng():
    from aegi_core.infra.searxng_client import SearXNGClient

    return SearXNGClient(base_url="http://localhost:8888")


@pytest.mark.asyncio
async def test_searxng_search_real(searxng):
    """真实 SearXNG 搜索返回 SearchResult 列表。"""
    results = await searxng.search("Python programming", limit=3)
    assert isinstance(results, list)
    assert len(results) > 0
    r = results[0]
    assert r.title
    assert r.url.startswith("http")
    await searxng.close()


@pytest.mark.asyncio
async def test_search_preview_real(searxng):
    """search_preview 返回带可信度字段的结果。"""
    from aegi_core.services.osint_collector import search_preview

    previews = await searxng.search("OpenAI", limit=3)
    assert len(previews) > 0

    # 也测一下 search_preview 辅助函数
    results = await search_preview(searxng, "OpenAI", limit=3)
    assert len(results) > 0
    item = results[0]
    assert "credibility" in item
    assert "score" in item["credibility"]
    assert "tier" in item["credibility"]
    await searxng.close()


@pytest.mark.asyncio
async def test_document_parser_html_real(searxng):
    """抓取真实页面 -> parse_html -> chunk_text。"""
    import httpx
    from aegi_core.services.document_parser import parse_html, chunk_text

    results = await searxng.search("Python", limit=1)
    assert len(results) > 0
    url = results[0].url

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html_bytes = resp.content

    text = parse_html(html_bytes)
    assert len(text.strip()) > 0

    chunks = chunk_text(text)
    assert len(chunks) >= 1
    assert all(len(c) > 0 for c in chunks)
    await searxng.close()


@pytest.mark.asyncio
@pytest.mark.requires_postgres
async def test_osint_collect_real(searxng):
    """完整 OSINT 采集管道（SearXNG + PG，不用 LLM/Qdrant）。"""
    from aegi_core.db.session import get_engine
    from aegi_core.services.osint_collector import OSINTCollector
    from aegi_core.db.models.case import Case
    from sqlalchemy.ext.asyncio import AsyncSession
    from uuid import uuid4

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        case_uid = f"case_test_{uuid4().hex[:8]}"
        session.add(Case(uid=case_uid, title="OSINT integration test"))
        await session.flush()

        collector = OSINTCollector(
            searxng=searxng,
            llm=None,
            qdrant=None,
            db_session=session,
        )
        try:
            result = await collector.collect(
                "Python programming language",
                case_uid,
                max_results=2,
                extract_claims=False,
            )
            assert result.urls_found > 0
            assert result.urls_found >= result.urls_ingested
        finally:
            await collector.close()
            await session.rollback()
    await searxng.close()
