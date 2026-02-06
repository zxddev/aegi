"""Qdrant 向量存储模块。

提供以下功能：
- 文档块（Chunk）的向量索引与语义搜索
- 集合生命周期管理
- 批量操作支持
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from baize_core.config.settings import QdrantConfig

logger = logging.getLogger(__name__)

# 尝试导入 qdrant_client，如果未安装则提供 stub
try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except ImportError:
    AsyncQdrantClient = None
    Distance = None
    FieldCondition = None
    Filter = None
    MatchValue = None
    PointStruct = None
    VectorParams = None


# 默认向量维度（根据 embedding 模型调整）
DEFAULT_VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small
DEFAULT_COLLECTION_NAME = "chunks"


@dataclass
class VectorSearchResult:
    """向量搜索结果。"""

    chunk_uid: str
    artifact_uid: str
    text: str
    score: float
    metadata: dict[str, Any]


class QdrantStore:
    """Qdrant 向量存储管理器。"""

    def __init__(
        self,
        config: QdrantConfig | str,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        """初始化 Qdrant 客户端。

        Args:
            config: Qdrant 配置
            collection_name: 集合名称
            vector_size: 向量维度
        """
        if AsyncQdrantClient is None:
            raise ImportError("qdrant_client 未安装。请运行: pip install qdrant-client")
        if isinstance(config, str):
            config = QdrantConfig(url=config, grpc_url="", api_key="")
        self._config = config
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._client: AsyncQdrantClient | None = None

    async def connect(self) -> None:
        """建立连接。"""
        if self._client is not None:
            return
        # 优先使用 gRPC 连接
        if self._config.grpc_url:
            self._client = AsyncQdrantClient(
                url=self._config.grpc_url,
                api_key=self._config.api_key if self._config.api_key else None,
                prefer_grpc=True,
            )
        else:
            self._client = AsyncQdrantClient(
                url=self._config.url,
                api_key=self._config.api_key if self._config.api_key else None,
            )
        logger.info("Qdrant 连接已建立: %s", self._config.url)

    async def close(self) -> None:
        """关闭连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Qdrant 连接已关闭")

    def _ensure_connected(self) -> AsyncQdrantClient:
        """确保已连接。"""
        if self._client is None:
            raise RuntimeError("Qdrant 未连接，请先调用 connect()")
        return self._client

    # ========== 集合管理 ==========

    async def create_collection(self, recreate: bool = False) -> None:
        """创建集合。

        Args:
            recreate: 如果为 True，先删除再创建
        """
        client = self._ensure_connected()
        exists = await client.collection_exists(self._collection_name)
        if exists:
            if recreate:
                await client.delete_collection(self._collection_name)
                logger.info("删除已存在的集合: %s", self._collection_name)
            else:
                logger.debug("集合已存在: %s", self._collection_name)
                return
        await client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(
                size=self._vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "创建集合: %s (向量维度: %d)", self._collection_name, self._vector_size
        )

    async def delete_collection(self) -> None:
        """删除集合。"""
        client = self._ensure_connected()
        exists = await client.collection_exists(self._collection_name)
        if exists:
            await client.delete_collection(self._collection_name)
            logger.info("删除集合: %s", self._collection_name)

    async def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息。"""
        client = self._ensure_connected()
        try:
            info = await client.get_collection(self._collection_name)
            vectors_count = getattr(info, "vectors_count", None)
            if vectors_count is None:
                vectors_count = getattr(info, "indexed_vectors_count", None)
            return {
                "name": self._collection_name,
                "vectors_count": vectors_count,
                "points_count": info.points_count,
                "status": info.status.value if info.status else None,
                "vector_size": self._vector_size,
            }
        except Exception as e:
            return {"error": str(e)}

    # ========== Chunk 操作 ==========

    async def upsert_chunk(
        self,
        chunk_uid: str,
        artifact_uid: str,
        text: str,
        embedding: list[float],
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """插入或更新单个 Chunk 向量。

        Args:
            chunk_uid: Chunk 唯一标识
            artifact_uid: Artifact 唯一标识
            text: 原始文本
            embedding: 向量表示
            task_id: 可选，关联的任务 ID
            metadata: 额外元数据
        """
        client = self._ensure_connected()
        point = PointStruct(
            id=chunk_uid,
            vector=embedding,
            payload={
                "chunk_uid": chunk_uid,
                "artifact_uid": artifact_uid,
                "text": text,
                "task_id": task_id,
                **(metadata or {}),
            },
        )
        await client.upsert(
            collection_name=self._collection_name,
            points=[point],
        )

    async def index_chunk(self, *, chunk_uid: str, text: str) -> None:
        """按最低信息写入向量索引。"""
        embedding = [0.0] * self._vector_size
        await self.upsert_chunk(
            chunk_uid=chunk_uid,
            artifact_uid="unknown",
            text=text,
            embedding=embedding,
        )

    async def upsert_chunks_batch(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """批量插入或更新 Chunk 向量。

        Args:
            chunks: Chunk 列表，每个包含 chunk_uid, artifact_uid, text, embedding

        Returns:
            成功插入的数量
        """
        if not chunks:
            return 0
        client = self._ensure_connected()
        points: list[PointStruct] = []
        for chunk in chunks:
            points.append(
                PointStruct(
                    id=chunk["chunk_uid"],
                    vector=chunk["embedding"],
                    payload={
                        "chunk_uid": chunk["chunk_uid"],
                        "artifact_uid": chunk["artifact_uid"],
                        "text": chunk["text"],
                        "task_id": chunk.get("task_id"),
                        **(chunk.get("metadata") or {}),
                    },
                )
            )
        await client.upsert(
            collection_name=self._collection_name,
            points=points,
        )
        return len(points)

    async def search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        artifact_uid: str | None = None,
        task_id: str | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        """语义搜索 Chunk。

        Args:
            query_embedding: 查询向量
            limit: 返回结果数量
            artifact_uid: 可选，限定 artifact
            task_id: 可选，限定 task
            score_threshold: 可选，最低相似度阈值

        Returns:
            搜索结果列表
        """
        client = self._ensure_connected()
        # 构建过滤条件
        filter_conditions: list[FieldCondition] = []
        if artifact_uid:
            filter_conditions.append(
                FieldCondition(
                    key="artifact_uid",
                    match=MatchValue(value=artifact_uid),
                )
            )
        if task_id:
            filter_conditions.append(
                FieldCondition(
                    key="task_id",
                    match=MatchValue(value=task_id),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = Filter(must=filter_conditions)

        results = await client.search(
            collection_name=self._collection_name,
            query_vector=query_embedding,
            limit=limit,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        search_results: list[VectorSearchResult] = []
        for hit in results:
            payload = hit.payload or {}
            search_results.append(
                VectorSearchResult(
                    chunk_uid=payload.get("chunk_uid", str(hit.id)),
                    artifact_uid=payload.get("artifact_uid", ""),
                    text=payload.get("text", ""),
                    score=hit.score,
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k not in {"chunk_uid", "artifact_uid", "text"}
                    },
                )
            )
        return search_results

    async def delete_chunk(self, chunk_uid: str) -> bool:
        """删除 Chunk。

        Args:
            chunk_uid: Chunk 唯一标识

        Returns:
            是否成功删除
        """
        client = self._ensure_connected()
        try:
            await client.delete(
                collection_name=self._collection_name,
                points_selector=[chunk_uid],
            )
            return True
        except Exception as e:
            logger.warning("删除 Chunk 失败: %s, 错误: %s", chunk_uid, e)
            return False

    async def delete_chunks_by_artifact(self, artifact_uid: str) -> int:
        """删除指定 artifact 的所有 Chunk。

        Args:
            artifact_uid: Artifact 唯一标识

        Returns:
            删除的数量（估计值）
        """
        client = self._ensure_connected()
        # 先查询数量
        count_result = await client.count(
            collection_name=self._collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="artifact_uid",
                        match=MatchValue(value=artifact_uid),
                    )
                ]
            ),
        )
        count = count_result.count

        # 执行删除
        await client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="artifact_uid",
                        match=MatchValue(value=artifact_uid),
                    )
                ]
            ),
        )
        return count

    async def get_chunk(self, chunk_uid: str) -> VectorSearchResult | None:
        """获取单个 Chunk。

        Args:
            chunk_uid: Chunk 唯一标识

        Returns:
            Chunk 信息，如果不存在则返回 None
        """
        client = self._ensure_connected()
        try:
            points = await client.retrieve(
                collection_name=self._collection_name,
                ids=[chunk_uid],
            )
            if not points:
                return None
            point = points[0]
            payload = point.payload or {}
            return VectorSearchResult(
                chunk_uid=payload.get("chunk_uid", str(point.id)),
                artifact_uid=payload.get("artifact_uid", ""),
                text=payload.get("text", ""),
                score=1.0,  # 直接获取没有相似度分数
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k not in {"chunk_uid", "artifact_uid", "text"}
                },
            )
        except Exception as e:
            logger.warning("获取 Chunk 失败: %s, 错误: %s", chunk_uid, e)
            return None
