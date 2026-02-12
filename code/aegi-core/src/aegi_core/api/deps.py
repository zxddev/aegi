# Author: msq
"""FastAPI 依赖注入提供者。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.session import ENGINE
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.minio_store import MinioStore
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.causal_inference import CausalInferenceEngine
from aegi_core.services.link_predictor import LinkPredictor
from aegi_core.services.tool_client import ToolClient
from aegi_core.settings import settings

if TYPE_CHECKING:
    from aegi_core.infra.gdelt_client import GDELTClient
    from aegi_core.infra.searxng_client import SearXNGClient


# ── DB ──────────────────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        yield session


# ── LLM ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    import json

    extra: dict[str, str] | None = None
    if settings.litellm_extra_headers:
        extra = json.loads(settings.litellm_extra_headers)
    return LLMClient(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        default_model=settings.litellm_default_model,
        extra_headers=extra,
    )


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


@lru_cache(maxsize=1)
def get_link_predictor() -> LinkPredictor:
    return LinkPredictor(neo4j=get_neo4j_store())


@lru_cache(maxsize=1)
def get_causal_inference_engine() -> CausalInferenceEngine:
    return CausalInferenceEngine(neo4j=get_neo4j_store())


# ── Qdrant ──────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_qdrant_store() -> QdrantStore:
    return QdrantStore(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


@lru_cache(maxsize=1)
def get_analysis_memory_qdrant_store() -> QdrantStore:
    return QdrantStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.analysis_memory_collection,
    )


# ── MinIO ───────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_minio_store() -> MinioStore:
    # endpoint 是 host:port，不带 scheme
    endpoint = settings.s3_endpoint_url.replace("http://", "").replace("https://", "")
    return MinioStore(
        endpoint=endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        secure=settings.s3_endpoint_url.startswith("https"),
    )


@lru_cache(maxsize=1)
def get_searxng_client() -> SearXNGClient:
    from aegi_core.infra.searxng_client import SearXNGClient

    return SearXNGClient(base_url=settings.searxng_base_url)


# ── GDELT ──────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_gdelt_client() -> GDELTClient:
    from aegi_core.infra.gdelt_client import GDELTClient

    proxy = settings.gdelt_proxy if settings.gdelt_proxy else None
    return GDELTClient(proxy=proxy)
