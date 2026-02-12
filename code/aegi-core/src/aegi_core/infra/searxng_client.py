"""SearXNG 搜索客户端。

通过自建 SearXNG 实例做结构化网页搜索。
供爬虫 agent 和 pipeline stage 获取外部信息。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str = ""


class SearXNGClient:
    """SearXNG JSON API 异步客户端。"""

    def __init__(self, base_url: str = "http://localhost:8888") -> None:
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def search(
        self,
        query: str,
        *,
        categories: str = "general",
        language: str = "zh-CN",
        limit: int = 10,
    ) -> list[SearchResult]:
        """执行搜索查询，返回结构化结果。"""
        client = await self._ensure_client()
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
        }
        try:
            resp = await client.get(f"{self._base_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("SearXNG search failed: %s", exc)
            return []

        results = []
        for item in data.get("results", [])[:limit]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    engine=item.get("engine", ""),
                )
            )
        return results

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.close()
