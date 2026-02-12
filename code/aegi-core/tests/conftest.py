# Author: msq
"""全局测试配置。"""

import os
import socket

# 必须在任何 aegi_core 导入之前设置
os.environ.setdefault("AEGI_DB_USE_NULL_POOL", "true")

import pytest  # noqa: E402


# ── 外部服务可用性检测 ──────────────────────────────────────────


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """检测 TCP 端口是否可达。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_pg_available = _port_open("127.0.0.1", 8710)


def _llm_healthy(timeout: float = 5.0) -> bool:
    """检测 LLM 是否真正可用（端口 + 实际调用）。"""
    from aegi_core.settings import settings
    from urllib.parse import urlparse

    parsed = urlparse(settings.litellm_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 443
    if not _port_open(host, port):
        return False
    try:
        import httpx
        import json as _json

        hdrs = {
            "Authorization": f"Bearer {settings.litellm_api_key}",
            "Content-Type": "application/json",
        }
        if settings.litellm_extra_headers:
            hdrs.update(_json.loads(settings.litellm_extra_headers))
        resp = httpx.post(
            f"{settings.litellm_base_url}/v1/chat/completions",
            json={
                "model": settings.litellm_default_model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
                "stream": False,
            },
            headers=hdrs,
            timeout=timeout,
        )
        return resp.status_code == 200
    except Exception:
        return False


_llm_available = _llm_healthy()
_qdrant_available = _port_open("127.0.0.1", 8716)
_gateway_available = _port_open("127.0.0.1", 8704)
_neo4j_available = _port_open("127.0.0.1", 8715)

requires_postgres = pytest.mark.skipif(
    not _pg_available, reason="PostgreSQL (port 8710) 不可用"
)
requires_llm = pytest.mark.skipif(
    not _llm_available, reason="LiteLLM Proxy (port 8713) 不可用"
)
requires_qdrant = pytest.mark.skipif(
    not _qdrant_available, reason="Qdrant (port 8716) 不可用"
)
requires_gateway = pytest.mark.skipif(
    not _gateway_available, reason="MCP Gateway (port 8704) 不可用"
)
requires_neo4j = pytest.mark.skipif(
    not _neo4j_available, reason="Neo4j (port 8715) 不可用"
)


def _searxng_json_api_available() -> bool:
    """检测 SearXNG JSON API 是否可用（不只是端口通）。"""
    if not _port_open("127.0.0.1", 8888):
        return False
    try:
        import httpx

        resp = httpx.get(
            "http://localhost:8888/search",
            params={"q": "test", "format": "json"},
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


_searxng_available = _searxng_json_api_available()
requires_searxng = pytest.mark.skipif(
    not _searxng_available, reason="SearXNG JSON API (port 8888) 不可用"
)


@pytest.fixture(autouse=True)
def _reset_infra_singletons():
    """每个测试后清除 lru_cache 单例，避免跨测试 event loop 污染。"""
    yield
    from aegi_core.api.deps import (
        get_llm_client,
        get_link_predictor,
        get_neo4j_store,
        get_qdrant_store,
        get_minio_store,
        get_gdelt_client,
    )

    for cached_fn in (
        get_llm_client,
        get_link_predictor,
        get_neo4j_store,
        get_qdrant_store,
        get_minio_store,
        get_gdelt_client,
    ):
        cached_fn.cache_clear()
