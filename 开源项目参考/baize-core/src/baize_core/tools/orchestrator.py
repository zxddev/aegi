"""MCP 工具链编排器。

实现 search→crawl→archive→parse 的自动化流程。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from baize_core.exceptions import ToolInvocationError
from baize_core.schemas.evidence import Artifact, Chunk, Evidence
from baize_core.schemas.mcp_toolchain import (
    ArchiveUrlOutput,
    DocParseOutput,
    MetaSearchOutput,
    MetaSearchResult,
    WebCrawlOutput,
)
from baize_core.schemas.policy import StageType
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.runner import ToolRunner

logger = logging.getLogger(__name__)


class ToolchainStage(str, Enum):
    """工具链阶段。"""

    SEARCH = "search"
    CRAWL = "crawl"
    ARCHIVE = "archive"
    PARSE = "parse"
    COMPLETE = "complete"
    FAILED = "failed"


class ToolchainConfig(BaseModel):
    """工具链配置。"""

    # 搜索配置
    max_results: int = Field(default=10, description="最大搜索结果数")
    language: str = Field(default="auto", description="搜索语言")
    time_range: str = Field(default="all", description="时间范围")

    # 抓取配置
    max_depth: int = Field(default=1, description="抓取深度")
    max_pages: int = Field(default=5, description="每个 URL 最大页面数")
    obey_robots_txt: bool = Field(default=True, description="是否遵守 robots.txt")
    timeout_ms: int = Field(default=30000, description="抓取超时（毫秒）")

    # 解析配置
    chunk_size: int = Field(default=800, description="分块大小")
    chunk_overlap: int = Field(default=120, description="分块重叠")

    # 去重配置
    dedupe_by_domain: bool = Field(default=True, description="按域名去重")
    dedupe_by_hash: bool = Field(default=True, description="按内容哈希去重")

    # 并发配置
    max_concurrent_crawls: int = Field(default=3, description="最大并发抓取数")
    max_concurrent_parses: int = Field(default=5, description="最大并发解析数")

    # 错误处理
    skip_on_error: bool = Field(default=True, description="出错时跳过")
    max_retries: int = Field(default=2, description="最大重试次数")


class ToolchainResult(BaseModel):
    """工具链执行结果。"""

    artifacts: list[Artifact] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    search_results: list[MetaSearchResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class UrlProcessResult(BaseModel):
    """单个 URL 处理结果。"""

    url: str
    search_result: MetaSearchResult | None = None
    crawl_artifact: Artifact | None = None
    archive_artifact: Artifact | None = None
    chunks: list[Chunk] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    success: bool = True
    error: str | None = None


@dataclass
class ToolchainOrchestrator:
    """MCP 工具链编排器。

    实现 search→crawl→archive→parse 的自动化流程，支持：
    - 并发执行
    - 错误恢复
    - 去重
    - 进度追踪
    """

    tool_runner: ToolRunner
    store: PostgresStore
    config: ToolchainConfig = field(default_factory=ToolchainConfig)

    # 去重状态
    _seen_urls: set[str] = field(default_factory=set)
    _seen_domains: set[str] = field(default_factory=set)
    _seen_hashes: set[str] = field(default_factory=set)

    async def run_full_chain(
        self,
        *,
        task_id: str,
        query: str,
    ) -> ToolchainResult:
        """运行完整工具链。

        Args:
            task_id: 任务标识
            query: 搜索查询

        Returns:
            工具链执行结果
        """
        result = ToolchainResult()

        # Step 1: 搜索
        search_output = await self._run_search(task_id, query)
        if search_output is None:
            result.errors.append("搜索失败")
            return result
        result.search_results = search_output.results
        result.stats["search_results"] = len(search_output.results)

        # Step 2-4: 并发处理每个 URL
        url_results = await self._process_urls(
            task_id=task_id,
            search_results=search_output.results,
        )

        # 聚合结果
        for url_result in url_results:
            if url_result.crawl_artifact:
                result.artifacts.append(url_result.crawl_artifact)
            if url_result.archive_artifact:
                result.artifacts.append(url_result.archive_artifact)
            result.chunks.extend(url_result.chunks)
            result.evidence.extend(url_result.evidence)
            if url_result.error:
                result.errors.append(f"{url_result.url}: {url_result.error}")

        result.stats["artifacts"] = len(result.artifacts)
        result.stats["chunks"] = len(result.chunks)
        result.stats["evidence"] = len(result.evidence)
        result.stats["errors"] = len(result.errors)

        return result

    async def run_from_urls(
        self,
        *,
        task_id: str,
        urls: list[str],
    ) -> ToolchainResult:
        """从 URL 列表运行工具链（跳过搜索）。

        Args:
            task_id: 任务标识
            urls: URL 列表

        Returns:
            工具链执行结果
        """
        result = ToolchainResult()

        # 创建虚拟搜索结果
        search_results = [
            MetaSearchResult(
                url=url,
                title=url,
                snippet="",
                source="direct",
                score=0.5,
            )
            for url in urls
        ]
        result.search_results = search_results

        url_results = await self._process_urls(
            task_id=task_id,
            search_results=search_results,
        )

        for url_result in url_results:
            if url_result.crawl_artifact:
                result.artifacts.append(url_result.crawl_artifact)
            if url_result.archive_artifact:
                result.artifacts.append(url_result.archive_artifact)
            result.chunks.extend(url_result.chunks)
            result.evidence.extend(url_result.evidence)
            if url_result.error:
                result.errors.append(f"{url_result.url}: {url_result.error}")

        result.stats["artifacts"] = len(result.artifacts)
        result.stats["chunks"] = len(result.chunks)
        result.stats["evidence"] = len(result.evidence)
        result.stats["errors"] = len(result.errors)

        return result

    async def _run_search(self, task_id: str, query: str) -> MetaSearchOutput | None:
        """执行搜索。"""
        payload: dict[str, object] = {
            "query": query,
            "max_results": self.config.max_results,
            "language": self.config.language,
            "time_range": self.config.time_range,
        }
        try:
            response = await self.tool_runner.run_mcp(
                tool_name="meta_search",
                tool_input=payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            return MetaSearchOutput.model_validate(response)
        except ToolInvocationError as exc:
            # 工具调用失败
            logger.warning("meta_search 工具调用失败: %s", exc)
            return None
        except Exception as exc:
            # 搜索失败（解析错误等）
            logger.warning("meta_search 处理失败: %s", exc)
            return None

    async def _process_urls(
        self,
        *,
        task_id: str,
        search_results: list[MetaSearchResult],
    ) -> list[UrlProcessResult]:
        """并发处理 URL 列表。"""
        # 创建并发信号量
        crawl_semaphore = asyncio.Semaphore(self.config.max_concurrent_crawls)
        parse_semaphore = asyncio.Semaphore(self.config.max_concurrent_parses)

        async def process_one(result: MetaSearchResult) -> UrlProcessResult:
            return await self._process_single_url(
                task_id=task_id,
                search_result=result,
                crawl_semaphore=crawl_semaphore,
                parse_semaphore=parse_semaphore,
            )

        tasks = [process_one(result) for result in search_results]
        return await asyncio.gather(*tasks)

    async def _process_single_url(
        self,
        *,
        task_id: str,
        search_result: MetaSearchResult,
        crawl_semaphore: asyncio.Semaphore,
        parse_semaphore: asyncio.Semaphore,
    ) -> UrlProcessResult:
        """处理单个 URL。"""
        url = search_result.url
        result = UrlProcessResult(url=url, search_result=search_result)

        # 去重检查
        if self._should_skip(url):
            result.success = False
            result.error = "重复 URL 或域名"
            return result

        try:
            # Step 2: 抓取
            async with crawl_semaphore:
                crawl_artifact = await self._run_crawl(task_id, url)
                if crawl_artifact:
                    result.crawl_artifact = crawl_artifact
                    await self.store.store_artifacts([crawl_artifact])

            # Step 3: 归档
            async with crawl_semaphore:
                archive_artifact = await self._run_archive(task_id, url)
                if archive_artifact is None:
                    result.success = False
                    result.error = "归档失败"
                    return result
                result.archive_artifact = archive_artifact
                await self.store.store_artifacts([archive_artifact])

            # 内容哈希去重
            if self.config.dedupe_by_hash:
                normalized_hash = archive_artifact.content_sha256.removeprefix(
                    "sha256:"
                )
                if normalized_hash in self._seen_hashes:
                    result.success = False
                    result.error = "重复内容"
                    return result
                self._seen_hashes.add(normalized_hash)

            # Step 4: 解析
            async with parse_semaphore:
                chunks = await self._run_parse(task_id, archive_artifact.artifact_uid)
                if chunks is None:
                    result.success = False
                    result.error = "解析失败"
                    return result
                result.chunks = chunks

            # 创建证据
            for chunk in chunks:
                evidence = Evidence(
                    chunk_uid=chunk.chunk_uid,
                    source=search_result.source,
                    uri=url,
                    collected_at=archive_artifact.fetched_at,
                    base_credibility=search_result.score,
                    tags=[f"source:{search_result.source}"],
                    summary=search_result.title,
                )
                result.evidence.append(evidence)

            # 写入存储
            if result.chunks or result.evidence:
                await self.store.store_evidence_chain(
                    artifacts=[],  # 已经存储
                    chunks=result.chunks,
                    evidence_items=result.evidence,
                    claims=[],
                )

            # 标记已处理
            self._mark_processed(url)

        except ToolInvocationError as e:
            # 工具调用失败
            logger.warning("URL 处理失败 (工具调用错误): %s - %s", url, e)
            result.success = False
            result.error = str(e)
        except Exception as e:
            # 其他未预期错误
            logger.exception("URL 处理发生未预期错误: %s", url)
            result.success = False
            result.error = str(e)

        return result

    async def _run_crawl(self, task_id: str, url: str) -> Artifact | None:
        """执行抓取。"""
        payload: dict[str, object] = {
            "url": url,
            "max_depth": self.config.max_depth,
            "max_pages": self.config.max_pages,
            "obey_robots_txt": self.config.obey_robots_txt,
            "timeout_ms": self.config.timeout_ms,
        }
        try:
            response = await self.tool_runner.run_mcp(
                tool_name="web_crawl",
                tool_input=payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            output = WebCrawlOutput.model_validate(response)
            output.artifact.origin_tool = "web_crawl"
            return output.artifact
        except ToolInvocationError as exc:
            logger.warning("web_crawl 工具调用失败: %s - %s", url, exc)
            if self.config.skip_on_error:
                return None
            raise
        except Exception as exc:
            logger.warning("web_crawl 处理失败: %s - %s", url, exc)
            if self.config.skip_on_error:
                return None
            raise ToolInvocationError(f"web_crawl 失败: {exc}") from exc

    async def _run_archive(self, task_id: str, url: str) -> Artifact | None:
        """执行归档。"""
        payload: dict[str, object] = {"url": url}
        try:
            response = await self.tool_runner.run_mcp(
                tool_name="archive_url",
                tool_input=payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            output = ArchiveUrlOutput.model_validate(response)
            output.artifact.origin_tool = "archive_url"
            return output.artifact
        except ToolInvocationError as exc:
            logger.warning("archive_url 工具调用失败: %s - %s", url, exc)
            if self.config.skip_on_error:
                return None
            raise
        except Exception as exc:
            logger.warning("archive_url 处理失败: %s - %s", url, exc)
            if self.config.skip_on_error:
                return None
            raise ToolInvocationError(f"archive_url 失败: {exc}") from exc

    async def _run_parse(self, task_id: str, artifact_uid: str) -> list[Chunk] | None:
        """执行解析。"""
        payload: dict[str, object] = {
            "artifact_uid": artifact_uid,
            "chunk_size": self.config.chunk_size,
            "chunk_overlap": self.config.chunk_overlap,
        }
        try:
            response = await self.tool_runner.run_mcp(
                tool_name="doc_parse",
                tool_input=payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            output = DocParseOutput.model_validate(response)
            return output.chunks
        except ToolInvocationError as exc:
            logger.warning("doc_parse 工具调用失败: %s - %s", artifact_uid, exc)
            if self.config.skip_on_error:
                return None
            raise
        except Exception as exc:
            logger.warning("doc_parse 处理失败: %s - %s", artifact_uid, exc)
            if self.config.skip_on_error:
                return None
            raise ToolInvocationError(f"doc_parse 失败: {exc}") from exc

    def _should_skip(self, url: str) -> bool:
        """检查是否应该跳过此 URL。"""
        if url in self._seen_urls:
            return True

        if self.config.dedupe_by_domain:
            domain = urlparse(url).netloc
            if domain and domain in self._seen_domains:
                return True

        return False

    def _mark_processed(self, url: str) -> None:
        """标记 URL 已处理。"""
        self._seen_urls.add(url)
        if self.config.dedupe_by_domain:
            domain = urlparse(url).netloc
            if domain:
                self._seen_domains.add(domain)

    def reset_dedup_state(self) -> None:
        """重置去重状态。"""
        self._seen_urls.clear()
        self._seen_domains.clear()
        self._seen_hashes.clear()


async def run_toolchain(
    *,
    tool_runner: ToolRunner,
    store: PostgresStore,
    task_id: str,
    query: str,
    config: ToolchainConfig | None = None,
) -> ToolchainResult:
    """便捷函数：运行完整工具链。

    Args:
        tool_runner: 工具运行器
        store: PostgreSQL 存储
        task_id: 任务标识
        query: 搜索查询
        config: 工具链配置

    Returns:
        工具链执行结果
    """
    orchestrator = ToolchainOrchestrator(
        tool_runner=tool_runner,
        store=store,
        config=config or ToolchainConfig(),
    )
    return await orchestrator.run_full_chain(task_id=task_id, query=query)
