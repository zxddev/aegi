# Author: msq
"""Dependency injection providers for FastAPI."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.session import ENGINE
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.minio_store import MinioStore
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.tool_client import ToolClient
from aegi_core.settings import settings


# ── DB ──────────────────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        yield session


# ── LLM ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        default_model=settings.litellm_default_model,
    )


# keep old name for backward compat
def get_llm_backend() -> LLMClient:
    """Returns LLMClient that also satisfies LLMBackend protocol via invoke_as_backend."""
    return get_llm_client()


# ── Tool client ─────────────────────────────────────────────────────


def get_tool_client() -> ToolClient:
    return ToolClient(base_url=settings.mcp_gateway_base_url)


# ── Neo4j ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_neo4j_store() -> Neo4jStore:
    return Neo4jStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )


# ── Qdrant ──────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_qdrant_store() -> QdrantStore:
    return QdrantStore(url=settings.qdrant_url)


# ── MinIO ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_minio_store() -> MinioStore:
    # endpoint is host:port without scheme
    endpoint = settings.s3_endpoint_url.replace("http://", "").replace("https://", "")
    return MinioStore(
        endpoint=endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        secure=settings.s3_endpoint_url.startswith("https"),
    )
