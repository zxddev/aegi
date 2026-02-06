"""外联治理。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from baize_mcp_gateway.db import ScrapeGuardSnapshot


@dataclass
class CachedResponse:
    """缓存响应。"""

    payload: dict[str, object]
    expires_at: float


@dataclass
class CachedTosResult:
    """缓存的 ToS 检查结果。"""

    result: TosCheckResult
    expires_at: float


@dataclass
class DomainLimiter:
    """按域名限流。"""

    rps: float
    concurrency: int
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    semaphore: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.rps
        self.last_refill = time.monotonic()
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(self.rps, self.tokens + elapsed * self.rps)
        self.last_refill = now

    def try_acquire_token(self) -> bool:
        """尝试消耗令牌。"""

        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


@dataclass
class TosCheckResult:
    """ToS 检查结果。"""

    tos_url: str | None
    tos_found: bool
    scraping_allowed: bool | None  # None 表示无法判断
    tos_summary: str | None
    error: str | None = None


class ScrapeGuard:
    """外联治理执行器。"""

    # 常见的 ToS 页面路径
    TOS_PATHS = [
        "/terms",
        "/terms-of-service",
        "/tos",
        "/legal/terms",
        "/terms-and-conditions",
        "/legal",
    ]

    # 禁止抓取的关键词
    SCRAPING_DENY_KEYWORDS = [
        "scraping is prohibited",
        "scraping is not allowed",
        "automated access is prohibited",
        "automated access is not allowed",
        "crawling is prohibited",
        "crawling is not allowed",
        "bots are not allowed",
        "no scraping",
        "no crawling",
        "禁止抓取",
        "禁止爬虫",
    ]

    def __init__(
        self,
        *,
        allowed_domains: tuple[str, ...],
        denied_domains: tuple[str, ...],
        domain_rps: float,
        domain_concurrency: int,
        cache_ttl_seconds: int,
        robots_require_allow: bool,
        tos_check_enabled: bool = True,  # 默认启用
        tos_require_allow: bool = False,
        tos_cache_ttl_seconds: int = 86400,  # ToS 缓存过期时间，默认 24 小时
    ) -> None:
        self._allowed_domains = allowed_domains
        self._denied_domains = denied_domains
        self._domain_rps = domain_rps
        self._domain_concurrency = domain_concurrency
        self._cache_ttl_seconds = cache_ttl_seconds
        self._robots_require_allow = robots_require_allow
        self._tos_check_enabled = tos_check_enabled
        self._tos_require_allow = tos_require_allow
        self._tos_cache_ttl_seconds = tos_cache_ttl_seconds
        self._limiters: dict[str, DomainLimiter] = {}
        self._cache: dict[str, CachedResponse] = {}
        self._url_cache: dict[str, CachedResponse] = {}
        self._robots_cache: dict[str, bool] = {}
        self._robots_cache_expires: dict[str, float] = {}  # robots 缓存过期时间
        self._tos_cache: dict[str, CachedTosResult] = {}
        self._logger = logging.getLogger("baize_mcp_gateway.scrape_guard")
        self._policy_lock = asyncio.Lock()
        self._last_loaded = 0.0
        self._refresh_seconds = 0
        self._source: Callable[[], Awaitable[ScrapeGuardSnapshot]] | None = None
        self._robots_audit: (
            Callable[[str, str, str, str, bool, str | None, datetime], Awaitable[None]]
            | None
        ) = None
        self._tos_audit: (
            Callable[
                [
                    str,
                    str,
                    str,
                    str | None,
                    bool,
                    bool | None,
                    str | None,
                    str | None,
                    datetime,
                ],
                Awaitable[None],
            ]
            | None
        ) = None

    def _match_domain(self, host: str, entry: str) -> bool:
        if host == entry:
            return True
        return host.endswith(f".{entry}")

    def _is_allowed(self, host: str) -> bool:
        if not self._allowed_domains:
            return False
        # 支持 * 通配符表示允许所有域名
        if "*" in self._allowed_domains:
            allowed = True
        else:
            allowed = any(
                self._match_domain(host, entry) for entry in self._allowed_domains
            )
        if not allowed:
            return False
        if self._denied_domains:
            denied = any(
                self._match_domain(host, entry) for entry in self._denied_domains
            )
            if denied:
                return False
        return True

    def _get_limiter(self, host: str) -> DomainLimiter:
        limiter = self._limiters.get(host)
        if limiter is None:
            limiter = DomainLimiter(
                rps=self._domain_rps,
                concurrency=self._domain_concurrency,
            )
            self._limiters[host] = limiter
        return limiter

    def attach_source(
        self,
        *,
        source: Callable[[], Awaitable[ScrapeGuardSnapshot]],
        refresh_seconds: int,
    ) -> None:
        """绑定数据源。"""

        self._source = source
        self._refresh_seconds = refresh_seconds

    def attach_robots_audit(
        self,
        *,
        recorder: Callable[
            [str, str, str, str, bool, str | None, datetime], Awaitable[None]
        ],
    ) -> None:
        """绑定 robots 审计回调。"""

        self._robots_audit = recorder

    def attach_tos_audit(
        self,
        *,
        recorder: Callable[
            [
                str,
                str,
                str,
                str | None,
                bool,
                bool | None,
                str | None,
                str | None,
                datetime,
            ],
            Awaitable[None],
        ],
    ) -> None:
        """绑定 ToS 审计回调。

        回调签名：(tool_name, url, host, tos_url, tos_found, scraping_allowed, tos_summary, error_message, checked_at)
        """
        self._tos_audit = recorder

    async def refresh_if_needed(self) -> None:
        """刷新治理配置。"""

        if self._source is None:
            return
        now = time.monotonic()
        if self._last_loaded and now - self._last_loaded < self._refresh_seconds:
            return
        async with self._policy_lock:
            now = time.monotonic()
            if self._last_loaded and now - self._last_loaded < self._refresh_seconds:
                return
            snapshot = await self._source()
            if not snapshot.allowed_domains:
                raise RuntimeError("Scrape Guard 允许域名列表为空")
            self._allowed_domains = snapshot.allowed_domains
            self._denied_domains = snapshot.denied_domains
            self._domain_rps = snapshot.settings.domain_rps
            self._domain_concurrency = snapshot.settings.domain_concurrency
            self._cache_ttl_seconds = snapshot.settings.cache_ttl_seconds
            self._robots_require_allow = snapshot.settings.robots_require_allow
            self._limiters.clear()
            self._last_loaded = time.monotonic()

    def _cache_key(self, tool_name: str, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return f"{tool_name}:{raw}"

    def _url_cache_key(self, tool_name: str, url: str) -> str:
        return f"{tool_name}:{url}"

    def cache_get(
        self, *, tool_name: str, payload: dict[str, object]
    ) -> dict[str, object] | None:
        """读取缓存。"""

        key = self._cache_key(tool_name, payload)
        item = self._cache.get(key)
        if item is None:
            return None
        if time.monotonic() >= item.expires_at:
            self._cache.pop(key, None)
            return None
        return item.payload

    def cache_set(
        self, *, tool_name: str, payload: dict[str, object], response: dict[str, object]
    ) -> None:
        """写入缓存。"""

        key = self._cache_key(tool_name, payload)
        expires_at = time.monotonic() + self._cache_ttl_seconds
        self._cache[key] = CachedResponse(payload=response, expires_at=expires_at)

    def cache_get_url(self, *, tool_name: str, url: str) -> dict[str, object] | None:
        """按 URL 读取缓存。"""

        key = self._url_cache_key(tool_name, url)
        item = self._url_cache.get(key)
        if item is None:
            return None
        if time.monotonic() >= item.expires_at:
            self._url_cache.pop(key, None)
            return None
        return item.payload

    def cache_set_url(
        self, *, tool_name: str, url: str, response: dict[str, object]
    ) -> None:
        """按 URL 写入缓存。"""

        key = self._url_cache_key(tool_name, url)
        expires_at = time.monotonic() + self._cache_ttl_seconds
        self._url_cache[key] = CachedResponse(payload=response, expires_at=expires_at)

    async def enforce(self, *, url: str, tool_name: str) -> asyncio.Semaphore:
        """执行外联治理。"""

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("仅支持 http/https URL")
        host = parsed.hostname
        if not host:
            raise ValueError("URL 缺少 hostname")
        host = host.lower()
        if not self._is_allowed(host):
            raise PermissionError("域名未在允许列表内")

        limiter = self._get_limiter(host)
        if not limiter.try_acquire_token():
            raise RuntimeError("触发域名速率限制")

        await limiter.semaphore.acquire()
        try:
            await self._check_robots(url, host, tool_name)
            # ToS 检查
            if self._tos_check_enabled:
                await self._check_tos(url, host, tool_name)
        except Exception:
            limiter.semaphore.release()
            raise
        return limiter.semaphore

    async def _check_robots(self, url: str, host: str, tool_name: str) -> None:
        cached = self._robots_cache.get(host)
        if cached is not None:
            if self._robots_require_allow and not cached:
                raise PermissionError("robots.txt 拒绝访问")
            return

        robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
        checked_at = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(trust_env=True) as client:
                response = await client.get(robots_url, timeout=10.0)
            
            # robots.txt 不存在（404）或其他客户端错误时，默认允许（除非配置要求必须存在）
            if response.status_code >= 400:
                # 缓存为 True（允许），因为没有 robots.txt 意味着没有限制
                allowed = True
                self._robots_cache[host] = allowed
                if self._robots_audit is not None:
                    await self._robots_audit(
                        tool_name,
                        url,
                        host,
                        robots_url,
                        allowed,
                        f"robots.txt 返回 {response.status_code}，默认允许",
                        checked_at,
                    )
                self._logger.info(
                    "robots_check",
                    extra={
                        "tool": tool_name,
                        "host": host,
                        "allowed": allowed,
                        "status_code": response.status_code,
                        "checked_at": checked_at.isoformat(),
                    },
                )
                return
            
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch("*", url)
            self._robots_cache[host] = allowed
            if self._robots_audit is not None:
                await self._robots_audit(
                    tool_name,
                    url,
                    host,
                    robots_url,
                    allowed,
                    None,
                    checked_at,
                )
            self._logger.info(
                "robots_check",
                extra={
                    "tool": tool_name,
                    "host": host,
                    "allowed": allowed,
                    "checked_at": checked_at.isoformat(),
                },
            )
            if self._robots_require_allow and not allowed:
                raise PermissionError("robots.txt 拒绝访问")
        except PermissionError:
            raise
        except Exception as exc:
            # 网络错误等情况，如果不要求 robots.txt 必须允许，则默认放行
            if not self._robots_require_allow:
                self._robots_cache[host] = True  # 缓存为允许
                if self._robots_audit is not None:
                    await self._robots_audit(
                        tool_name,
                        url,
                        host,
                        robots_url,
                        True,
                        f"robots.txt 获取失败（{exc}），默认允许",
                        checked_at,
                    )
                self._logger.warning(
                    "robots_check_failed_allow",
                    extra={
                        "tool": tool_name,
                        "host": host,
                        "error": str(exc),
                        "checked_at": checked_at.isoformat(),
                    },
                )
                return
            # 如果要求必须允许，则抛出异常
            if self._robots_audit is not None:
                await self._robots_audit(
                    tool_name,
                    url,
                    host,
                    robots_url,
                    False,
                    str(exc),
                    checked_at,
                )
            raise

    async def _check_tos(self, url: str, host: str, tool_name: str) -> None:
        """检查服务条款（ToS）。"""
        # 检查缓存（带过期时间）
        cached = self._tos_cache.get(host)
        now = time.monotonic()
        if cached is not None:
            if now < cached.expires_at:
                # 缓存有效
                if self._tos_require_allow and cached.result.scraping_allowed is False:
                    raise PermissionError(
                        f"ToS 禁止抓取: {cached.result.tos_summary}",
                    )
                return
            # 缓存已过期，清理
            del self._tos_cache[host]

        checked_at = datetime.now(UTC)
        result = await self._fetch_and_analyze_tos(url, host)

        # 缓存结果（带过期时间）
        expires_at = now + self._tos_cache_ttl_seconds
        self._tos_cache[host] = CachedTosResult(result=result, expires_at=expires_at)

        # 记录审计
        if self._tos_audit is not None:
            await self._tos_audit(
                tool_name,
                url,
                host,
                result.tos_url,
                result.tos_found,
                result.scraping_allowed,
                result.tos_summary,
                result.error,
                checked_at,
            )

        self._logger.info(
            "tos_check",
            extra={
                "tool": tool_name,
                "host": host,
                "tos_found": result.tos_found,
                "scraping_allowed": result.scraping_allowed,
                "checked_at": checked_at.isoformat(),
            },
        )

        # 如果要求 ToS 允许且检测到禁止
        if self._tos_require_allow and result.scraping_allowed is False:
            raise PermissionError(
                f"ToS 禁止抓取: {result.tos_summary}. "
                f"如需继续访问，请联系站点管理员或配置例外规则。"
            )

    async def _fetch_and_analyze_tos(self, url: str, host: str) -> TosCheckResult:
        """获取并分析 ToS 页面。"""
        scheme = urlparse(url).scheme

        # 尝试常见的 ToS 路径
        for path in self.TOS_PATHS:
            tos_url = f"{scheme}://{host}{path}"
            try:
                async with httpx.AsyncClient(trust_env=True) as client:
                    response = await client.get(
                        tos_url, timeout=10.0, follow_redirects=True
                    )
                if response.status_code == 200:
                    content = response.text.lower()
                    # 检查是否包含禁止抓取的关键词
                    scraping_allowed = True
                    deny_reason = None
                    for keyword in self.SCRAPING_DENY_KEYWORDS:
                        if keyword.lower() in content:
                            scraping_allowed = False
                            deny_reason = keyword
                            break

                    # 生成摘要
                    if scraping_allowed:
                        summary = "ToS 未发现明确禁止抓取的条款"
                    else:
                        summary = f"ToS 包含禁止抓取的条款: {deny_reason}"

                    return TosCheckResult(
                        tos_url=tos_url,
                        tos_found=True,
                        scraping_allowed=scraping_allowed,
                        tos_summary=summary,
                    )
            except Exception:
                continue

        # 未找到 ToS 页面
        return TosCheckResult(
            tos_url=None,
            tos_found=False,
            scraping_allowed=None,  # 无法判断
            tos_summary="未找到 ToS 页面",
        )

    async def get_tos_status(self, host: str) -> TosCheckResult | None:
        """获取域名的 ToS 状态（用于查询）。"""
        cached = self._tos_cache.get(host)
        if cached is None:
            return None
        # 检查是否过期
        if time.monotonic() >= cached.expires_at:
            del self._tos_cache[host]
            return None
        return cached.result

    def clear_tos_cache(self, host: str | None = None) -> int:
        """清理 ToS 缓存。

        Args:
            host: 指定域名，None 表示清理所有

        Returns:
            清理的条目数
        """
        if host is not None:
            if host in self._tos_cache:
                del self._tos_cache[host]
                return 1
            return 0
        count = len(self._tos_cache)
        self._tos_cache.clear()
        return count

    def get_cache_stats(self) -> dict[str, object]:
        """获取缓存统计信息。"""
        now = time.monotonic()
        # 统计有效/过期的缓存条目
        valid_response_cache = sum(
            1 for item in self._cache.values() if now < item.expires_at
        )
        valid_url_cache = sum(
            1 for item in self._url_cache.values() if now < item.expires_at
        )
        valid_tos_cache = sum(
            1 for item in self._tos_cache.values() if now < item.expires_at
        )
        return {
            "response_cache": {
                "total": len(self._cache),
                "valid": valid_response_cache,
            },
            "url_cache": {
                "total": len(self._url_cache),
                "valid": valid_url_cache,
            },
            "robots_cache": {
                "total": len(self._robots_cache),
            },
            "tos_cache": {
                "total": len(self._tos_cache),
                "valid": valid_tos_cache,
                "ttl_seconds": self._tos_cache_ttl_seconds,
            },
            "tos_check_enabled": self._tos_check_enabled,
            "tos_require_allow": self._tos_require_allow,
        }
