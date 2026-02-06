"""审计链路 API（查询/完整性校验）集成测试。

说明：不使用 mock/stub；如未配置 POSTGRES_DSN，将自动跳过。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from baize_core.api.audit_routes import register_audit_chain_routes
from baize_core.schemas.audit import ToolTrace
from baize_core.storage.database import create_session_factory
from baize_core.storage.models import Base
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.mcp_client import McpClient


async def _build_store() -> PostgresStore:
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("未配置 POSTGRES_DSN")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await connection.execute(text("CREATE SCHEMA IF NOT EXISTS baize_core"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    return PostgresStore(session_factory)


class _GatewayAuditHandler(BaseHTTPRequestHandler):
    api_key: str = "gateway_test_key"
    by_trace_id: dict[str, dict[str, object]] = {}
    by_decision_id: dict[str, list[dict[str, object]]] = {}

    def do_GET(self) -> None:  # noqa: N802
        auth = self.headers.get("Authorization", "")
        if auth.strip() != f"Bearer {self.api_key}":
            self.send_response(401)
            self.end_headers()
            return

        if self.path.startswith("/admin/audit/tools/"):
            trace_id = self.path.split("/")[-1]
            record = self.by_trace_id.get(trace_id)
            if record is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(record).encode("utf-8"))
            return

        if self.path.startswith("/admin/audit/decisions/"):
            decision_id = self.path.split("/")[-1]
            records = self.by_decision_id.get(decision_id, [])
            if not records:
                self.send_response(404)
                self.end_headers()
                return
            payload = {"decision_id": decision_id, "tool_traces": records}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _start_gateway_audit_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _GatewayAuditHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


@pytest.mark.asyncio
async def test_audit_chain_query_and_integrity_check() -> None:
    store = await _build_store()

    task_id = f"task_{uuid4().hex}"
    trace_id = f"trace_{uuid4().hex}"
    decision_id = f"pol_{uuid4().hex}"

    await store.record_tool_trace(
        ToolTrace(
            trace_id=trace_id,
            tool_name="meta_search",
            task_id=task_id,
            duration_ms=1,
            success=True,
            policy_decision_id=decision_id,
            result_ref="ok",
        )
    )

    server, port = _start_gateway_audit_server()
    try:
        started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        gateway_record = {
            "trace_id": trace_id,
            "tool_name": "meta_search",
            "started_at": started_at,
            "duration_ms": 10,
            "success": True,
            "error_type": None,
            "error_message": None,
            "result_ref": "ok",
            "policy_decision_id": decision_id,
            "caller_trace_id": trace_id,
            "caller_policy_decision_id": decision_id,
        }
        _GatewayAuditHandler.by_trace_id = {trace_id: gateway_record}
        _GatewayAuditHandler.by_decision_id = {decision_id: [gateway_record]}

        mcp_client = McpClient(
            base_url=f"http://127.0.0.1:{port}",
            api_key=_GatewayAuditHandler.api_key,
            tls_verify=True,
        )

        app = FastAPI()
        register_audit_chain_routes(app, store=store, mcp_audit_client=mcp_client)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # 6.3: 审计链路查询 API
            resp = await client.get(f"/audit/traces/{trace_id}")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["trace_id"] == trace_id
            assert payload["local_tool_trace"]["trace_id"] == trace_id
            assert payload["gateway_tool_trace"]["trace_id"] == trace_id

            resp = await client.get(f"/audit/decisions/{decision_id}")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["decision_id"] == decision_id
            assert len(payload["local_tool_traces"]) == 1
            assert len(payload["gateway_tool_traces"]) == 1

            # 6.4: 完整性校验（闭合）
            resp = await client.post(
                "/audit/integrity-check", json={"task_id": task_id}
            )
            assert resp.status_code == 200
            report = resp.json()
            assert report["task_id"] == task_id
            assert report["total_traces"] == 1
            assert report["matched_gateway_traces"] == 1
            assert report["broken_traces"] == 0
            assert report["ok"] is True
            assert report["issues"] == []
            assert len(report["traces"]) == 1
            assert report["traces"][0]["ok"] is True

            # 6.4: 完整性校验（断裂：Gateway 缺失）
            _GatewayAuditHandler.by_trace_id = {}
            _GatewayAuditHandler.by_decision_id = {}
            resp = await client.post(
                "/audit/integrity-check", json={"task_id": task_id}
            )
            assert resp.status_code == 200
            report = resp.json()
            assert report["ok"] is False
            assert report["broken_traces"] == 1
            assert any(
                issue["issue"] == "missing_gateway_trace" for issue in report["issues"]
            )
    finally:
        server.shutdown()
        server.server_close()
