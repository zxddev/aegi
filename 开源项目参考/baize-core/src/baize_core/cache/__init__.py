"""缓存模块。

支持多后端缓存：内存、Redis。
"""

from baize_core.cache.redis_cache import (
    CacheConfig,
    CacheEntry,
    CacheStats,
    InMemoryCache,
    RedisCache,
)

__all__ = [
    "CacheConfig",
    "CacheEntry",
    "CacheStats",
    "InMemoryCache",
    "RedisCache",
]
