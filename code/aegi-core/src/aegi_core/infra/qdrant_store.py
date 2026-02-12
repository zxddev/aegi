# Author: msq
"""Qdrant 向量存储 — AEGI chunk embedding + 语义搜索。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid5, NAMESPACE_URL

logger = logging.getLogger(__name__)

DEFAULT_VECTOR_SIZE = 1024  # BGE-M3
DEFAULT_COLLECTION = "aegi_chunks"


@dataclass
class VectorSearchResult:
    chunk_uid: str
    text: str
    score: float
    metadata: dict[str, Any]


class QdrantStore:
    """Qdrant 向量存储。"""

    def __init__(
        self,
        url: str,
        *,
        grpc_url: str = "",
        collection: str = DEFAULT_COLLECTION,
        vector_size: int = DEFAULT_VECTOR_SIZE,
        api_key: str = "",
    ) -> None:
        from qdrant_client import AsyncQdrantClient

        self._url = url
        self._api_key = api_key
        self._collection = collection
        self._vector_size = vector_size
        kw: dict = {"url": url, "check_compatibility": False}
        if api_key:
            kw["api_key"] = api_key
        self._client: AsyncQdrantClient = AsyncQdrantClient(**kw)

    async def connect(self) -> None:
        """确保 collection 存在。如果之前关闭过则重新连接。"""
        if self._client is None:
            from qdrant_client import AsyncQdrantClient

            kw: dict = {"url": self._url, "check_compatibility": False}
            if self._api_key:
                kw["api_key"] = self._api_key
            self._client = AsyncQdrantClient(**kw)
        from qdrant_client.http.models import Distance, VectorParams

        exists = await self._client.collection_exists(self._collection)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_size, distance=Distance.COSINE
                ),
            )
            logger.info("Created Qdrant collection: %s", self._collection)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def upsert(
        self,
        chunk_uid: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from qdrant_client.http.models import PointStruct

        assert self._client is not None
        point_id = str(uuid5(NAMESPACE_URL, chunk_uid))
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={"chunk_uid": chunk_uid, "text": text, **(metadata or {})},
                )
            ],
        )

    async def upsert_batch(self, points: list[dict[str, Any]]) -> int:
        from qdrant_client.http.models import PointStruct

        assert self._client is not None
        if not points:
            return 0
        ps = [
            PointStruct(
                id=str(uuid5(NAMESPACE_URL, p["chunk_uid"])),
                vector=p["embedding"],
                payload={
                    "chunk_uid": p["chunk_uid"],
                    "text": p["text"],
                    **p.get("metadata", {}),
                },
            )
            for p in points
        ]
        await self._client.upsert(collection_name=self._collection, points=ps)
        return len(ps)

    async def search(
        self,
        query_embedding: list[float],
        *,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[VectorSearchResult]:
        assert self._client is not None
        results = await self._client.query_points(
            collection_name=self._collection,
            query=query_embedding,
            limit=limit,
            score_threshold=score_threshold,
        )
        return [
            VectorSearchResult(
                chunk_uid=(hit.payload or {}).get("chunk_uid", str(hit.id)),
                text=(hit.payload or {}).get("text", ""),
                score=hit.score,
                metadata={
                    k: v
                    for k, v in (hit.payload or {}).items()
                    if k not in {"chunk_uid", "text"}
                },
            )
            for hit in results.points
        ]

    async def delete(self, chunk_uid: str) -> None:
        assert self._client is not None
        point_id = str(uuid5(NAMESPACE_URL, chunk_uid))
        await self._client.delete(
            collection_name=self._collection, points_selector=[point_id]
        )
