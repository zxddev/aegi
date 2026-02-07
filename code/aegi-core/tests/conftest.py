# Author: msq
"""全局测试配置。"""

import os

# 必须在任何 aegi_core 导入之前设置
os.environ.setdefault("AEGI_DB_USE_NULL_POOL", "true")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_infra_singletons():
    """每个测试后清除 lru_cache 单例，避免跨测试 event loop 污染。"""
    yield
    from aegi_core.api.deps import (
        get_llm_client,
        get_neo4j_store,
        get_qdrant_store,
        get_minio_store,
    )

    for cached_fn in (
        get_llm_client,
        get_neo4j_store,
        get_qdrant_store,
        get_minio_store,
    ):
        cached_fn.cache_clear()
