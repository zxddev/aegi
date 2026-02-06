"""重试机制测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from baize_mcp_gateway.retry import (
    ErrorCategory,
    RetryAttempt,
    RetryConfig,
    RetryResult,
    calculate_delay,
    categorize_error,
    categorize_response,
    create_audit_record,
    parse_retry_after,
    retry_async,
    should_retry,
)


def _make_response(
    status_code: int, *, headers: dict[str, str] | None = None
) -> httpx.Response:
    request = httpx.Request("GET", "http://example.com")
    return httpx.Response(
        status_code=status_code,
        headers=headers or {},
        request=request,
    )


class TestCategorizeError:
    """categorize_error 测试。"""

    def test_timeout_error(self) -> None:
        """测试超时错误分类。"""
        error = httpx.TimeoutException("Timeout")
        assert categorize_error(error) == ErrorCategory.TIMEOUT

    def test_connect_error(self) -> None:
        """测试连接错误分类。"""
        error = httpx.ConnectError("Connection refused")
        assert categorize_error(error) == ErrorCategory.NETWORK

    def test_network_error(self) -> None:
        """测试网络错误分类。"""
        error = httpx.NetworkError("Network error")
        assert categorize_error(error) == ErrorCategory.NETWORK

    def test_http_status_error_429(self) -> None:
        """测试 429 错误分类。"""
        response = _make_response(429)
        error = httpx.HTTPStatusError(
            "Rate limited", request=response.request, response=response
        )
        assert categorize_error(error) == ErrorCategory.RATE_LIMIT

    def test_http_status_error_500(self) -> None:
        """测试 5xx 错误分类。"""
        response = _make_response(503)
        error = httpx.HTTPStatusError(
            "Service unavailable", request=response.request, response=response
        )
        assert categorize_error(error) == ErrorCategory.SERVER

    def test_http_status_error_400(self) -> None:
        """测试 4xx 错误分类。"""
        response = _make_response(400)
        error = httpx.HTTPStatusError(
            "Bad request", request=response.request, response=response
        )
        assert categorize_error(error) == ErrorCategory.CLIENT

    def test_unknown_error(self) -> None:
        """测试未知错误分类。"""
        error = ValueError("Unknown error")
        assert categorize_error(error) == ErrorCategory.UNKNOWN


class TestCategorizeResponse:
    """categorize_response 测试。"""

    def test_success_response(self) -> None:
        """测试成功响应。"""
        response = _make_response(200)
        assert categorize_response(response) is None

    def test_redirect_response(self) -> None:
        """测试重定向响应。"""
        response = _make_response(302)
        assert categorize_response(response) is None

    def test_rate_limit_response(self) -> None:
        """测试限流响应。"""
        response = _make_response(429)
        assert categorize_response(response) == ErrorCategory.RATE_LIMIT

    def test_server_error_response(self) -> None:
        """测试服务端错误响应。"""
        response = _make_response(500)
        assert categorize_response(response) == ErrorCategory.SERVER

    def test_client_error_response(self) -> None:
        """测试客户端错误响应。"""
        response = _make_response(404)
        assert categorize_response(response) == ErrorCategory.CLIENT


class TestCalculateDelay:
    """calculate_delay 测试。"""

    def test_first_attempt(self) -> None:
        """测试首次重试延迟。"""
        config = RetryConfig(
            initial_delay_ms=1000,
            multiplier=2.0,
            jitter_factor=0.0,  # 禁用抖动以便测试
        )
        delay = calculate_delay(0, config)
        assert delay == 1000

    def test_exponential_backoff(self) -> None:
        """测试指数退避。"""
        config = RetryConfig(
            initial_delay_ms=1000,
            multiplier=2.0,
            jitter_factor=0.0,
        )
        assert calculate_delay(0, config) == 1000
        assert calculate_delay(1, config) == 2000
        assert calculate_delay(2, config) == 4000

    def test_max_delay(self) -> None:
        """测试最大延迟限制。"""
        config = RetryConfig(
            initial_delay_ms=1000,
            max_delay_ms=5000,
            multiplier=2.0,
            jitter_factor=0.0,
        )
        delay = calculate_delay(10, config)  # 会超过 max_delay
        assert delay == 5000

    def test_retry_after_header(self) -> None:
        """测试 Retry-After 头优先。"""
        config = RetryConfig(
            initial_delay_ms=1000,
            max_delay_ms=30000,
        )
        delay = calculate_delay(0, config, rate_limit_retry_after=5)
        assert delay == 5000

    def test_jitter(self) -> None:
        """测试抖动范围。"""
        config = RetryConfig(
            initial_delay_ms=1000,
            jitter_factor=0.1,
        )
        delays = [calculate_delay(0, config) for _ in range(100)]
        # 延迟应该在 900-1100 范围内
        assert all(900 <= d <= 1100 for d in delays)
        # 应该有不同的值（抖动生效）
        assert len(set(delays)) > 1


class TestShouldRetry:
    """should_retry 测试。"""

    def test_max_retries_exceeded(self) -> None:
        """测试超过最大重试次数。"""
        config = RetryConfig(max_retries=3)
        assert should_retry(ErrorCategory.SERVER, 3, config) is False
        assert should_retry(ErrorCategory.SERVER, 4, config) is False

    def test_retryable_category(self) -> None:
        """测试可重试错误类别。"""
        config = RetryConfig(max_retries=3)
        assert should_retry(ErrorCategory.SERVER, 0, config) is True
        assert should_retry(ErrorCategory.NETWORK, 0, config) is True
        assert should_retry(ErrorCategory.TIMEOUT, 0, config) is True
        assert should_retry(ErrorCategory.RATE_LIMIT, 0, config) is True

    def test_non_retryable_category(self) -> None:
        """测试不可重试错误类别。"""
        config = RetryConfig(max_retries=3)
        assert should_retry(ErrorCategory.CLIENT, 0, config) is False


class TestParseRetryAfter:
    """parse_retry_after 测试。"""

    def test_numeric_value(self) -> None:
        """测试数字值。"""
        response = _make_response(200, headers={"Retry-After": "60"})
        assert parse_retry_after(response) == 60

    def test_no_header(self) -> None:
        """测试无头部。"""
        response = _make_response(200)
        assert parse_retry_after(response) is None

    def test_invalid_value(self) -> None:
        """测试无效值。"""
        response = _make_response(200, headers={"Retry-After": "invalid"})
        assert parse_retry_after(response) is None


class TestRetryAsync:
    """retry_async 测试。"""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self) -> None:
        """测试首次成功。"""
        response = _make_response(200)

        async def success_func() -> httpx.Response:
            return response

        result = await retry_async(success_func, RetryConfig())
        assert result.success is True
        assert result.total_attempts == 1
        assert result.response == response

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self) -> None:
        """测试服务端错误重试。"""
        call_count = 0
        success_response = _make_response(200)
        error_response = _make_response(503)

        async def flaky_func() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return error_response
            return success_response

        config = RetryConfig(
            max_retries=5,
            initial_delay_ms=10,  # 快速测试
        )
        result = await retry_async(flaky_func, config)
        assert result.success is True
        assert result.total_attempts == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_exception(self) -> None:
        """测试异常重试。"""
        call_count = 0
        success_response = _make_response(200)

        async def flaky_func() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("Connection refused")
            return success_response

        config = RetryConfig(
            max_retries=3,
            initial_delay_ms=10,
        )
        result = await retry_async(flaky_func, config)
        assert result.success is True
        assert result.total_attempts == 2

    @pytest.mark.asyncio
    async def test_all_retries_failed(self) -> None:
        """测试所有重试都失败。"""
        error_response = _make_response(500)

        async def always_fail() -> httpx.Response:
            return error_response

        config = RetryConfig(
            max_retries=2,
            initial_delay_ms=10,
        )
        result = await retry_async(always_fail, config)
        assert result.success is False
        assert result.total_attempts == 3  # 1 初始 + 2 重试

    @pytest.mark.asyncio
    async def test_on_retry_callback(self) -> None:
        """测试重试回调。"""
        error_response = _make_response(500)
        success_response = _make_response(200)
        call_count = 0

        async def flaky_func() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return error_response
            return success_response

        callback_calls: list[RetryAttempt] = []

        def on_retry(attempt: RetryAttempt) -> None:
            callback_calls.append(attempt)

        config = RetryConfig(
            max_retries=3,
            initial_delay_ms=10,
        )
        await retry_async(flaky_func, config, on_retry=on_retry)
        # 只有失败的尝试会触发回调
        assert len(callback_calls) == 1
        assert callback_calls[0].attempt_number == 1
        assert callback_calls[0].success is False

    @pytest.mark.asyncio
    async def test_client_error_not_retried(self) -> None:
        """测试客户端错误不重试。"""
        error_response = _make_response(400)

        async def client_error() -> httpx.Response:
            return error_response

        config = RetryConfig(max_retries=3, initial_delay_ms=10)
        result = await retry_async(client_error, config)
        assert result.success is False
        assert result.total_attempts == 1  # 不重试


class TestCreateAuditRecord:
    """create_audit_record 测试。"""

    def test_successful_result(self) -> None:
        """测试成功结果的审计记录。"""
        response = _make_response(200)
        attempt = RetryAttempt(
            attempt_number=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=100,
            success=True,
            status_code=200,
        )
        result = RetryResult(
            success=True,
            attempts=[attempt],
            response=response,
            total_duration_ms=100,
        )
        record = create_audit_record(result, "test_tool", "http://example.com", "GET")
        assert record["tool_name"] == "test_tool"
        assert record["url"] == "http://example.com"
        assert record["method"] == "GET"
        assert record["success"] is True
        assert record["total_attempts"] == 1
        assert record["retries_count"] == 0

    def test_failed_result(self) -> None:
        """测试失败结果的审计记录。"""
        attempt1 = RetryAttempt(
            attempt_number=1,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=100,
            success=False,
            error_category=ErrorCategory.SERVER,
            error_message="HTTP 500",
            status_code=500,
        )
        attempt2 = RetryAttempt(
            attempt_number=2,
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=100,
            success=False,
            error_category=ErrorCategory.SERVER,
            error_message="HTTP 500",
            status_code=500,
        )
        result = RetryResult(
            success=False,
            attempts=[attempt1, attempt2],
            final_error=Exception("All retries failed"),
            total_duration_ms=200,
        )
        record = create_audit_record(result, "test_tool", "http://example.com", "POST")
        assert record["success"] is False
        assert record["total_attempts"] == 2
        assert record["retries_count"] == 1
        assert record["final_error"] == "All retries failed"
        assert len(record["attempts"]) == 2
