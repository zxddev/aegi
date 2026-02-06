"""代理池管理模块。

实现代理池的核心功能：
- 多种选择策略（轮询、基于延迟、随机）
- 健康检查与故障切换
- 代理状态追踪与统计
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class ProxyProtocol(Enum):
    """代理协议类型。"""

    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


@dataclass
class ProxyConfig:
    """代理配置。"""

    host: str
    port: int
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    username: str | None = None
    password: str | None = None
    # 可选的域名白名单/黑名单
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()

    def to_url(self) -> str:
        """生成代理 URL。"""
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        return f"{self.protocol.value}://{auth}{self.host}:{self.port}"

    def matches_domain(self, domain: str | None) -> bool:
        """检查域名是否匹配此代理的规则。"""
        if domain is None:
            return True
        domain_lower = domain.lower()
        # 黑名单优先
        if self.denied_domains:
            for denied in self.denied_domains:
                if domain_lower.endswith(denied.lower()):
                    return False
        # 白名单检查
        if self.allowed_domains:
            for allowed in self.allowed_domains:
                if domain_lower.endswith(allowed.lower()):
                    return True
            return False
        return True


@dataclass
class ProxyHealth:
    """代理健康状态。"""

    is_healthy: bool = True
    consecutive_failures: int = 0
    last_check_time: float = 0.0
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    last_latency_ms: float = 0.0
    last_error: str | None = None

    @property
    def average_latency_ms(self) -> float:
        """计算平均延迟。"""
        if self.successful_requests == 0:
            return float("inf")
        return self.total_latency_ms / self.successful_requests

    @property
    def success_rate(self) -> float:
        """计算成功率。"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


@dataclass
class ProxyPoolConfig:
    """代理池配置。"""

    # 健康检查配置
    health_check_interval_seconds: int = 60
    health_check_timeout_seconds: int = 10
    health_check_url: str = "https://www.google.com"
    # 故障切换配置
    unhealthy_threshold: int = 3  # 连续失败次数阈值
    recovery_interval_seconds: int = 300  # 恢复检查间隔
    # 选择策略
    selector_type: str = "round_robin"  # round_robin, latency, random


class ProxySelector(ABC):
    """代理选择器基类。"""

    @abstractmethod
    def select(
        self,
        proxies: list[tuple[ProxyConfig, ProxyHealth]],
        domain: str | None = None,
    ) -> ProxyConfig | None:
        """选择一个代理。"""


class RoundRobinSelector(ProxySelector):
    """轮询选择器。"""

    def __init__(self) -> None:
        self._index = 0
        self._lock = asyncio.Lock()

    def select(
        self,
        proxies: list[tuple[ProxyConfig, ProxyHealth]],
        domain: str | None = None,
    ) -> ProxyConfig | None:
        """轮询选择健康的代理。"""
        # 过滤健康且匹配域名的代理
        healthy = [
            (p, h) for p, h in proxies if h.is_healthy and p.matches_domain(domain)
        ]
        if not healthy:
            return None
        # 轮询
        idx = self._index % len(healthy)
        self._index = (self._index + 1) % len(healthy)
        return healthy[idx][0]


class LatencyBasedSelector(ProxySelector):
    """基于延迟的选择器。"""

    def select(
        self,
        proxies: list[tuple[ProxyConfig, ProxyHealth]],
        domain: str | None = None,
    ) -> ProxyConfig | None:
        """选择延迟最低的健康代理。"""
        healthy = [
            (p, h) for p, h in proxies if h.is_healthy and p.matches_domain(domain)
        ]
        if not healthy:
            return None
        # 按平均延迟排序
        healthy.sort(key=lambda x: x[1].average_latency_ms)
        return healthy[0][0]


class RandomSelector(ProxySelector):
    """随机选择器。"""

    def select(
        self,
        proxies: list[tuple[ProxyConfig, ProxyHealth]],
        domain: str | None = None,
    ) -> ProxyConfig | None:
        """随机选择健康的代理。"""
        healthy = [
            (p, h) for p, h in proxies if h.is_healthy and p.matches_domain(domain)
        ]
        if not healthy:
            return None
        return random.choice(healthy)[0]


def parse_proxy_list(proxy_list: str) -> list[ProxyConfig]:
    """解析代理列表字符串。

    格式：逗号分隔的代理 URL，支持：
    - http://host:port
    - https://host:port
    - socks5://host:port
    - http://user:pass@host:port
    """
    proxies: list[ProxyConfig] = []
    for item in proxy_list.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parsed = urlparse(item)
            if not parsed.hostname or not parsed.port:
                logger.warning("无效的代理 URL: %s", item)
                continue
            protocol_map = {
                "http": ProxyProtocol.HTTP,
                "https": ProxyProtocol.HTTPS,
                "socks5": ProxyProtocol.SOCKS5,
            }
            protocol = protocol_map.get(parsed.scheme, ProxyProtocol.HTTP)
            proxies.append(
                ProxyConfig(
                    host=parsed.hostname,
                    port=parsed.port,
                    protocol=protocol,
                    username=parsed.username,
                    password=parsed.password,
                )
            )
        except Exception as e:
            logger.warning("解析代理 URL 失败: %s, 错误: %s", item, e)
    return proxies


@dataclass
class ProxyPool:
    """代理池管理器。"""

    config: ProxyPoolConfig
    _proxies: dict[str, tuple[ProxyConfig, ProxyHealth]] = field(
        default_factory=dict, init=False
    )
    _selector: ProxySelector = field(init=False)
    _health_check_task: asyncio.Task[None] | None = field(default=None, init=False)
    _running: bool = field(default=False, init=False)
    _on_proxy_status_change: Callable[[ProxyConfig, bool], None] | None = field(
        default=None, init=False
    )

    def __post_init__(self) -> None:
        """初始化选择器。"""
        selector_map: dict[str, type[ProxySelector]] = {
            "round_robin": RoundRobinSelector,
            "latency": LatencyBasedSelector,
            "random": RandomSelector,
        }
        selector_cls = selector_map.get(self.config.selector_type, RoundRobinSelector)
        self._selector = selector_cls()

    def add_proxy(self, proxy: ProxyConfig) -> None:
        """添加代理。"""
        key = proxy.to_url()
        if key in self._proxies:
            logger.debug("代理已存在: %s", key)
            return
        self._proxies[key] = (proxy, ProxyHealth())
        logger.info("添加代理: %s", key)

    def remove_proxy(self, proxy: ProxyConfig) -> None:
        """移除代理。"""
        key = proxy.to_url()
        if key in self._proxies:
            del self._proxies[key]
            logger.info("移除代理: %s", key)

    @property
    def proxy_count(self) -> int:
        """代理总数。"""
        return len(self._proxies)

    @property
    def healthy_proxy_count(self) -> int:
        """健康代理数。"""
        return sum(1 for _, h in self._proxies.values() if h.is_healthy)

    @property
    def has_healthy_proxy(self) -> bool:
        """是否有健康代理。"""
        return self.healthy_proxy_count > 0

    def get_proxy(self, domain: str | None = None) -> ProxyConfig | None:
        """获取一个代理。"""
        if not self._proxies:
            return None
        proxies = list(self._proxies.values())
        return self._selector.select(proxies, domain)

    async def report_success(self, proxy: ProxyConfig, latency_ms: float) -> None:
        """报告请求成功。"""
        key = proxy.to_url()
        if key not in self._proxies:
            return
        _, health = self._proxies[key]
        health.is_healthy = True
        health.consecutive_failures = 0
        health.last_success_time = time.time()
        health.total_requests += 1
        health.successful_requests += 1
        health.total_latency_ms += latency_ms
        health.last_latency_ms = latency_ms
        health.last_error = None

    async def report_failure(self, proxy: ProxyConfig, error: str = "") -> None:
        """报告请求失败。"""
        key = proxy.to_url()
        if key not in self._proxies:
            return
        _, health = self._proxies[key]
        health.consecutive_failures += 1
        health.last_failure_time = time.time()
        health.total_requests += 1
        health.failed_requests += 1
        health.last_error = error
        # 检查是否达到不健康阈值
        if health.consecutive_failures >= self.config.unhealthy_threshold:
            if health.is_healthy:
                health.is_healthy = False
                logger.warning(
                    "代理标记为不健康: %s (连续失败 %d 次)",
                    key,
                    health.consecutive_failures,
                )
                if self._on_proxy_status_change:
                    self._on_proxy_status_change(proxy, False)

    def set_status_change_callback(
        self, callback: Callable[[ProxyConfig, bool], None]
    ) -> None:
        """设置代理状态变化回调。"""
        self._on_proxy_status_change = callback

    async def start_health_check(self) -> None:
        """启动健康检查任务。"""
        if self._running:
            return
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("代理池健康检查已启动")

    async def stop_health_check(self) -> None:
        """停止健康检查任务。"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        logger.info("代理池健康检查已停止")

    async def _health_check_loop(self) -> None:
        """健康检查循环。"""
        while self._running:
            try:
                await self._run_health_checks()
            except Exception as e:
                logger.error("健康检查异常: %s", e)
            await asyncio.sleep(self.config.health_check_interval_seconds)

    async def _run_health_checks(self) -> None:
        """执行所有代理的健康检查。"""
        now = time.time()
        tasks: list[asyncio.Task[None]] = []
        for _key, (proxy, health) in self._proxies.items():
            # 健康代理正常检查
            # 不健康代理在恢复间隔后重试
            should_check = health.is_healthy or (
                now - health.last_check_time >= self.config.recovery_interval_seconds
            )
            if should_check:
                tasks.append(asyncio.create_task(self._check_proxy(proxy, health)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_proxy(self, proxy: ProxyConfig, health: ProxyHealth) -> None:
        """检查单个代理健康状态。"""
        health.last_check_time = time.time()
        start_time = time.time()
        try:
            async with httpx.AsyncClient(
                proxy=proxy.to_url(),
                timeout=self.config.health_check_timeout_seconds,
                verify=False,  # 健康检查不验证 SSL
            ) as client:
                response = await client.get(self.config.health_check_url)
                response.raise_for_status()
            latency_ms = (time.time() - start_time) * 1000
            was_unhealthy = not health.is_healthy
            health.is_healthy = True
            health.consecutive_failures = 0
            health.last_success_time = time.time()
            health.last_latency_ms = latency_ms
            health.last_error = None
            if was_unhealthy:
                logger.info("代理恢复健康: %s", proxy.to_url())
                if self._on_proxy_status_change:
                    self._on_proxy_status_change(proxy, True)
        except Exception as e:
            health.consecutive_failures += 1
            health.last_failure_time = time.time()
            health.last_error = str(e)
            if (
                health.is_healthy
                and health.consecutive_failures >= self.config.unhealthy_threshold
            ):
                health.is_healthy = False
                logger.warning(
                    "代理健康检查失败，标记为不健康: %s, 错误: %s", proxy.to_url(), e
                )
                if self._on_proxy_status_change:
                    self._on_proxy_status_change(proxy, False)

    def get_statistics(self) -> dict[str, object]:
        """获取代理池统计信息。"""
        stats: dict[str, object] = {
            "total_proxies": self.proxy_count,
            "healthy_proxies": self.healthy_proxy_count,
            "unhealthy_proxies": self.proxy_count - self.healthy_proxy_count,
            "proxies": [],
        }
        proxy_stats: list[dict[str, object]] = []
        for key, (_proxy, health) in self._proxies.items():
            proxy_stats.append(
                {
                    "url": key,
                    "is_healthy": health.is_healthy,
                    "consecutive_failures": health.consecutive_failures,
                    "total_requests": health.total_requests,
                    "successful_requests": health.successful_requests,
                    "failed_requests": health.failed_requests,
                    "average_latency_ms": health.average_latency_ms
                    if health.successful_requests > 0
                    else None,
                    "last_latency_ms": health.last_latency_ms,
                    "success_rate": health.success_rate,
                    "last_error": health.last_error,
                }
            )
        stats["proxies"] = proxy_stats
        return stats
