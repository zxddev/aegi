"""OpenSearch 存储测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from baize_core.config.settings import OpenSearchConfig
from baize_core.storage.opensearch_store import (
    AUDIT_INDEX_MAPPING,
    CHUNK_INDEX_MAPPING,
    OpenSearchStore,
)


@pytest.fixture
def opensearch_config() -> OpenSearchConfig:
    """OpenSearch 配置 fixture。"""
    return OpenSearchConfig(
        host="localhost",
        port=9200,
        use_ssl=False,
        verify_certs=False,
        http_auth_user="admin",
        http_auth_password="admin",
        chunk_index="test_chunks",
        audit_index="test_audit",
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock OpenSearch 客户端。"""
    client = AsyncMock()
    client.indices = AsyncMock()
    client.indices.exists = AsyncMock(return_value=False)
    client.indices.create = AsyncMock()
    client.indices.delete = AsyncMock()
    client.indices.refresh = AsyncMock()
    client.indices.stats = AsyncMock(
        return_value={"_all": {"total": {"docs": {"count": 100}}}}
    )
    client.index = AsyncMock()
    client.bulk = AsyncMock(return_value={"errors": False, "items": []})
    client.search = AsyncMock(
        return_value={"hits": {"hits": [], "total": {"value": 0}}}
    )
    client.delete = AsyncMock()
    client.delete_by_query = AsyncMock(return_value={"deleted": 5})
    client.close = AsyncMock()
    return client


class TestOpenSearchStoreConnection:
    """连接管理测试。"""

    @pytest.mark.asyncio
    async def test_connect(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试连接。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            assert store._client is not None

    @pytest.mark.asyncio
    async def test_close(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试关闭连接。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.close()
            mock_client.close.assert_called_once()
            assert store._client is None


class TestIndexManagement:
    """索引管理测试。"""

    @pytest.mark.asyncio
    async def test_create_chunk_index(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试创建 Chunk 索引。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.create_chunk_index()
            mock_client.indices.exists.assert_called()
            mock_client.indices.create.assert_called_once_with(
                index="test_chunks", body=CHUNK_INDEX_MAPPING
            )

    @pytest.mark.asyncio
    async def test_create_audit_index(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试创建审计索引。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.create_audit_index()
            mock_client.indices.exists.assert_called()
            mock_client.indices.create.assert_called_once_with(
                index="test_audit", body=AUDIT_INDEX_MAPPING
            )

    @pytest.mark.asyncio
    async def test_create_index_already_exists(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试索引已存在时不重复创建。"""
        mock_client.indices.exists = AsyncMock(return_value=True)
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.create_chunk_index()
            mock_client.indices.create.assert_not_called()


class TestChunkOperations:
    """Chunk 操作测试。"""

    @pytest.mark.asyncio
    async def test_index_chunk(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试索引 Chunk。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.index_chunk(
                chunk_uid="chk_123",
                artifact_uid="art_456",
                text="测试文本内容",
                text_sha256="abc123",
                anchor={"type": "text_offset", "ref": "0-100"},
                task_id="task_789",
            )
            mock_client.index.assert_called_once()
            call_kwargs = mock_client.index.call_args[1]
            assert call_kwargs["index"] == "test_chunks"
            assert call_kwargs["id"] == "chk_123"
            assert call_kwargs["body"]["text"] == "测试文本内容"

    @pytest.mark.asyncio
    async def test_index_chunks_bulk(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试批量索引 Chunk。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            chunks = [
                {
                    "chunk_uid": "chk_1",
                    "artifact_uid": "art_1",
                    "text": "文本1",
                    "text_sha256": "hash1",
                    "anchor": {"type": "text_offset", "ref": "0-10"},
                },
                {
                    "chunk_uid": "chk_2",
                    "artifact_uid": "art_1",
                    "text": "文本2",
                    "text_sha256": "hash2",
                    "anchor": {"type": "text_offset", "ref": "10-20"},
                },
            ]
            count = await store.index_chunks_bulk(chunks)
            assert count == 2
            mock_client.bulk.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_chunks(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试搜索 Chunk。"""
        mock_client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "chunk_uid": "chk_1",
                                "artifact_uid": "art_1",
                                "text": "测试文本",
                            },
                            "_score": 1.5,
                            "highlight": {"text": ["<em>测试</em>文本"]},
                        }
                    ],
                    "total": {"value": 1},
                }
            }
        )
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            results = await store.search_chunks("测试", max_results=5)
            assert len(results) == 1
            assert results[0].chunk_uid == "chk_1"
            assert results[0].score == 1.5
            assert "<em>测试</em>" in results[0].highlights[0]

    @pytest.mark.asyncio
    async def test_delete_chunk(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试删除 Chunk。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            result = await store.delete_chunk("chk_1")
            assert result is True
            mock_client.delete.assert_called_once_with(index="test_chunks", id="chk_1")

    @pytest.mark.asyncio
    async def test_delete_chunks_by_artifact(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试删除 artifact 的所有 Chunk。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            count = await store.delete_chunks_by_artifact("art_1")
            assert count == 5
            mock_client.delete_by_query.assert_called_once()


class TestAuditOperations:
    """审计操作测试。"""

    @pytest.mark.asyncio
    async def test_index_audit_event(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试索引审计事件。"""
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            await store.index_audit_event(
                event_id="evt_123",
                event_type="tool_call",
                timestamp=datetime.now(UTC),
                task_id="task_1",
                tool_name="web_crawl",
                success=True,
                duration_ms=500,
            )
            mock_client.index.assert_called_once()
            call_kwargs = mock_client.index.call_args[1]
            assert call_kwargs["index"] == "test_audit"
            assert call_kwargs["id"] == "evt_123"

    @pytest.mark.asyncio
    async def test_search_audit_events(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试搜索审计事件。"""
        mock_client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_source": {
                                "event_id": "evt_1",
                                "event_type": "tool_call",
                                "task_id": "task_1",
                                "trace_id": "trace_1",
                                "timestamp": "2024-01-01T12:00:00+00:00",
                                "tool_name": "web_crawl",
                                "success": True,
                                "duration_ms": 500,
                            }
                        }
                    ],
                    "total": {"value": 1},
                }
            }
        )
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            results = await store.search_audit_events(event_type="tool_call")
            assert len(results) == 1
            assert results[0].event_id == "evt_1"
            assert results[0].tool_name == "web_crawl"

    @pytest.mark.asyncio
    async def test_get_audit_stats(
        self, opensearch_config: OpenSearchConfig, mock_client: AsyncMock
    ) -> None:
        """测试获取审计统计。"""
        mock_client.search = AsyncMock(
            return_value={
                "hits": {"total": {"value": 100}},
                "aggregations": {
                    "by_event_type": {
                        "buckets": [
                            {"key": "tool_call", "doc_count": 50},
                            {"key": "model_call", "doc_count": 30},
                        ]
                    },
                    "by_tool": {
                        "buckets": [
                            {"key": "web_crawl", "doc_count": 25},
                        ]
                    },
                    "by_model": {
                        "buckets": [
                            {"key": "gpt-4", "doc_count": 30},
                        ]
                    },
                    "success_rate": {"value": 0.95},
                    "avg_duration": {"value": 350.5},
                },
            }
        )
        with patch(
            "baize_core.storage.opensearch_store.AsyncOpenSearch",
            return_value=mock_client,
        ):
            store = OpenSearchStore(opensearch_config)
            await store.connect()
            stats = await store.get_audit_stats()
            assert stats["total_events"] == 100
            assert len(stats["by_event_type"]) == 2
            assert stats["success_rate"] == 0.95
            assert stats["avg_duration_ms"] == 350.5
