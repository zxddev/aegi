"""MCP Gateway 客户端。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class McpClient:
    """MCP Gateway 客户端。"""

    base_url: str
    api_key: str
    tls_verify: bool

    async def invoke(
        self,
        *,
        tool_name: str,
        payload: dict[str, object],
        trace_id: str | None = None,
        policy_decision_id: str | None = None,
    ) -> dict[str, object]:
        """调用 MCP 工具。"""

        url = f"{self.base_url.rstrip('/')}/tools/{tool_name}/invoke"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if policy_decision_id:
            headers["X-Policy-Decision-ID"] = policy_decision_id
        async with httpx.AsyncClient(trust_env=False, verify=self.tls_verify) as client:
            response = await client.post(
                url, json=payload, headers=headers, timeout=120.0  # 增加到 120 秒
            )
            response.raise_for_status()
            return response.json()

    async def get_audit_tool_trace(self, trace_id: str) -> dict[str, object] | None:
        """获取 MCP Gateway 工具审计记录。"""

        url = f"{self.base_url.rstrip('/')}/admin/audit/tools/{trace_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(trust_env=False, verify=self.tls_verify) as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def get_audit_traces_by_decision(
        self, decision_id: str
    ) -> list[dict[str, object]]:
        """按策略决策 ID 获取 MCP Gateway 审计记录。"""

        url = f"{self.base_url.rstrip('/')}/admin/audit/decisions/{decision_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(trust_env=False, verify=self.tls_verify) as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            payload = response.json()
            tool_traces = payload.get("tool_traces")
            if isinstance(tool_traces, list):
                return tool_traces
            return []
