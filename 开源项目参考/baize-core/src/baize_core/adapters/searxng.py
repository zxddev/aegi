"""SearxNG 元搜索适配器。

SearxNG 是一个开源的元搜索引擎，支持聚合多个搜索引擎的结果。
此适配器提供与 SearxNG API 的集成。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SearchCategory(str, Enum):
    """搜索类别。"""

    GENERAL = "general"
    IMAGES = "images"
    VIDEOS = "videos"
    NEWS = "news"
    MAP = "map"
    MUSIC = "music"
    IT = "it"
    SCIENCE = "science"
    FILES = "files"
    SOCIAL_MEDIA = "social media"


class TimeRange(str, Enum):
    """时间范围。"""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SafeSearch(int, Enum):
    """安全搜索级别。"""

    OFF = 0
    MODERATE = 1
    STRICT = 2


@dataclass(frozen=True)
class SearxNGConfig:
    """SearxNG 配置。"""

    base_url: str  # SearxNG 服务地址
    timeout_seconds: int = 30
    verify_ssl: bool = True
    # 默认搜索引擎（空列表表示使用所有启用的引擎）
    default_engines: tuple[str, ...] = ()
    # 默认语言
    default_language: str = "auto"
    # 默认安全搜索级别
    default_safe_search: SafeSearch = SafeSearch.MODERATE


@dataclass
class SearchResult:
    """搜索结果。"""

    title: str
    url: str
    snippet: str
    score: float
    source: str  # 搜索引擎名称
    published_at: datetime | None = None
    category: str = "general"
    thumbnail: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearxNGResponse:
    """SearxNG 响应。"""

    query: str
    results: list[SearchResult]
    number_of_results: int
    search_time_seconds: float
    suggestions: list[str]
    infoboxes: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


class SearxNGClient:
    """SearxNG 客户端。

    支持功能：
    - 多搜索引擎聚合
    - 搜索类别过滤
    - 时间范围过滤
    - 语言设置
    - 分页
    """

    def __init__(self, config: SearxNGConfig) -> None:
        """初始化客户端。

        Args:
            config: SearxNG 配置
        """
        self._config = config

    async def search(
        self,
        query: str,
        *,
        categories: list[SearchCategory] | None = None,
        engines: list[str] | None = None,
        language: str | None = None,
        time_range: TimeRange | None = None,
        safe_search: SafeSearch | None = None,
        page: int = 1,
        max_results: int = 10,
    ) -> SearxNGResponse:
        """执行搜索。

        Args:
            query: 搜索查询
            categories: 搜索类别列表
            engines: 指定的搜索引擎列表
            language: 搜索语言
            time_range: 时间范围
            safe_search: 安全搜索级别
            page: 页码（从 1 开始）
            max_results: 最大结果数

        Returns:
            搜索响应
        """
        url = f"{self._config.base_url}/search"
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "pageno": page,
        }

        # 类别
        if categories:
            params["categories"] = ",".join(c.value for c in categories)

        # 引擎
        effective_engines = engines or list(self._config.default_engines)
        if effective_engines:
            params["engines"] = ",".join(effective_engines)

        # 语言
        effective_language = language or self._config.default_language
        if effective_language != "auto":
            params["language"] = effective_language

        # 时间范围
        if time_range:
            params["time_range"] = time_range.value

        # 安全搜索
        effective_safe_search = safe_search or self._config.default_safe_search
        params["safesearch"] = effective_safe_search.value

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            import time

            start_time = time.time()
            response = await client.get(url, params=params)
            response.raise_for_status()
            elapsed_seconds = time.time() - start_time

            data = response.json()
            return self._parse_response(
                query=query,
                data=data,
                elapsed_seconds=elapsed_seconds,
                max_results=max_results,
            )

    async def search_images(
        self,
        query: str,
        *,
        engines: list[str] | None = None,
        language: str | None = None,
        time_range: TimeRange | None = None,
        safe_search: SafeSearch | None = None,
        max_results: int = 20,
    ) -> list[SearchResult]:
        """搜索图片。

        Args:
            query: 搜索查询
            engines: 指定的图片搜索引擎
            language: 搜索语言
            time_range: 时间范围
            safe_search: 安全搜索级别
            max_results: 最大结果数

        Returns:
            图片搜索结果列表
        """
        response = await self.search(
            query=query,
            categories=[SearchCategory.IMAGES],
            engines=engines,
            language=language,
            time_range=time_range,
            safe_search=safe_search,
            max_results=max_results,
        )
        return response.results

    async def search_news(
        self,
        query: str,
        *,
        engines: list[str] | None = None,
        language: str | None = None,
        time_range: TimeRange | None = None,
        max_results: int = 20,
    ) -> list[SearchResult]:
        """搜索新闻。

        Args:
            query: 搜索查询
            engines: 指定的新闻搜索引擎
            language: 搜索语言
            time_range: 时间范围
            max_results: 最大结果数

        Returns:
            新闻搜索结果列表
        """
        response = await self.search(
            query=query,
            categories=[SearchCategory.NEWS],
            engines=engines,
            language=language,
            time_range=time_range,
            max_results=max_results,
        )
        return response.results

    async def search_videos(
        self,
        query: str,
        *,
        engines: list[str] | None = None,
        language: str | None = None,
        time_range: TimeRange | None = None,
        safe_search: SafeSearch | None = None,
        max_results: int = 20,
    ) -> list[SearchResult]:
        """搜索视频。

        Args:
            query: 搜索查询
            engines: 指定的视频搜索引擎
            language: 搜索语言
            time_range: 时间范围
            safe_search: 安全搜索级别
            max_results: 最大结果数

        Returns:
            视频搜索结果列表
        """
        response = await self.search(
            query=query,
            categories=[SearchCategory.VIDEOS],
            engines=engines,
            language=language,
            time_range=time_range,
            safe_search=safe_search,
            max_results=max_results,
        )
        return response.results

    async def get_engines(self) -> list[dict[str, Any]]:
        """获取可用的搜索引擎列表。

        Returns:
            搜索引擎信息列表
        """
        url = f"{self._config.base_url}/config"
        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("engines", [])

    def _parse_response(
        self,
        query: str,
        data: dict[str, Any],
        elapsed_seconds: float,
        max_results: int,
    ) -> SearxNGResponse:
        """解析搜索响应。"""
        results: list[SearchResult] = []
        raw_results = data.get("results", [])

        for idx, item in enumerate(raw_results[:max_results]):
            result = self._parse_result(item, idx)
            if result:
                results.append(result)

        # 建议
        suggestions = data.get("suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = []

        # Infoboxes
        infoboxes = data.get("infoboxes", [])
        if not isinstance(infoboxes, list):
            infoboxes = []

        return SearxNGResponse(
            query=query,
            results=results,
            number_of_results=data.get("number_of_results", len(results)),
            search_time_seconds=elapsed_seconds,
            suggestions=suggestions,
            infoboxes=infoboxes,
            metadata={
                "query": data.get("query", query),
                "unresponsive_engines": data.get("unresponsive_engines", []),
            },
        )

    def _parse_result(
        self,
        item: dict[str, Any],
        idx: int,
    ) -> SearchResult | None:
        """解析单个搜索结果。"""
        url = item.get("url")
        title = item.get("title")

        if not url or not title:
            return None

        # 提取摘要
        content = item.get("content") or item.get("snippet") or ""

        # 提取来源（搜索引擎）
        engines = item.get("engines", [])
        source = engines[0] if engines else item.get("engine", "unknown")

        # 计算分数（基于排名和引擎数量）
        engine_count = len(engines) if engines else 1
        rank_score = 1.0 - (idx * 0.05)  # 排名越靠前分数越高
        engine_bonus = min(0.2, engine_count * 0.05)  # 多引擎加分
        score = min(1.0, max(0.1, rank_score + engine_bonus))

        # 解析发布时间
        published_at = None
        published_date = item.get("publishedDate")
        if published_date:
            try:
                from dateutil import parser

                published_at = parser.parse(published_date)
            except Exception:
                pass

        # 类别
        category = item.get("category", "general")

        # 缩略图
        thumbnail = item.get("thumbnail") or item.get("img_src")

        return SearchResult(
            title=title,
            url=url,
            snippet=content,
            score=score,
            source=source,
            published_at=published_at,
            category=category,
            thumbnail=thumbnail,
            metadata={
                "engines": engines,
                "parsed_url": item.get("parsed_url", []),
                "template": item.get("template"),
            },
        )


def create_searxng_client(
    base_url: str,
    timeout_seconds: int = 30,
    default_language: str = "zh-CN",
) -> SearxNGClient:
    """创建 SearxNG 客户端的便捷函数。

    Args:
        base_url: SearxNG 服务地址
        timeout_seconds: 超时时间
        default_language: 默认语言

    Returns:
        SearxNG 客户端实例
    """
    config = SearxNGConfig(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        default_language=default_language,
    )
    return SearxNGClient(config)
