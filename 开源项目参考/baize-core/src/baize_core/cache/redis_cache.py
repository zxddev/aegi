"""Redis 缓存实现。

实现：
- 多类型缓存（字符串、JSON、二进制）
- TTL 管理
- 批量操作
- 缓存统计
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CacheType(str, Enum):
    """缓存类型。"""

    STRING = "string"
    JSON = "json"
    BINARY = "binary"


class CacheEntry(BaseModel):
    """缓存条目。"""

    key: str = Field(description="缓存键")
    value: Any = Field(description="缓存值")
    cache_type: CacheType = Field(default=CacheType.STRING)
    ttl_seconds: int | None = Field(default=None, description="TTL（秒）")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(default=None)
    hit_count: int = Field(default=0)


class CacheStats(BaseModel):
    """缓存统计。"""

    hits: int = Field(default=0, description="命中次数")
    misses: int = Field(default=0, description="未命中次数")
    sets: int = Field(default=0, description="设置次数")
    deletes: int = Field(default=0, description="删除次数")
    expired: int = Field(default=0, description="过期次数")
    size: int = Field(default=0, description="当前条目数")
    memory_bytes: int = Field(default=0, description="内存占用（字节）")

    @property
    def hit_rate(self) -> float:
        """命中率。"""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class CacheConfig(BaseModel):
    """缓存配置。"""

    # Redis 配置
    redis_url: str = Field(default="redis://localhost:6379/0")
    key_prefix: str = Field(default="baize_core:", description="键前缀")

    # TTL 配置
    default_ttl_seconds: int = Field(default=3600, description="默认 TTL")
    max_ttl_seconds: int = Field(default=86400, description="最大 TTL")

    # 内存缓存配置（L1）
    enable_l1_cache: bool = Field(default=True, description="启用 L1 缓存")
    l1_max_size: int = Field(default=1000, description="L1 最大条目数")
    l1_ttl_seconds: int = Field(default=60, description="L1 TTL")

    # 连接配置
    max_connections: int = Field(default=10, description="最大连接数")
    socket_timeout: float = Field(default=5.0, description="Socket 超时（秒）")


@runtime_checkable
class CacheBackend(Protocol):
    """缓存后端接口。"""

    async def get(self, key: str) -> Any | None:
        """获取缓存。"""
        ...

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """设置缓存。"""
        ...

    async def delete(self, key: str) -> bool:
        """删除缓存。"""
        ...

    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        ...

    async def get_stats(self) -> CacheStats:
        """获取统计信息。"""
        ...


@dataclass
class InMemoryCache:
    """内存缓存实现。"""

    max_size: int = 1000
    default_ttl: int = 3600

    _store: dict[str, CacheEntry] = field(default_factory=dict)
    _stats: CacheStats = field(default_factory=CacheStats)

    async def get(self, key: str) -> Any | None:
        """获取缓存。"""
        entry = self._store.get(key)
        if entry is None:
            self._stats.misses += 1
            return None

        # 检查过期
        if entry.expires_at and datetime.now(UTC) > entry.expires_at:
            del self._store[key]
            self._stats.misses += 1
            self._stats.expired += 1
            return None

        entry.hit_count += 1
        self._stats.hits += 1
        return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """设置缓存。"""
        # 检查容量
        if len(self._store) >= self.max_size and key not in self._store:
            # 淘汰最旧的条目
            oldest_key = min(
                self._store.keys(),
                key=lambda k: self._store[k].created_at,
            )
            del self._store[oldest_key]

        ttl = ttl_seconds or self.default_ttl
        expires_at = None
        if ttl > 0:
            from datetime import timedelta

            expires_at = datetime.now(UTC) + timedelta(seconds=ttl)

        self._store[key] = CacheEntry(
            key=key,
            value=value,
            ttl_seconds=ttl,
            expires_at=expires_at,
        )
        self._stats.sets += 1
        self._stats.size = len(self._store)

    async def delete(self, key: str) -> bool:
        """删除缓存。"""
        if key in self._store:
            del self._store[key]
            self._stats.deletes += 1
            self._stats.size = len(self._store)
            return True
        return False

    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        entry = self._store.get(key)
        if entry is None:
            return False
        if entry.expires_at and datetime.now(UTC) > entry.expires_at:
            del self._store[key]
            return False
        return True

    async def get_stats(self) -> CacheStats:
        """获取统计信息。"""
        self._stats.size = len(self._store)
        return self._stats

    async def clear(self) -> int:
        """清空缓存。"""
        count = len(self._store)
        self._store.clear()
        self._stats.size = 0
        return count

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取。"""
        results = {}
        for key in keys:
            value = await self.get(key)
            if value is not None:
                results[key] = value
        return results

    async def set_many(
        self,
        items: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """批量设置。"""
        for key, value in items.items():
            await self.set(key, value, ttl_seconds)

    async def delete_many(self, keys: list[str]) -> int:
        """批量删除。"""
        count = 0
        for key in keys:
            if await self.delete(key):
                count += 1
        return count


@dataclass
class RedisCache:
    """Redis 缓存实现。"""

    config: CacheConfig = field(default_factory=CacheConfig)

    _client: Any = None
    _l1_cache: InMemoryCache | None = None
    _stats: CacheStats = field(default_factory=CacheStats)

    async def connect(self) -> None:
        """连接 Redis。"""
        import redis.asyncio as redis

        self._client = redis.from_url(
            self.config.redis_url,
            max_connections=self.config.max_connections,
            socket_timeout=self.config.socket_timeout,
        )

        # 初始化 L1 缓存
        if self.config.enable_l1_cache:
            self._l1_cache = InMemoryCache(
                max_size=self.config.l1_max_size,
                default_ttl=self.config.l1_ttl_seconds,
            )

    async def close(self) -> None:
        """关闭连接。"""
        if self._client:
            await self._client.close()
            self._client = None

    def _make_key(self, key: str) -> str:
        """生成完整键名。"""
        return f"{self.config.key_prefix}{key}"

    async def get(self, key: str) -> Any | None:
        """获取缓存。"""
        # L1 缓存
        if self._l1_cache:
            l1_value = await self._l1_cache.get(key)
            if l1_value is not None:
                return l1_value

        if self._client is None:
            return None

        full_key = self._make_key(key)
        try:
            value = await self._client.get(full_key)
            if value is None:
                self._stats.misses += 1
                return None

            self._stats.hits += 1

            # 尝试 JSON 解析
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                decoded = value.decode("utf-8") if isinstance(value, bytes) else value

            # 写入 L1
            if self._l1_cache:
                await self._l1_cache.set(key, decoded)

            return decoded

        except Exception:
            self._stats.misses += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        """设置缓存。"""
        if self._client is None:
            raise RuntimeError("Redis 未连接")

        full_key = self._make_key(key)
        ttl = ttl_seconds or self.config.default_ttl_seconds
        ttl = min(ttl, self.config.max_ttl_seconds)

        # 序列化
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value)

        await self._client.setex(full_key, ttl, serialized)
        self._stats.sets += 1

        # 写入 L1
        if self._l1_cache:
            await self._l1_cache.set(key, value, self.config.l1_ttl_seconds)

    async def delete(self, key: str) -> bool:
        """删除缓存。"""
        if self._client is None:
            return False

        full_key = self._make_key(key)
        result = await self._client.delete(full_key)

        if self._l1_cache:
            await self._l1_cache.delete(key)

        if result > 0:
            self._stats.deletes += 1
            return True
        return False

    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        if self._client is None:
            return False

        full_key = self._make_key(key)
        return await self._client.exists(full_key) > 0

    async def get_stats(self) -> CacheStats:
        """获取统计信息。"""
        if self._client:
            try:
                info = await self._client.info("stats")
                self._stats.size = info.get("keyspace_hits", 0)
            except Exception:
                pass
        return self._stats

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取。"""
        if self._client is None:
            return {}

        full_keys = [self._make_key(k) for k in keys]
        values = await self._client.mget(full_keys)

        results = {}
        for key, value in zip(keys, values, strict=False):
            if value is not None:
                try:
                    decoded = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    decoded = (
                        value.decode("utf-8") if isinstance(value, bytes) else value
                    )
                results[key] = decoded
                self._stats.hits += 1
            else:
                self._stats.misses += 1

        return results

    async def set_many(
        self,
        items: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """批量设置。"""
        if self._client is None:
            return

        ttl = ttl_seconds or self.config.default_ttl_seconds
        ttl = min(ttl, self.config.max_ttl_seconds)

        pipe = self._client.pipeline()
        for key, value in items.items():
            full_key = self._make_key(key)
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, ensure_ascii=False)
            else:
                serialized = str(value)
            pipe.setex(full_key, ttl, serialized)

        await pipe.execute()
        self._stats.sets += len(items)

    async def delete_many(self, keys: list[str]) -> int:
        """批量删除。"""
        if self._client is None:
            return 0

        full_keys = [self._make_key(k) for k in keys]
        result = await self._client.delete(*full_keys)

        if self._l1_cache:
            for key in keys:
                await self._l1_cache.delete(key)

        self._stats.deletes += result
        return result

    async def clear_prefix(self, prefix: str) -> int:
        """清除指定前缀的所有键。"""
        if self._client is None:
            return 0

        pattern = self._make_key(f"{prefix}*")
        count = 0

        async for key in self._client.scan_iter(match=pattern):
            await self._client.delete(key)
            count += 1

        return count

    # ==================== 高级功能 ====================

    async def get_or_set(
        self,
        key: str,
        factory: Any,
        ttl_seconds: int | None = None,
    ) -> Any:
        """获取或设置缓存。

        Args:
            key: 缓存键
            factory: 值工厂函数或值
            ttl_seconds: TTL

        Returns:
            缓存值
        """
        value = await self.get(key)
        if value is not None:
            return value

        # 计算值
        if callable(factory):
            import asyncio

            if asyncio.iscoroutinefunction(factory):
                value = await factory()
            else:
                value = factory()
        else:
            value = factory

        await self.set(key, value, ttl_seconds)
        return value

    async def incr(self, key: str, amount: int = 1) -> int:
        """原子递增。"""
        if self._client is None:
            raise RuntimeError("Redis 未连接")

        full_key = self._make_key(key)
        return await self._client.incrby(full_key, amount)

    async def decr(self, key: str, amount: int = 1) -> int:
        """原子递减。"""
        if self._client is None:
            raise RuntimeError("Redis 未连接")

        full_key = self._make_key(key)
        return await self._client.decrby(full_key, amount)

    async def set_hash(
        self,
        key: str,
        mapping: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """设置哈希。"""
        if self._client is None:
            raise RuntimeError("Redis 未连接")

        full_key = self._make_key(key)
        # 序列化值
        serialized = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            for k, v in mapping.items()
        }
        await self._client.hset(full_key, mapping=serialized)

        if ttl_seconds:
            await self._client.expire(full_key, ttl_seconds)

    async def get_hash(self, key: str) -> dict[str, Any]:
        """获取哈希。"""
        if self._client is None:
            return {}

        full_key = self._make_key(key)
        result = await self._client.hgetall(full_key)

        decoded = {}
        for k, v in result.items():
            key_str = k.decode("utf-8") if isinstance(k, bytes) else k
            val_str = v.decode("utf-8") if isinstance(v, bytes) else v
            try:
                decoded[key_str] = json.loads(val_str)
            except (json.JSONDecodeError, TypeError):
                decoded[key_str] = val_str

        return decoded


def make_cache_key(*parts: Any) -> str:
    """生成缓存键。

    Args:
        parts: 键的组成部分

    Returns:
        缓存键
    """
    key_str = ":".join(str(p) for p in parts)
    if len(key_str) > 200:
        # 过长的键使用哈希
        hash_val = hashlib.md5(key_str.encode()).hexdigest()[:16]
        return f"{str(parts[0])}:{hash_val}"
    return key_str
