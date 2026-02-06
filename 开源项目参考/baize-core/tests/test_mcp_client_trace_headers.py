"""baize-core MCP 客户端 trace 头传递测试（不使用 mock）。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from baize_core.tools.mcp_client import McpClient


class _CaptureHandler(BaseHTTPRequestHandler):
    received: dict[str, object] = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        headers = {k.lower(): v for k, v in dict(self.headers).items()}
        _CaptureHandler.received = {
            "path": self.path,
            "headers": headers,
            "body": body,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # 测试时关闭默认日志输出
        return


def _start_http_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


@pytest.mark.asyncio
async def test_mcp_client_includes_trace_headers() -> None:
    server, port = _start_http_server()
    try:
        client = McpClient(
            base_url=f"http://127.0.0.1:{port}",
            api_key="test_key",
            tls_verify=True,
        )
        trace_id = "trace_" + "0" * 32
        decision_id = "pol_123"

        result = await client.invoke(
            tool_name="demo",
            payload={"x": 1},
            trace_id=trace_id,
            policy_decision_id=decision_id,
        )
        assert result.get("ok") is True

        captured = _CaptureHandler.received
        assert captured.get("path") == "/tools/demo/invoke"
        headers = captured.get("headers")
        assert isinstance(headers, dict)
        assert headers.get("authorization") == "Bearer test_key"
        assert headers.get("x-trace-id") == trace_id
        assert headers.get("x-policy-decision-id") == decision_id
    finally:
        server.shutdown()
        server.server_close()
