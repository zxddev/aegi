"""API 请求限流模块。

基于滑动窗口算法实现，支持按 API Key / IP / 用户维度限流。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LimitDimension(Enum):
    """限流维度。"""

    API_KEY = "api_key"
    IP = "ip"
    USER = "user"
    GLOBAL = "global"


@dataclass
class RateLimitConfig:
    """限流配置。"""

    # 每秒请求数限制
    requests_per_second: float
    # 突发请求数（令牌桶容量）
    burst_size: int
    # 限流维度
    dimension: LimitDimension = LimitDimension.API_KEY
    # 窗口大小（秒）
    window_size_seconds: float = 1.0

    def __post_init__(self) -> None:
        """校验配置。"""
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second 必须大于 0")
        if self.burst_size <= 0:
            raise ValueError("burst_size 必须大于 0")
        if self.window_size_seconds <= 0:
            raise ValueError("window_size_seconds 必须大于 0")


@dataclass
class RateLimitResult:
    """限流结果。"""

    allowed: bool
    remaining: int
    reset_after_seconds: float
    retry_after_seconds: float | None = None

    def to_headers(self) -> dict[str, str]:
        """生成响应头。"""
        headers = {
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_after_seconds)),
        }
        if self.retry_after_seconds is not None:
            headers["Retry-After"] = str(int(self.retry_after_seconds) + 1)
        return headers


@dataclass
class _TokenBucket:
    """令牌桶实现。"""

    capacity: int
    refill_rate: float  # 每秒补充的令牌数
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        """初始化令牌数为满。"""
        self.tokens = float(self.capacity)

    def _refill(self) -> None:
        """补充令牌。"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

    def try_consume(self, count: int = 1) -> tuple[bool, float, float]:
        """尝试消费令牌。

        Args:
            count: 消费数量

        Returns:
            (是否成功, 剩余令牌数, 下次可用时间)
        """
        self._refill()
        if self.tokens >= count:
            self.tokens -= count
            return True, self.tokens, 0.0
        # 计算需要等待的时间
        needed = count - self.tokens
        wait_seconds = needed / self.refill_rate
        return False, self.tokens, wait_seconds


@dataclass
class _SlidingWindowCounter:
    """滑动窗口计数器实现。"""

    window_size_seconds: float
    max_requests: int
    # 时间戳列表（单调递增）
    timestamps: list[float] = field(default_factory=list)

    def _cleanup(self, now: float) -> None:
        """清理过期时间戳。"""
        cutoff = now - self.window_size_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.pop(0)

    def try_acquire(self) -> tuple[bool, int, float]:
        """尝试获取请求配额。

        Returns:
            (是否成功, 剩余配额, 重置时间)
        """
        now = time.monotonic()
        self._cleanup(now)

        remaining = self.max_requests - len(self.timestamps)

        if remaining > 0:
            self.timestamps.append(now)
            return True, remaining - 1, self.window_size_seconds

        # 计算下次可用时间
        if self.timestamps:
            oldest = self.timestamps[0]
            reset_after = (oldest + self.window_size_seconds) - now
            return False, 0, max(0.0, reset_after)

        return False, 0, self.window_size_seconds


class RateLimiter:
    """API 请求限流器。

    支持按 API Key / IP / 用户维度限流，使用令牌桶算法。
    """

    def __init__(self, config: RateLimitConfig) -> None:
        """初始化限流器。

        Args:
            config: 限流配置
        """
        self._config = config
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()
        # 清理间隔（秒）
        self._cleanup_interval = 300.0
        self._last_cleanup = time.monotonic()

    def _get_bucket_key(
        self,
        api_key: str | None = None,
        ip: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """生成桶键。"""
        dimension = self._config.dimension
        if dimension == LimitDimension.API_KEY:
            return f"api_key:{api_key or 'anonymous'}"
        if dimension == LimitDimension.IP:
            return f"ip:{ip or 'unknown'}"
        if dimension == LimitDimension.USER:
            return f"user:{user_id or 'anonymous'}"
        return "global"

    def _get_or_create_bucket(self, key: str) -> _TokenBucket:
        """获取或创建令牌桶。"""
        if key not in self._buckets:
            self._buckets[key] = _TokenBucket(
                capacity=self._config.burst_size,
                refill_rate=self._config.requests_per_second,
            )
        return self._buckets[key]

    def _maybe_cleanup(self) -> None:
        """定期清理过期桶。"""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        # 清理一段时间没有活动的桶
        inactive_threshold = 600.0  # 10 分钟
        keys_to_remove = []
        for key, bucket in self._buckets.items():
            if now - bucket.last_refill > inactive_threshold:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._buckets[key]
        if keys_to_remove:
            logger.debug("清理了 %d 个不活跃的限流桶", len(keys_to_remove))

    async def check(
        self,
        api_key: str | None = None,
        ip: str | None = None,
        user_id: str | None = None,
    ) -> RateLimitResult:
        """检查请求是否被限流。

        Args:
            api_key: API Key
            ip: 客户端 IP
            user_id: 用户 ID

        Returns:
            限流结果
        """
        async with self._lock:
            self._maybe_cleanup()
            key = self._get_bucket_key(api_key, ip, user_id)
            bucket = self._get_or_create_bucket(key)
            allowed, remaining, wait_seconds = bucket.try_consume(1)

            if allowed:
                return RateLimitResult(
                    allowed=True,
                    remaining=int(remaining),
                    reset_after_seconds=1.0 / self._config.requests_per_second,
                )
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_after_seconds=wait_seconds,
                retry_after_seconds=wait_seconds,
            )

    def get_stats(self) -> dict[str, object]:
        """获取限流统计信息。"""
        return {
            "dimension": self._config.dimension.value,
            "requests_per_second": self._config.requests_per_second,
            "burst_size": self._config.burst_size,
            "active_buckets": len(self._buckets),
        }


class MultiDimensionRateLimiter:
    """多维度限流器。

    支持同时按多个维度限流（如全局 + API Key）。
    """

    def __init__(self, configs: list[RateLimitConfig]) -> None:
        """初始化多维度限流器。

        Args:
            configs: 限流配置列表
        """
        self._limiters = [RateLimiter(config) for config in configs]

    async def check(
        self,
        api_key: str | None = None,
        ip: str | None = None,
        user_id: str | None = None,
    ) -> RateLimitResult:
        """检查请求是否被任意维度限流。

        Args:
            api_key: API Key
            ip: 客户端 IP
            user_id: 用户 ID

        Returns:
            限流结果（任意维度被限流则返回被限流）
        """
        results = await asyncio.gather(
            *[limiter.check(api_key, ip, user_id) for limiter in self._limiters]
        )
        # 返回最严格的限制
        for result in results:
            if not result.allowed:
                return result
        # 所有维度都允许，返回剩余最少的
        min_remaining = min(r.remaining for r in results)
        max_reset = max(r.reset_after_seconds for r in results)
        return RateLimitResult(
            allowed=True,
            remaining=min_remaining,
            reset_after_seconds=max_reset,
        )

    def get_stats(self) -> dict[str, object]:
        """获取所有限流器统计信息。"""
        return {
            "limiters": [limiter.get_stats() for limiter in self._limiters],
        }
