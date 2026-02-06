"""OSINT 数据流端到端测试。

测试从搜索到归档再到解析的完整数据流。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from baize_core.adapters.archivebox import (
    ArchiveBoxClient,
    ArchiveBoxConfig,
    ArchiveResult,
    ArchiveStatus,
)
from baize_core.adapters.firecrawl import (
    FirecrawlClient,
    FirecrawlConfig,
    OutputFormat,
    ScrapeResult,
)
from baize_core.adapters.searxng import (
    SearxNGClient,
    SearxNGConfig,
    SearxNGResponse,
    TimeRange,
)
from baize_core.adapters.unstructured import (
    ElementType,
    ParseResult,
    UnstructuredClient,
    UnstructuredConfig,
)


class TestSearxNGClient:
    """SearxNG 客户端测试。"""

    @pytest.fixture
    def config(self) -> SearxNGConfig:
        """创建测试配置。"""
        return SearxNGConfig(
            base_url="http://localhost:8601",
            timeout_seconds=10,
        )

    @pytest.fixture
    def client(self, config: SearxNGConfig) -> SearxNGClient:
        """创建客户端实例。"""
        return SearxNGClient(config)

    @pytest.mark.asyncio
    async def test_search_basic(self, client: SearxNGClient) -> None:
        """测试基本搜索功能。"""
        mock_response = {
            "results": [
                {
                    "url": "https://example.com/article1",
                    "title": "测试文章 1",
                    "content": "这是测试文章的摘要内容",
                    "engines": ["google", "bing"],
                    "score": 0.9,
                },
                {
                    "url": "https://example.com/article2",
                    "title": "测试文章 2",
                    "content": "另一篇测试文章的摘要",
                    "engines": ["google"],
                    "score": 0.8,
                },
            ],
            "number_of_results": 2,
            "suggestions": ["相关搜索建议"],
            "infoboxes": [],
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            response = await client.search(
                query="测试查询",
                max_results=10,
            )

        assert isinstance(response, SearxNGResponse)
        assert response.query == "测试查询"
        assert len(response.results) == 2
        assert response.results[0].title == "测试文章 1"
        assert response.results[0].url == "https://example.com/article1"
        assert response.suggestions == ["相关搜索建议"]

    @pytest.mark.asyncio
    async def test_search_with_categories(self, client: SearxNGClient) -> None:
        """测试带类别的搜索。"""
        mock_response = {
            "results": [
                {
                    "url": "https://news.example.com/breaking",
                    "title": "突发新闻",
                    "content": "新闻摘要",
                    "engines": ["google_news"],
                    "score": 0.95,
                    "publishedDate": "2024-01-15T10:00:00Z",
                },
            ],
            "number_of_results": 1,
            "suggestions": [],
            "infoboxes": [],
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            results = await client.search_news(
                query="突发新闻",
                time_range=TimeRange.DAY,
                max_results=5,
            )

        assert len(results) == 1
        assert results[0].title == "突发新闻"


class TestFirecrawlClient:
    """Firecrawl 客户端测试。"""

    @pytest.fixture
    def config(self) -> FirecrawlConfig:
        """创建测试配置。"""
        return FirecrawlConfig(
            base_url="http://localhost:3002",
            timeout_seconds=60,
        )

    @pytest.fixture
    def client(self, config: FirecrawlConfig) -> FirecrawlClient:
        """创建客户端实例。"""
        return FirecrawlClient(config)

    @pytest.mark.asyncio
    async def test_scrape_basic(self, client: FirecrawlClient) -> None:
        """测试基本抓取功能。"""
        mock_response = {
            "success": True,
            "data": {
                "url": "https://example.com/article",
                "markdown": "# 测试文章\n\n这是文章内容。",
                "metadata": {
                    "title": "测试文章",
                    "description": "文章描述",
                    "sourceURL": "https://example.com/article",
                },
            },
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            result = await client.scrape(
                url="https://example.com/article",
                formats=[OutputFormat.MARKDOWN],
            )

        assert isinstance(result, ScrapeResult)
        assert result.url == "https://example.com/article"
        assert "# 测试文章" in result.markdown
        assert result.title == "测试文章"


class TestArchiveBoxClient:
    """ArchiveBox 客户端测试。"""

    @pytest.fixture
    def config(self) -> ArchiveBoxConfig:
        """创建测试配置。"""
        return ArchiveBoxConfig(
            use_api=False,
            docker_container="archivebox",
            docker_user="archivebox",
            public_host="localhost",
            public_port=8602,
        )

    @pytest.fixture
    def client(self, config: ArchiveBoxConfig) -> ArchiveBoxClient:
        """创建客户端实例。"""
        return ArchiveBoxClient(config)

    @pytest.mark.asyncio
    async def test_add_url(self, client: ArchiveBoxClient) -> None:
        """测试添加 URL 到归档。"""
        mock_stdout = """
        [{"timestamp": "20240115120000", "url": "https://example.com", "title": "Example", "content_sha256": "abc123"}]
        """

        with patch("asyncio.to_thread") as mock_thread:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = mock_stdout
            mock_process.stderr = ""
            mock_thread.return_value = mock_process

            result = await client.add("https://example.com")

        assert isinstance(result, ArchiveResult)
        assert result.url == "https://example.com"
        assert result.timestamp == "20240115120000"
        assert result.status == ArchiveStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_add_and_create_artifact(self, client: ArchiveBoxClient) -> None:
        """测试添加 URL 并创建 Artifact。"""
        mock_stdout = """
        [{"timestamp": "20240115120000", "url": "https://example.com", "title": "Example", "content_sha256": "abc123", "mime_type": "text/html"}]
        """

        with patch("asyncio.to_thread") as mock_thread:
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = mock_stdout
            mock_process.stderr = ""
            mock_thread.return_value = mock_process

            artifact = await client.add_and_create_artifact("https://example.com")

        assert artifact.artifact_uid == "art_20240115120000"
        assert artifact.source_url == "https://example.com"
        assert artifact.origin_tool == "archivebox"


class TestUnstructuredClient:
    """Unstructured 客户端测试。"""

    @pytest.fixture
    def config(self) -> UnstructuredConfig:
        """创建测试配置。"""
        return UnstructuredConfig(
            api_url="http://localhost:8603/general/v0/general",
            timeout_seconds=60,
        )

    @pytest.fixture
    def client(self, config: UnstructuredConfig) -> UnstructuredClient:
        """创建客户端实例。"""
        return UnstructuredClient(config)

    @pytest.mark.asyncio
    async def test_parse_file(self, client: UnstructuredClient) -> None:
        """测试文件解析。"""
        mock_response = [
            {
                "element_id": "elem1",
                "type": "Title",
                "text": "文档标题",
                "metadata": {"page_number": 1},
            },
            {
                "element_id": "elem2",
                "type": "NarrativeText",
                "text": "这是文档的正文内容。",
                "metadata": {"page_number": 1},
            },
        ]

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            result = await client.parse_file(
                file_content=b"test content",
                filename="test.pdf",
                content_type="application/pdf",
            )

        assert isinstance(result, ParseResult)
        assert len(result.elements) == 2
        assert result.elements[0].element_type == ElementType.TITLE
        assert result.elements[0].text == "文档标题"

    @pytest.mark.asyncio
    async def test_parse_and_chunk(self, client: UnstructuredClient) -> None:
        """测试解析并分块。"""
        mock_response = [
            {
                "element_id": "elem1",
                "type": "Title",
                "text": "章节标题",
                "metadata": {"page_number": 1},
            },
            {
                "element_id": "elem2",
                "type": "NarrativeText",
                "text": "这是章节内容。" * 50,  # 较长文本用于分块
                "metadata": {"page_number": 1},
            },
        ]

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_response,
                raise_for_status=lambda: None,
            )

            result = await client.parse_and_chunk(
                file_content=b"test content",
                filename="test.pdf",
                artifact_uid="art_test123",
                chunk_size=100,
                chunk_overlap=20,
            )

        assert result.total_chunks > 0
        for chunk in result.chunks:
            assert chunk.artifact_uid == "art_test123"
            assert len(chunk.text) <= 100

    def test_chunk_text(self, client: UnstructuredClient) -> None:
        """测试文本分块。"""
        text = "这是一段测试文本。" * 20

        chunks = client._chunk_text(
            text=text,
            artifact_uid="art_test",
            max_chunk_size=50,
            overlap=10,
        )

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text) <= 50
            assert chunk.artifact_uid == "art_test"


class TestOSINTDataFlow:
    """OSINT 数据流端到端测试。"""

    @pytest.mark.asyncio
    async def test_search_to_archive_flow(self) -> None:
        """测试从搜索到归档的数据流。"""
        # 1. 创建 SearxNG 客户端
        searxng_config = SearxNGConfig(
            base_url="http://localhost:8601",
        )
        searxng = SearxNGClient(searxng_config)

        # 2. 创建 ArchiveBox 客户端
        archive_config = ArchiveBoxConfig(
            use_api=False,
            docker_container="archivebox",
        )
        archive = ArchiveBoxClient(archive_config)

        # 模拟搜索结果
        mock_search_response = {
            "results": [
                {
                    "url": "https://example.com/article1",
                    "title": "测试文章",
                    "content": "文章摘要",
                    "engines": ["google"],
                    "score": 0.9,
                },
            ],
            "number_of_results": 1,
            "suggestions": [],
            "infoboxes": [],
        }

        # 模拟归档结果
        mock_archive_stdout = """
        [{"timestamp": "20240115120000", "url": "https://example.com/article1", "title": "测试文章", "content_sha256": "abc123", "mime_type": "text/html"}]
        """

        with (
            patch("httpx.AsyncClient.get") as mock_get,
            patch("asyncio.to_thread") as mock_thread,
        ):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: mock_search_response,
                raise_for_status=lambda: None,
            )

            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = mock_archive_stdout
            mock_process.stderr = ""
            mock_thread.return_value = mock_process

            # 执行搜索
            search_result = await searxng.search("测试查询", max_results=5)
            assert len(search_result.results) == 1

            # 归档搜索结果中的 URL
            for result in search_result.results:
                artifact = await archive.add_and_create_artifact(result.url)
                assert artifact.source_url == result.url
                assert artifact.origin_tool == "archivebox"

    @pytest.mark.asyncio
    async def test_scrape_to_parse_flow(self) -> None:
        """测试从抓取到解析的数据流。"""
        # 1. 创建 Firecrawl 客户端
        firecrawl_config = FirecrawlConfig(
            base_url="http://localhost:3002",
        )
        firecrawl = FirecrawlClient(firecrawl_config)

        # 2. 创建 Unstructured 客户端
        unstructured_config = UnstructuredConfig(
            api_url="http://localhost:8603/general/v0/general",
        )
        unstructured = UnstructuredClient(unstructured_config)

        # 模拟抓取结果
        mock_scrape_response = {
            "success": True,
            "data": {
                "url": "https://example.com/article",
                "markdown": "# 测试文章\n\n这是文章的正文内容。" * 10,
                "metadata": {
                    "title": "测试文章",
                    "sourceURL": "https://example.com/article",
                },
            },
        }

        # 模拟解析结果
        mock_parse_response = [
            {
                "element_id": "elem1",
                "type": "Title",
                "text": "测试文章",
                "metadata": {"page_number": 1},
            },
            {
                "element_id": "elem2",
                "type": "NarrativeText",
                "text": "这是文章的正文内容。" * 10,
                "metadata": {"page_number": 1},
            },
        ]

        with patch("httpx.AsyncClient.post") as mock_post:
            # 第一次调用是 Firecrawl，第二次是 Unstructured
            mock_post.side_effect = [
                MagicMock(
                    status_code=200,
                    json=lambda: mock_scrape_response,
                    raise_for_status=lambda: None,
                ),
                MagicMock(
                    status_code=200,
                    json=lambda: mock_parse_response,
                    raise_for_status=lambda: None,
                ),
            ]

            # 执行抓取
            scrape_result = await firecrawl.scrape(
                url="https://example.com/article",
            )
            assert scrape_result.markdown.startswith("# 测试文章")

            # 解析抓取内容
            chunk_result = await unstructured.parse_and_chunk(
                file_content=scrape_result.markdown.encode("utf-8"),
                filename="article.md",
                artifact_uid="art_test123",
                content_type="text/markdown",
                chunk_size=100,
            )

            assert chunk_result.total_chunks > 0
            for chunk in chunk_result.chunks:
                assert chunk.artifact_uid == "art_test123"
