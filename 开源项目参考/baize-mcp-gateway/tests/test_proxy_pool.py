"""代理池测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from baize_mcp_gateway.proxy_pool import (
    LatencyBasedSelector,
    ProxyConfig,
    ProxyHealth,
    ProxyPool,
    ProxyPoolConfig,
    ProxyProtocol,
    RandomSelector,
    RoundRobinSelector,
    parse_proxy_list,
)


class TestProxyConfig:
    """ProxyConfig 测试。"""

    def test_to_url_basic(self) -> None:
        """测试基本 URL 生成。"""
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        assert proxy.to_url() == "http://127.0.0.1:8080"

    def test_to_url_with_auth(self) -> None:
        """测试带认证的 URL 生成。"""
        proxy = ProxyConfig(
            host="proxy.example.com",
            port=3128,
            username="user",
            password="pass",
        )
        assert proxy.to_url() == "http://user:pass@proxy.example.com:3128"

    def test_to_url_socks5(self) -> None:
        """测试 SOCKS5 协议 URL。"""
        proxy = ProxyConfig(
            host="socks.example.com",
            port=1080,
            protocol=ProxyProtocol.SOCKS5,
        )
        assert proxy.to_url() == "socks5://socks.example.com:1080"

    def test_matches_domain_no_rules(self) -> None:
        """测试无规则时匹配所有域名。"""
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        assert proxy.matches_domain("example.com") is True
        assert proxy.matches_domain("any.domain.com") is True
        assert proxy.matches_domain(None) is True

    def test_matches_domain_allowed(self) -> None:
        """测试白名单规则。"""
        proxy = ProxyConfig(
            host="127.0.0.1",
            port=8080,
            allowed_domains=("example.com", "test.org"),
        )
        assert proxy.matches_domain("example.com") is True
        assert proxy.matches_domain("sub.example.com") is True
        assert proxy.matches_domain("other.com") is False

    def test_matches_domain_denied(self) -> None:
        """测试黑名单规则。"""
        proxy = ProxyConfig(
            host="127.0.0.1",
            port=8080,
            denied_domains=("blocked.com",),
        )
        assert proxy.matches_domain("blocked.com") is False
        assert proxy.matches_domain("sub.blocked.com") is False
        assert proxy.matches_domain("allowed.com") is True


class TestParseProxyList:
    """parse_proxy_list 测试。"""

    def test_empty_string(self) -> None:
        """测试空字符串。"""
        assert parse_proxy_list("") == []

    def test_single_proxy(self) -> None:
        """测试单个代理。"""
        proxies = parse_proxy_list("http://127.0.0.1:8080")
        assert len(proxies) == 1
        assert proxies[0].host == "127.0.0.1"
        assert proxies[0].port == 8080
        assert proxies[0].protocol == ProxyProtocol.HTTP

    def test_multiple_proxies(self) -> None:
        """测试多个代理。"""
        proxies = parse_proxy_list(
            "http://127.0.0.1:8080,https://192.168.1.1:3128,socks5://10.0.0.1:1080"
        )
        assert len(proxies) == 3
        assert proxies[0].protocol == ProxyProtocol.HTTP
        assert proxies[1].protocol == ProxyProtocol.HTTPS
        assert proxies[2].protocol == ProxyProtocol.SOCKS5

    def test_proxy_with_auth(self) -> None:
        """测试带认证的代理。"""
        proxies = parse_proxy_list("http://user:pass@proxy.com:8080")
        assert len(proxies) == 1
        assert proxies[0].username == "user"
        assert proxies[0].password == "pass"

    def test_invalid_proxy_skipped(self) -> None:
        """测试跳过无效代理。"""
        proxies = parse_proxy_list(
            "http://127.0.0.1:8080,invalid,http://192.168.1.1:3128"
        )
        assert len(proxies) == 2


class TestProxyHealth:
    """ProxyHealth 测试。"""

    def test_average_latency_no_requests(self) -> None:
        """测试无请求时的平均延迟。"""
        health = ProxyHealth()
        assert health.average_latency_ms == float("inf")

    def test_average_latency(self) -> None:
        """测试平均延迟计算。"""
        health = ProxyHealth(
            successful_requests=2,
            total_latency_ms=200.0,
        )
        assert health.average_latency_ms == 100.0

    def test_success_rate_no_requests(self) -> None:
        """测试无请求时的成功率。"""
        health = ProxyHealth()
        assert health.success_rate == 1.0

    def test_success_rate(self) -> None:
        """测试成功率计算。"""
        health = ProxyHealth(
            total_requests=10,
            successful_requests=8,
        )
        assert health.success_rate == 0.8


class TestProxySelectors:
    """代理选择器测试。"""

    def test_round_robin_empty(self) -> None:
        """测试轮询选择器空列表。"""
        selector = RoundRobinSelector()
        assert selector.select([]) is None

    def test_round_robin_selects_healthy(self) -> None:
        """测试轮询选择器只选择健康代理。"""
        selector = RoundRobinSelector()
        proxy1 = ProxyConfig(host="1.1.1.1", port=8080)
        proxy2 = ProxyConfig(host="2.2.2.2", port=8080)
        health1 = ProxyHealth(is_healthy=False)
        health2 = ProxyHealth(is_healthy=True)
        proxies = [(proxy1, health1), (proxy2, health2)]
        selected = selector.select(proxies)
        assert selected == proxy2

    def test_latency_based_selects_lowest(self) -> None:
        """测试延迟选择器选择最低延迟。"""
        selector = LatencyBasedSelector()
        proxy1 = ProxyConfig(host="1.1.1.1", port=8080)
        proxy2 = ProxyConfig(host="2.2.2.2", port=8080)
        health1 = ProxyHealth(
            is_healthy=True, successful_requests=10, total_latency_ms=1000
        )
        health2 = ProxyHealth(
            is_healthy=True, successful_requests=10, total_latency_ms=500
        )
        proxies = [(proxy1, health1), (proxy2, health2)]
        selected = selector.select(proxies)
        assert selected == proxy2

    def test_random_selects_healthy(self) -> None:
        """测试随机选择器只选择健康代理。"""
        selector = RandomSelector()
        proxy1 = ProxyConfig(host="1.1.1.1", port=8080)
        proxy2 = ProxyConfig(host="2.2.2.2", port=8080)
        health1 = ProxyHealth(is_healthy=False)
        health2 = ProxyHealth(is_healthy=True)
        proxies = [(proxy1, health1), (proxy2, health2)]
        selected = selector.select(proxies)
        assert selected == proxy2


class TestProxyPool:
    """ProxyPool 测试。"""

    def test_add_remove_proxy(self) -> None:
        """测试添加和移除代理。"""
        pool = ProxyPool(ProxyPoolConfig())
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        assert pool.proxy_count == 1
        pool.remove_proxy(proxy)
        assert pool.proxy_count == 0

    def test_get_proxy_empty(self) -> None:
        """测试空池获取代理。"""
        pool = ProxyPool(ProxyPoolConfig())
        assert pool.get_proxy() is None

    def test_get_proxy(self) -> None:
        """测试获取代理。"""
        pool = ProxyPool(ProxyPoolConfig())
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        selected = pool.get_proxy()
        assert selected == proxy

    @pytest.mark.asyncio
    async def test_report_success(self) -> None:
        """测试报告成功。"""
        pool = ProxyPool(ProxyPoolConfig())
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        await pool.report_success(proxy, 100.0)
        stats = pool.get_statistics()
        proxy_stats = stats["proxies"]
        assert isinstance(proxy_stats, list)
        assert len(proxy_stats) == 1
        assert proxy_stats[0]["successful_requests"] == 1
        assert proxy_stats[0]["last_latency_ms"] == 100.0

    @pytest.mark.asyncio
    async def test_report_failure_marks_unhealthy(self) -> None:
        """测试连续失败标记为不健康。"""
        config = ProxyPoolConfig(unhealthy_threshold=2)
        pool = ProxyPool(config)
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        # 第一次失败
        await pool.report_failure(proxy, "error1")
        assert pool.healthy_proxy_count == 1
        # 第二次失败，达到阈值
        await pool.report_failure(proxy, "error2")
        assert pool.healthy_proxy_count == 0

    def test_get_statistics(self) -> None:
        """测试获取统计信息。"""
        pool = ProxyPool(ProxyPoolConfig())
        proxy1 = ProxyConfig(host="1.1.1.1", port=8080)
        proxy2 = ProxyConfig(host="2.2.2.2", port=8080)
        pool.add_proxy(proxy1)
        pool.add_proxy(proxy2)
        stats = pool.get_statistics()
        assert stats["total_proxies"] == 2
        assert stats["healthy_proxies"] == 2
        assert stats["unhealthy_proxies"] == 0

    @pytest.mark.asyncio
    async def test_health_check_lifecycle(self) -> None:
        """测试健康检查生命周期。"""
        pool = ProxyPool(ProxyPoolConfig(health_check_interval_seconds=1))
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        await pool.start_health_check()
        assert pool._running is True
        await pool.stop_health_check()
        assert pool._running is False

    @pytest.mark.asyncio
    async def test_check_proxy_success(self) -> None:
        """测试代理健康检查成功。"""
        pool = ProxyPool(ProxyPoolConfig())
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        _, health = pool._proxies[proxy.to_url()]
        health.is_healthy = False
        health.consecutive_failures = 5

        # Mock httpx 请求成功
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            await pool._check_proxy(proxy, health)

        assert health.is_healthy is True
        assert health.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_check_proxy_failure(self) -> None:
        """测试代理健康检查失败。"""
        config = ProxyPoolConfig(unhealthy_threshold=1)
        pool = ProxyPool(config)
        proxy = ProxyConfig(host="127.0.0.1", port=8080)
        pool.add_proxy(proxy)
        _, health = pool._proxies[proxy.to_url()]

        # Mock httpx 请求失败
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_instance.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_client.return_value = mock_instance

            await pool._check_proxy(proxy, health)

        assert health.is_healthy is False
        assert health.consecutive_failures == 1
