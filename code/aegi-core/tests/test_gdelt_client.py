# Author: msq
"""GDELT DOC API 客户端单元测试（mock HTTP）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import httpx

from aegi_core.infra.gdelt_client import GDELTClient


@pytest.fixture
def gdelt_client() -> GDELTClient:
    return GDELTClient(proxy=None)


@pytest.mark.asyncio
async def test_search_articles_success(gdelt_client: GDELTClient) -> None:
    """正常 JSON 响应 → 解析出文章列表。"""
    mock_resp = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://example.com/article1",
                    "title": "Test Article",
                    "domain": "example.com",
                    "language": "English",
                    "seendate": "20260211T120000Z",
                    "socialimage": "",
                    "tone": -2.5,
                    "sourcecountry": "US",
                },
            ],
        },
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    articles = await gdelt_client.search_articles("test query")
    assert len(articles) == 1
    assert articles[0].title == "Test Article"
    assert articles[0].url == "https://example.com/article1"
    assert articles[0].source_domain == "example.com"
    assert articles[0].tone == -2.5
    assert articles[0].domain_country == "US"


@pytest.mark.asyncio
async def test_search_articles_empty(gdelt_client: GDELTClient) -> None:
    """空结果 → 返回空列表。"""
    mock_resp = httpx.Response(200, json={"articles": []})
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    articles = await gdelt_client.search_articles("nothing")
    assert articles == []


@pytest.mark.asyncio
async def test_search_articles_malformed_json(gdelt_client: GDELTClient) -> None:
    """畸形 JSON → 容错返回空列表。"""
    mock_resp = httpx.Response(200, content=b"not json at all")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    articles = await gdelt_client.search_articles("bad")
    assert articles == []


@pytest.mark.asyncio
async def test_search_articles_timeout(gdelt_client: GDELTClient) -> None:
    """超时 → 容错返回空列表。"""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    articles = await gdelt_client.search_articles("slow")
    assert articles == []


@pytest.mark.asyncio
async def test_search_articles_with_filters(gdelt_client: GDELTClient) -> None:
    """source_country / source_lang 拼接到 query 参数。"""
    captured_kwargs: dict = {}

    async def capture_get(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return httpx.Response(200, json={"articles": []})

    mock_client = AsyncMock()
    mock_client.get = capture_get
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    await gdelt_client.search_articles(
        "ukraine",
        source_country="UA",
        source_lang="English",
    )

    params = captured_kwargs.get("params", {})
    query_val = params.get("query", "")
    assert "sourcecountry:UA" in query_val
    assert "sourcelang:English" in query_val


@pytest.mark.asyncio
async def test_search_articles_with_proxy() -> None:
    """初始化 client 时应透传 proxy 配置。"""
    fake_client = AsyncMock()
    fake_client.get = AsyncMock(return_value=httpx.Response(200, json={"articles": []}))
    fake_client.is_closed = False

    with patch("aegi_core.infra.gdelt_client.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value = fake_client

        gdelt_client = GDELTClient(proxy="http://127.0.0.1:7890")
        await gdelt_client.search_articles("proxy-check")

    assert mock_async_client.call_count == 1
    kwargs = mock_async_client.call_args.kwargs
    assert kwargs["proxy"] == "http://127.0.0.1:7890"


@pytest.mark.asyncio
async def test_search_articles_timespan_too_short_fallback(
    gdelt_client: GDELTClient,
) -> None:
    """timespan 过短返回文本时，自动回退到 1d 并重试。"""
    short_resp = httpx.Response(
        200,
        text="Timespan is too short.",
        headers={"content-type": "text/html; charset=utf-8"},
    )
    ok_resp = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://example.com/fallback",
                    "title": "Fallback OK",
                    "domain": "example.com",
                    "language": "English",
                }
            ]
        },
        headers={"content-type": "application/json; charset=utf-8"},
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[short_resp, ok_resp])
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    articles = await gdelt_client.search_articles("iran", timespan="15min")
    assert len(articles) == 1
    assert articles[0].title == "Fallback OK"
    assert mock_client.get.await_count == 2
    second_call_params = mock_client.get.await_args_list[1].kwargs["params"]
    assert second_call_params["timespan"] == "1d"


@pytest.mark.asyncio
async def test_search_articles_country_only_query_normalized(
    gdelt_client: GDELTClient,
) -> None:
    """国家过滤查询不应拼接无效通配符 '*'。"""
    captured_kwargs: dict = {}

    async def capture_get(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return httpx.Response(200, json={"articles": []})

    mock_client = AsyncMock()
    mock_client.get = capture_get
    mock_client.is_closed = False
    gdelt_client._client = mock_client

    await gdelt_client.search_articles("*", source_country="IR")
    params = captured_kwargs.get("params", {})
    assert params.get("query") == "sourcecountry:IR"


@pytest.mark.asyncio
async def test_close_uses_aclose(gdelt_client: GDELTClient) -> None:
    """关闭客户端时调用 AsyncClient.aclose。"""
    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.aclose = AsyncMock()
    gdelt_client._client = mock_client

    await gdelt_client.close()
    mock_client.aclose.assert_called_once()
