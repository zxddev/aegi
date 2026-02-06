"""HTTP 请求重试机制模块。

实现指数退避重试策略：
- 可配置的最大重试次数
- 指数退避延迟
- 抖动（jitter）防止惊群效应
- 错误分类与可重试判断
- 审计记录生成
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorCategory(Enum):
    """错误分类。"""

    NETWORK = "network"  # 网络连接错误
    SERVER = "server"  # 服务端错误 (5xx)
    CLIENT = "client"  # 客户端错误 (4xx)
    RATE_LIMIT = "rate_limit"  # 速率限制 (429)
    TIMEOUT = "timeout"  # 超时
    UNKNOWN = "unknown"  # 未知错误


@dataclass(frozen=True)
class RetryConfig:
    """重试配置。"""

    max_retries: int = 3  # 最大重试次数
    initial_delay_ms: int = 1000  # 初始延迟（毫秒）
    max_delay_ms: int = 30000  # 最大延迟（毫秒）
    multiplier: float = 2.0  # 延迟倍数
    jitter_factor: float = 0.1  # 抖动因子 (0-1)
    # 可重试的错误类别
    retryable_categories: frozenset[ErrorCategory] = field(
        default_factory=lambda: frozenset(
            {
                ErrorCategory.NETWORK,
                ErrorCategory.SERVER,
                ErrorCategory.RATE_LIMIT,
                ErrorCategory.TIMEOUT,
            }
        )
    )
    # 可重试的 HTTP 状态码
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )


@dataclass
class RetryAttempt:
    """重试尝试记录。"""

    attempt_number: int
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    success: bool
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    status_code: int | None = None
    delay_before_ms: int = 0  # 此次尝试前的等待时间


@dataclass
class RetryResult:
    """重试结果。"""

    success: bool
    attempts: list[RetryAttempt]
    response: httpx.Response | None = None
    final_error: Exception | None = None
    total_duration_ms: int = 0

    @property
    def total_attempts(self) -> int:
        """总尝试次数。"""
        return len(self.attempts)

    @property
    def retries_count(self) -> int:
        """重试次数（不含首次）。"""
        return max(0, len(self.attempts) - 1)


def categorize_error(error: Exception) -> ErrorCategory:
    """将异常分类。"""
    if isinstance(error, httpx.TimeoutException):
        return ErrorCategory.TIMEOUT
    if isinstance(error, httpx.ConnectError):
        return ErrorCategory.NETWORK
    if isinstance(error, httpx.NetworkError):
        return ErrorCategory.NETWORK
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 429:
            return ErrorCategory.RATE_LIMIT
        if 500 <= status < 600:
            return ErrorCategory.SERVER
        if 400 <= status < 500:
            return ErrorCategory.CLIENT
    return ErrorCategory.UNKNOWN


def categorize_response(response: httpx.Response) -> ErrorCategory | None:
    """根据响应状态码分类。"""
    status = response.status_code
    if 200 <= status < 400:
        return None  # 成功，无错误
    if status == 429:
        return ErrorCategory.RATE_LIMIT
    if 500 <= status < 600:
        return ErrorCategory.SERVER
    if 400 <= status < 500:
        return ErrorCategory.CLIENT
    return ErrorCategory.UNKNOWN


def calculate_delay(
    attempt: int,
    config: RetryConfig,
    rate_limit_retry_after: int | None = None,
) -> int:
    """计算重试延迟（毫秒）。

    使用指数退避 + 抖动策略。
    如果服务端返回 Retry-After，优先使用。
    """
    # 如果有 Retry-After 头，优先使用
    if rate_limit_retry_after is not None and rate_limit_retry_after > 0:
        return min(rate_limit_retry_after * 1000, config.max_delay_ms)

    # 指数退避: initial * (multiplier ^ attempt)
    base_delay = config.initial_delay_ms * (config.multiplier**attempt)

    # 限制最大延迟
    base_delay = min(base_delay, config.max_delay_ms)

    # 添加抖动
    jitter_range = base_delay * config.jitter_factor
    jitter = random.uniform(-jitter_range, jitter_range)
    delay = base_delay + jitter

    # 确保延迟不为负
    return max(int(delay), 0)


def should_retry(
    category: ErrorCategory,
    attempt: int,
    config: RetryConfig,
) -> bool:
    """判断是否应该重试。"""
    # 检查是否超过最大重试次数
    if attempt >= config.max_retries:
        return False
    # 检查错误类别是否可重试
    return category in config.retryable_categories


def parse_retry_after(response: httpx.Response) -> int | None:
    """解析 Retry-After 头。"""
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        # 尝试解析为秒数
        return int(retry_after)
    except ValueError:
        # 可能是 HTTP-date 格式，暂不支持
        return None


async def retry_async(
    func: Callable[[], Any],
    config: RetryConfig,
    on_retry: Callable[[RetryAttempt], None] | None = None,
) -> RetryResult:
    """执行带重试的异步函数。

    Args:
        func: 要执行的异步函数
        config: 重试配置
        on_retry: 重试时的回调函数

    Returns:
        RetryResult 包含所有尝试的详细信息
    """
    attempts: list[RetryAttempt] = []
    total_start = time.time()
    response: httpx.Response | None = None
    final_error: Exception | None = None
    delay_before = 0

    for attempt_num in range(config.max_retries + 1):
        attempt_start = datetime.now(UTC)
        attempt_start_ts = time.time()

        try:
            # 执行请求
            result = await func()
            attempt_end = datetime.now(UTC)
            duration = int((time.time() - attempt_start_ts) * 1000)

            # 如果返回的是 Response 对象，检查状态码
            if isinstance(result, httpx.Response):
                response = result
                category = categorize_response(response)
                if category is not None:
                    # 有错误，记录并判断是否重试
                    attempt = RetryAttempt(
                        attempt_number=attempt_num + 1,
                        started_at=attempt_start,
                        ended_at=attempt_end,
                        duration_ms=duration,
                        success=False,
                        error_category=category,
                        error_message=f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        delay_before_ms=delay_before,
                    )
                    attempts.append(attempt)

                    if on_retry:
                        on_retry(attempt)

                    if should_retry(category, attempt_num, config):
                        retry_after = parse_retry_after(response)
                        delay_before = calculate_delay(attempt_num, config, retry_after)
                        logger.debug(
                            "重试 #%d，延迟 %d ms，错误: HTTP %d",
                            attempt_num + 1,
                            delay_before,
                            response.status_code,
                        )
                        await asyncio.sleep(delay_before / 1000.0)
                        continue
                    else:
                        # 不可重试
                        break

            # 成功
            attempt = RetryAttempt(
                attempt_number=attempt_num + 1,
                started_at=attempt_start,
                ended_at=attempt_end,
                duration_ms=duration,
                success=True,
                status_code=response.status_code if response else None,
                delay_before_ms=delay_before,
            )
            attempts.append(attempt)
            total_duration = int((time.time() - total_start) * 1000)
            return RetryResult(
                success=True,
                attempts=attempts,
                response=response,
                total_duration_ms=total_duration,
            )

        except Exception as e:
            attempt_end = datetime.now(UTC)
            duration = int((time.time() - attempt_start_ts) * 1000)
            category = categorize_error(e)
            final_error = e

            attempt = RetryAttempt(
                attempt_number=attempt_num + 1,
                started_at=attempt_start,
                ended_at=attempt_end,
                duration_ms=duration,
                success=False,
                error_category=category,
                error_message=str(e),
                delay_before_ms=delay_before,
            )
            attempts.append(attempt)

            if on_retry:
                on_retry(attempt)

            if should_retry(category, attempt_num, config):
                delay_before = calculate_delay(attempt_num, config)
                logger.debug(
                    "重试 #%d，延迟 %d ms，错误: %s",
                    attempt_num + 1,
                    delay_before,
                    e,
                )
                await asyncio.sleep(delay_before / 1000.0)
                continue
            else:
                # 不可重试
                break

    # 所有重试都失败
    total_duration = int((time.time() - total_start) * 1000)
    return RetryResult(
        success=False,
        attempts=attempts,
        response=response,
        final_error=final_error,
        total_duration_ms=total_duration,
    )


class RetryableHttpClient:
    """带重试功能的 HTTP 客户端封装。"""

    def __init__(
        self,
        config: RetryConfig,
        timeout: float = 30.0,
        proxy_url: str | None = None,
        verify: bool = True,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._proxy_url = proxy_url
        self._verify = verify

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        on_retry: Callable[[RetryAttempt], None] | None = None,
    ) -> RetryResult:
        """执行 GET 请求。"""

        async def do_request() -> httpx.Response:
            async with httpx.AsyncClient(
                proxy=self._proxy_url,
                timeout=self._timeout,
                verify=self._verify,
                trust_env=False,
            ) as client:
                response = await client.get(url, params=params, headers=headers)
                return response

        return await retry_async(do_request, self._config, on_retry)

    async def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        on_retry: Callable[[RetryAttempt], None] | None = None,
    ) -> RetryResult:
        """执行 POST 请求。"""

        async def do_request() -> httpx.Response:
            async with httpx.AsyncClient(
                proxy=self._proxy_url,
                timeout=self._timeout,
                verify=self._verify,
                trust_env=False,
            ) as client:
                response = await client.post(
                    url, json=json, data=data, files=files, headers=headers
                )
                return response

        return await retry_async(do_request, self._config, on_retry)


def create_audit_record(
    result: RetryResult,
    tool_name: str,
    url: str,
    method: str,
) -> dict[str, Any]:
    """创建重试审计记录。"""
    return {
        "tool_name": tool_name,
        "url": url,
        "method": method,
        "success": result.success,
        "total_attempts": result.total_attempts,
        "retries_count": result.retries_count,
        "total_duration_ms": result.total_duration_ms,
        "final_status_code": result.response.status_code if result.response else None,
        "final_error": str(result.final_error) if result.final_error else None,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "started_at": a.started_at.isoformat(),
                "ended_at": a.ended_at.isoformat(),
                "duration_ms": a.duration_ms,
                "success": a.success,
                "error_category": a.error_category.value if a.error_category else None,
                "error_message": a.error_message,
                "status_code": a.status_code,
                "delay_before_ms": a.delay_before_ms,
            }
            for a in result.attempts
        ],
    }
