"""Qdrant 存储测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from baize_core.config.settings import QdrantConfig
from baize_core.storage.qdrant_store import (
    DEFAULT_VECTOR_SIZE,
    QdrantStore,
)


@pytest.fixture
def qdrant_config() -> QdrantConfig:
    """Qdrant 配置 fixture。"""
    return QdrantConfig(
        url="http://localhost:6333",
        grpc_url="http://localhost:6334",
        api_key="test_api_key",
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    """Mock Qdrant 客户端。"""
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.create_collection = AsyncMock()
    client.delete_collection = AsyncMock()
    client.get_collection = AsyncMock(
        return_value=MagicMock(
            vectors_count=100,
            points_count=100,
            status=MagicMock(value="green"),
        )
    )
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    client.delete = AsyncMock()
    client.count = AsyncMock(return_value=MagicMock(count=5))
    client.retrieve = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


class TestQdrantStoreConnection:
    """连接管理测试。"""

    @pytest.mark.asyncio
    async def test_connect(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试连接。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            assert store._client is not None

    @pytest.mark.asyncio
    async def test_close(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试关闭连接。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            await store.close()
            mock_client.close.assert_called_once()
            assert store._client is None


class TestCollectionManagement:
    """集合管理测试。"""

    @pytest.mark.asyncio
    async def test_create_collection(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试创建集合。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            await store.create_collection()
            mock_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_collection_already_exists(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试集合已存在时不重复创建。"""
        mock_client.collection_exists = AsyncMock(return_value=True)
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            await store.create_collection()
            mock_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_collection_recreate(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试重新创建集合。"""
        mock_client.collection_exists = AsyncMock(return_value=True)
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            await store.create_collection(recreate=True)
            mock_client.delete_collection.assert_called_once()
            mock_client.create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_collection_info(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试获取集合信息。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            info = await store.get_collection_info()
            assert info["vectors_count"] == 100
            assert info["points_count"] == 100


class TestChunkOperations:
    """Chunk 操作测试。"""

    @pytest.mark.asyncio
    async def test_upsert_chunk(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试插入 Chunk。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            embedding = [0.1] * DEFAULT_VECTOR_SIZE
            await store.upsert_chunk(
                chunk_uid="chk_123",
                artifact_uid="art_456",
                text="测试文本",
                embedding=embedding,
                task_id="task_789",
            )
            mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_chunks_batch(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试批量插入 Chunk。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            embedding = [0.1] * DEFAULT_VECTOR_SIZE
            chunks = [
                {
                    "chunk_uid": "chk_1",
                    "artifact_uid": "art_1",
                    "text": "文本1",
                    "embedding": embedding,
                },
                {
                    "chunk_uid": "chk_2",
                    "artifact_uid": "art_1",
                    "text": "文本2",
                    "embedding": embedding,
                },
            ]
            count = await store.upsert_chunks_batch(chunks)
            assert count == 2
            mock_client.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_search(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试搜索 Chunk。"""
        mock_hit = MagicMock()
        mock_hit.id = "chk_1"
        mock_hit.score = 0.95
        mock_hit.payload = {
            "chunk_uid": "chk_1",
            "artifact_uid": "art_1",
            "text": "测试文本",
            "task_id": "task_1",
        }
        mock_client.search = AsyncMock(return_value=[mock_hit])
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            embedding = [0.1] * DEFAULT_VECTOR_SIZE
            results = await store.search(query_embedding=embedding, limit=5)
            assert len(results) == 1
            assert results[0].chunk_uid == "chk_1"
            assert results[0].score == 0.95
            assert results[0].text == "测试文本"

    @pytest.mark.asyncio
    async def test_search_with_filter(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试带过滤条件的搜索。"""
        mock_client.search = AsyncMock(return_value=[])
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            embedding = [0.1] * DEFAULT_VECTOR_SIZE
            await store.search(
                query_embedding=embedding,
                limit=5,
                artifact_uid="art_1",
                task_id="task_1",
            )
            call_kwargs = mock_client.search.call_args[1]
            assert call_kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_delete_chunk(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试删除 Chunk。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            result = await store.delete_chunk("chk_1")
            assert result is True
            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_chunks_by_artifact(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试删除 artifact 的所有 Chunk。"""
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            count = await store.delete_chunks_by_artifact("art_1")
            assert count == 5
            mock_client.count.assert_called_once()
            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_chunk(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试获取 Chunk。"""
        mock_point = MagicMock()
        mock_point.id = "chk_1"
        mock_point.payload = {
            "chunk_uid": "chk_1",
            "artifact_uid": "art_1",
            "text": "测试文本",
        }
        mock_client.retrieve = AsyncMock(return_value=[mock_point])
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            result = await store.get_chunk("chk_1")
            assert result is not None
            assert result.chunk_uid == "chk_1"
            assert result.text == "测试文本"

    @pytest.mark.asyncio
    async def test_get_chunk_not_found(
        self, qdrant_config: QdrantConfig, mock_client: AsyncMock
    ) -> None:
        """测试获取不存在的 Chunk。"""
        mock_client.retrieve = AsyncMock(return_value=[])
        with patch(
            "baize_core.storage.qdrant_store.AsyncQdrantClient",
            return_value=mock_client,
        ):
            store = QdrantStore(qdrant_config)
            await store.connect()
            result = await store.get_chunk("chk_not_exist")
            assert result is None
