# Author: msq
"""GDELT DOC API 异步客户端。

通过 GDELT v2 DOC API 搜索全球新闻文章。
仅做 HTTP 请求 + JSON 解析，不涉及业务逻辑。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class GDELTArticle:
    """GDELT DOC API 返回的单篇文章。"""

    url: str = ""
    title: str = ""
    source_domain: str = ""
    language: str = ""
    seendate: str = ""
    socialimage: str = ""
    tone: float = 0.0
    domain_country: str = ""


class GDELTClient:
    """GDELT DOC API 异步客户端，遵循 SearXNGClient 模式。"""

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                proxy=self._proxy,
            )
        return self._client

    async def search_articles(
        self,
        query: str,
        *,
        mode: str = "ArtList",
        timespan: str = "15min",
        max_records: int = 50,
        source_country: str | None = None,
        source_lang: str | None = None,
        sort: str = "DateDesc",
    ) -> list[GDELTArticle]:
        """搜索 GDELT 文章，容错返回空列表。"""
        # 拼接 query 过滤条件
        q_parts = [query]
        if source_country:
            q_parts.append(f"sourcecountry:{source_country}")
        if source_lang:
            q_parts.append(f"sourcelang:{source_lang}")

        params = {
            "query": " ".join(q_parts),
            "mode": mode,
            "maxrecords": str(max_records),
            "timespan": timespan,
            "sort": sort,
            "format": "json",
        }

        client = await self._ensure_client()
        try:
            resp = await client.get(self.BASE_URL, params=params)
            if resp.status_code != 200:
                logger.warning("GDELT API 非 200: status=%d", resp.status_code)
                return []
            data = resp.json()
        except httpx.TimeoutException:
            logger.warning("GDELT API 超时: query=%s", query)
            return []
        except Exception as exc:
            logger.warning("GDELT API 请求失败: %s", exc)
            return []

        raw_articles = data.get("articles", [])
        if not isinstance(raw_articles, list):
            logger.warning("GDELT API 返回非预期格式: %s", type(raw_articles))
            return []

        articles: list[GDELTArticle] = []
        for item in raw_articles[:max_records]:
            try:
                articles.append(
                    GDELTArticle(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        source_domain=item.get("domain", ""),
                        language=item.get("language", ""),
                        seendate=item.get("seendate", ""),
                        socialimage=item.get("socialimage", ""),
                        tone=float(item.get("tone", 0.0)),
                        domain_country=item.get("domaincountry", "")
                        or item.get("sourcecountry", ""),
                    )
                )
            except (ValueError, TypeError):
                continue
        return articles

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.close()
