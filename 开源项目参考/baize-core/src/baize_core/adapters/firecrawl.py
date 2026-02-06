"""Firecrawl 深度抓取适配器。

Firecrawl 是一个将网页转换为 LLM-ready Markdown 的服务。
此适配器提供与 Firecrawl API 的集成。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any

import httpx

from baize_core.schemas.evidence import Artifact
from baize_core.storage.minio_store import MinioArtifactStore

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """输出格式。"""

    MARKDOWN = "markdown"
    HTML = "html"
    RAW_HTML = "rawHtml"
    LINKS = "links"
    SCREENSHOT = "screenshot"


class CrawlMode(str, Enum):
    """抓取模式。"""

    DEFAULT = "default"  # 默认抓取
    FAST = "fast"  # 快速抓取（跳过 JS 渲染）


@dataclass(frozen=True)
class FirecrawlConfig:
    """Firecrawl 配置。"""

    base_url: str  # Firecrawl 服务地址
    api_key: str | None = None  # API Key（如果需要）
    timeout_seconds: int = 60
    verify_ssl: bool = True
    # 默认输出格式
    default_formats: tuple[OutputFormat, ...] = (OutputFormat.MARKDOWN,)
    # 默认抓取深度
    default_max_depth: int = 1
    # 默认最大页面数
    default_max_pages: int = 10


@dataclass
class ScrapeResult:
    """单页抓取结果。"""

    url: str
    markdown: str
    html: str | None = None
    raw_html: str | None = None
    links: list[str] = field(default_factory=list)
    screenshot: str | None = None  # Base64 编码
    metadata: dict[str, Any] = field(default_factory=dict)
    title: str | None = None
    description: str | None = None
    language: str | None = None
    source_url: str | None = None


@dataclass
class CrawlResult:
    """多页抓取结果。"""

    pages: list[ScrapeResult]
    total_pages: int
    crawl_time_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


class FirecrawlClient:
    """Firecrawl 客户端。

    支持功能：
    - 单页抓取（scrape）
    - 多页抓取（crawl）
    - 多种输出格式
    - 与 MinIO 集成存储 Artifact
    """

    def __init__(
        self,
        config: FirecrawlConfig,
        artifact_store: MinioArtifactStore | None = None,
    ) -> None:
        """初始化客户端。

        Args:
            config: Firecrawl 配置
            artifact_store: MinIO 存储（可选，用于存储 Artifact）
        """
        self._config = config
        self._artifact_store = artifact_store

    async def scrape(
        self,
        url: str,
        *,
        formats: list[OutputFormat] | None = None,
        wait_for: str | None = None,
        timeout_ms: int | None = None,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        only_main_content: bool = True,
    ) -> ScrapeResult:
        """抓取单个页面。

        Args:
            url: 目标 URL
            formats: 输出格式列表
            wait_for: 等待特定元素出现（CSS 选择器）
            timeout_ms: 超时时间（毫秒）
            include_tags: 只包含特定标签
            exclude_tags: 排除特定标签
            only_main_content: 只提取主要内容

        Returns:
            抓取结果
        """
        endpoint = f"{self._config.base_url}/v1/scrape"
        effective_formats = formats or list(self._config.default_formats)

        payload: dict[str, Any] = {
            "url": url,
            "formats": [f.value for f in effective_formats],
            "onlyMainContent": only_main_content,
        }

        if wait_for:
            payload["waitFor"] = wait_for
        if timeout_ms:
            payload["timeout"] = timeout_ms
        if include_tags:
            payload["includeTags"] = include_tags
        if exclude_tags:
            payload["excludeTags"] = exclude_tags

        headers = self._build_headers()

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_scrape_result(data)

    async def crawl(
        self,
        url: str,
        *,
        max_depth: int | None = None,
        max_pages: int | None = None,
        formats: list[OutputFormat] | None = None,
        include_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
        allow_backward_links: bool = False,
        allow_external_links: bool = False,
        ignore_sitemap: bool = False,
    ) -> CrawlResult:
        """抓取多个页面。

        Args:
            url: 起始 URL
            max_depth: 最大深度
            max_pages: 最大页面数
            formats: 输出格式列表
            include_paths: 只包含特定路径
            exclude_paths: 排除特定路径
            allow_backward_links: 允许反向链接
            allow_external_links: 允许外部链接
            ignore_sitemap: 忽略 sitemap

        Returns:
            抓取结果
        """
        endpoint = f"{self._config.base_url}/v1/crawl"
        effective_max_depth = max_depth or self._config.default_max_depth
        effective_max_pages = max_pages or self._config.default_max_pages
        effective_formats = formats or list(self._config.default_formats)

        payload: dict[str, Any] = {
            "url": url,
            "maxDepth": effective_max_depth,
            "limit": effective_max_pages,
            "scrapeOptions": {
                "formats": [f.value for f in effective_formats],
            },
        }

        if include_paths:
            payload["includePaths"] = include_paths
        if exclude_paths:
            payload["excludePaths"] = exclude_paths
        if allow_backward_links:
            payload["allowBackwardLinks"] = True
        if allow_external_links:
            payload["allowExternalLinks"] = True
        if ignore_sitemap:
            payload["ignoreSitemap"] = True

        headers = self._build_headers()

        import time

        start_time = time.time()

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds * 2,  # 爬取可能需要更长时间
            verify=self._config.verify_ssl,
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            elapsed_seconds = time.time() - start_time
            return self._parse_crawl_result(data, elapsed_seconds)

    async def scrape_and_store(
        self,
        url: str,
        task_id: str,
        *,
        formats: list[OutputFormat] | None = None,
        **kwargs: Any,
    ) -> Artifact:
        """抓取页面并存储为 Artifact。

        Args:
            url: 目标 URL
            task_id: 任务 ID
            formats: 输出格式列表
            **kwargs: 其他参数传递给 scrape

        Returns:
            存储的 Artifact

        Raises:
            ValueError: artifact_store 未配置
        """
        if self._artifact_store is None:
            raise ValueError("artifact_store 未配置")

        result = await self.scrape(url, formats=formats, **kwargs)

        # 存储 Markdown 内容
        markdown_bytes = result.markdown.encode("utf-8")
        content_hash = sha256(markdown_bytes).hexdigest()
        object_name = f"firecrawl/{task_id}/{content_hash}.md"

        await self._artifact_store.ensure_bucket()
        await self._artifact_store.put_text(
            object_name=object_name,
            text=result.markdown,
            content_type="text/markdown",
        )

        # 创建 Artifact 记录
        artifact = Artifact(
            artifact_uid=f"art_{content_hash}",
            source_url=result.source_url or url,
            fetched_at=datetime.now(UTC),
            content_sha256=f"sha256:{content_hash}",
            mime_type="text/markdown",
            storage_ref=f"minio://{self._artifact_store.bucket}/{object_name}",
            origin_tool="firecrawl",
        )

        return artifact

    def _build_headers(self) -> dict[str, str]:
        """构建请求头。"""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def _parse_scrape_result(self, data: dict[str, Any]) -> ScrapeResult:
        """解析抓取结果。"""
        if not data.get("success", True):
            error = data.get("error", "Unknown error")
            raise ValueError(f"Firecrawl 抓取失败: {error}")

        result_data = data.get("data", data)

        return ScrapeResult(
            url=result_data.get("url", ""),
            markdown=result_data.get("markdown", ""),
            html=result_data.get("html"),
            raw_html=result_data.get("rawHtml"),
            links=result_data.get("links", []),
            screenshot=result_data.get("screenshot"),
            metadata=result_data.get("metadata", {}),
            title=result_data.get("metadata", {}).get("title"),
            description=result_data.get("metadata", {}).get("description"),
            language=result_data.get("metadata", {}).get("language"),
            source_url=result_data.get("metadata", {}).get("sourceURL"),
        )

    def _parse_crawl_result(
        self,
        data: dict[str, Any],
        elapsed_seconds: float,
    ) -> CrawlResult:
        """解析爬取结果。"""
        if not data.get("success", True):
            error = data.get("error", "Unknown error")
            raise ValueError(f"Firecrawl 爬取失败: {error}")

        pages: list[ScrapeResult] = []
        raw_data = data.get("data", [])

        if isinstance(raw_data, list):
            for item in raw_data:
                try:
                    page = self._parse_scrape_result({"data": item})
                    pages.append(page)
                except Exception as exc:
                    logger.warning("解析页面失败: %s", exc)

        return CrawlResult(
            pages=pages,
            total_pages=len(pages),
            crawl_time_seconds=elapsed_seconds,
            metadata={
                "total": data.get("total"),
                "completed": data.get("completed"),
                "creditsUsed": data.get("creditsUsed"),
            },
        )


def create_firecrawl_client(
    base_url: str,
    api_key: str | None = None,
    timeout_seconds: int = 60,
    artifact_store: MinioArtifactStore | None = None,
) -> FirecrawlClient:
    """创建 Firecrawl 客户端的便捷函数。

    Args:
        base_url: Firecrawl 服务地址
        api_key: API Key
        timeout_seconds: 超时时间
        artifact_store: MinIO 存储

    Returns:
        Firecrawl 客户端实例
    """
    config = FirecrawlConfig(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    return FirecrawlClient(config, artifact_store=artifact_store)
