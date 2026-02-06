"""Perplexica AI 搜索适配器。

Perplexica 是一个开源的 AI 驱动搜索引擎。
此适配器提供与 Perplexica API 的集成。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PerplexicaConfig:
    """Perplexica 配置。"""

    base_url: str  # Perplexica 服务地址
    timeout_seconds: int = 60
    verify_ssl: bool = True


@dataclass
class SearchResult:
    """搜索结果。"""

    title: str
    url: str
    snippet: str
    score: float
    source: str
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PerplexicaResponse:
    """Perplexica 响应。"""

    query: str
    answer: str  # AI 生成的答案
    sources: list[SearchResult]
    search_time_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


class PerplexicaClient:
    """Perplexica 客户端。"""

    def __init__(self, config: PerplexicaConfig) -> None:
        """初始化客户端。

        Args:
            config: Perplexica 配置
        """
        self._config = config

    async def search(
        self,
        query: str,
        focus_mode: str = "webSearch",
        optimization_mode: str = "balanced",
        chat_history: list[dict[str, str]] | None = None,
    ) -> PerplexicaResponse:
        """执行 AI 搜索。

        Args:
            query: 搜索查询
            focus_mode: 聚焦模式 (webSearch, academicSearch, writingAssistant, etc.)
            optimization_mode: 优化模式 (speed, balanced, quality)
            chat_history: 可选的对话历史

        Returns:
            搜索响应
        """
        url = f"{self._config.base_url}/api/search"
        payload = {
            "chatModel": {
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
            "embeddingModel": {
                "provider": "openai",
                "model": "text-embedding-3-small",
            },
            "focusMode": focus_mode,
            "optimizationMode": optimization_mode,
            "query": query,
            "history": chat_history or [],
        }

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            import time

            start_time = time.time()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            elapsed_ms = int((time.time() - start_time) * 1000)

            data = response.json()
            return self._parse_response(query, data, elapsed_ms)

    async def search_images(
        self,
        query: str,
    ) -> list[SearchResult]:
        """搜索图片。

        Args:
            query: 搜索查询

        Returns:
            图片搜索结果列表
        """
        url = f"{self._config.base_url}/api/images"
        payload = {
            "query": query,
            "chatHistory": [],
        }

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_images(data)

    async def search_videos(
        self,
        query: str,
    ) -> list[SearchResult]:
        """搜索视频。

        Args:
            query: 搜索查询

        Returns:
            视频搜索结果列表
        """
        url = f"{self._config.base_url}/api/videos"
        payload = {
            "query": query,
            "chatHistory": [],
        }

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return self._parse_videos(data)

    def _parse_response(
        self, query: str, data: dict[str, Any], elapsed_ms: int
    ) -> PerplexicaResponse:
        """解析搜索响应。"""
        sources: list[SearchResult] = []
        for idx, source in enumerate(data.get("sources", [])):
            sources.append(
                SearchResult(
                    title=source.get("title", ""),
                    url=source.get("url", ""),
                    snippet=source.get("content", ""),
                    score=1.0 - (idx * 0.1),  # 基于排名的分数
                    source="perplexica",
                )
            )
        return PerplexicaResponse(
            query=query,
            answer=data.get("message", ""),
            sources=sources,
            search_time_ms=elapsed_ms,
        )

    def _parse_images(self, data: dict[str, Any]) -> list[SearchResult]:
        """解析图片搜索结果。"""
        results: list[SearchResult] = []
        for idx, image in enumerate(data.get("images", [])):
            results.append(
                SearchResult(
                    title=image.get("title", ""),
                    url=image.get("img_src", ""),
                    snippet="",
                    score=1.0 - (idx * 0.05),
                    source="perplexica_images",
                    metadata={"url": image.get("url", "")},
                )
            )
        return results

    def _parse_videos(self, data: dict[str, Any]) -> list[SearchResult]:
        """解析视频搜索结果。"""
        results: list[SearchResult] = []
        for idx, video in enumerate(data.get("videos", [])):
            results.append(
                SearchResult(
                    title=video.get("title", ""),
                    url=video.get("url", ""),
                    snippet="",
                    score=1.0 - (idx * 0.05),
                    source="perplexica_videos",
                    metadata={"thumbnail": video.get("thumbnail", "")},
                )
            )
        return results
