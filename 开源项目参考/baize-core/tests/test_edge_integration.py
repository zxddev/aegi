"""边缘网关端到端集成测试。

通过环境变量启用，避免在缺少网关/WAF时失败。
"""

from __future__ import annotations

import os

import httpx
import pytest

EDGE_BASE_URL = os.getenv("BAIZE_E2E_EDGE_BASE_URL", "").strip()
WAF_TEST_ENABLED = os.getenv("BAIZE_E2E_WAF_TEST", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


@pytest.mark.asyncio
async def test_edge_health_routes() -> None:
    """验证 edge 网关能转发核心服务健康检查。"""
    if not EDGE_BASE_URL:
        pytest.skip("set BAIZE_E2E_EDGE_BASE_URL to run edge gateway checks")

    async with httpx.AsyncClient(base_url=EDGE_BASE_URL, timeout=10.0) as client:
        core_resp = await client.get("/api/v1/agent/health")
        assert core_resp.status_code == 200

        mcp_resp = await client.get("/api/v1/mcp/health")
        assert mcp_resp.status_code == 200


@pytest.mark.asyncio
async def test_edge_waf_blocks_suspicious_payload() -> None:
    """验证 WAF 能拦截明显的脚本注入请求。"""
    if not EDGE_BASE_URL or not WAF_TEST_ENABLED:
        pytest.skip(
            "set BAIZE_E2E_EDGE_BASE_URL and BAIZE_E2E_WAF_TEST=1 to run WAF check"
        )

    async with httpx.AsyncClient(base_url=EDGE_BASE_URL, timeout=10.0) as client:
        resp = await client.get(
            "/api/v1/agent/health",
            params={"q": "<script>alert(1)</script>"},
        )
        assert resp.status_code in {403, 406}
