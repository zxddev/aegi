# Author: msq
"""Ingest helpers — embed chunks to Qdrant, store artifacts to MinIO."""

from __future__ import annotations

import hashlib
from typing import Any

from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.minio_store import MinioStore
from aegi_core.infra.qdrant_store import QdrantStore


async def embed_and_index_chunk(
    *,
    chunk_uid: str,
    text: str,
    llm: LLMClient,
    qdrant: QdrantStore,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Embed a text chunk via LLM and index it in Qdrant."""
    embedding = await llm.embed(text)
    await qdrant.upsert(chunk_uid, embedding, text, metadata)


async def embed_and_index_chunks_batch(
    *,
    chunks: list[dict[str, Any]],
    llm: LLMClient,
    qdrant: QdrantStore,
) -> int:
    """Batch embed + index. Each chunk dict needs 'chunk_uid' and 'text'."""
    points = []
    for c in chunks:
        embedding = await llm.embed(c["text"])
        points.append(
            {
                "chunk_uid": c["chunk_uid"],
                "embedding": embedding,
                "text": c["text"],
                "metadata": c.get("metadata", {}),
            }
        )
    return await qdrant.upsert_batch(points)


async def store_artifact_to_minio(
    *,
    content: bytes,
    content_type: str,
    minio: MinioStore,
) -> str:
    """Store artifact content in MinIO, return storage_ref (minio://bucket/key)."""
    sha = hashlib.sha256(content).hexdigest()
    object_name = f"artifacts/{sha[:4]}/{sha}"
    return await minio.put_bytes(object_name, content, content_type)


async def semantic_search(
    *,
    query: str,
    llm: LLMClient,
    qdrant: QdrantStore,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Embed query and search Qdrant for similar chunks."""
    embedding = await llm.embed(query)
    results = await qdrant.search(embedding, limit=limit)
    return [
        {"chunk_uid": r.chunk_uid, "text": r.text, "score": r.score, **r.metadata}
        for r in results
    ]
