# Author: msq

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app
from aegi_mcp_gateway.audit.tool_trace import TOOL_TRACES, clear_tool_traces


@pytest.fixture(autouse=True)
def _clear_traces() -> None:
    clear_tool_traces()


def test_archive_url_denied_by_default_returns_structured_error_and_records_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 设置白名单但不包含目标域名 → 拒绝
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "other.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com"})

    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == "policy_denied"
    assert "message" in body
    assert "details" in body

    assert len(TOOL_TRACES) == 1
    trace = TOOL_TRACES[0]
    assert trace["tool_name"] == "archive_url"
    assert trace["policy"]["allowed"] is False


def test_archive_url_allowed_when_domain_in_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com/x"})

    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
    assert "policy" in body
    assert body["policy"]["allowed"] is True
    assert body["policy"]["domain"] == "example.com"

    assert len(TOOL_TRACES) == 1
    assert TOOL_TRACES[0]["policy"]["allowed"] is True


def test_validation_error_uses_unified_error_shape() -> None:
    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert "message" in body
    assert "details" in body


def test_rate_limit_denies_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")
    monkeypatch.setenv("AEGI_GATEWAY_MIN_INTERVAL_MS", "60000")

    client = TestClient(app)
    first = client.post("/tools/archive_url", json={"url": "https://example.com/x"})
    assert first.status_code == 200

    second = client.post("/tools/archive_url", json={"url": "https://example.com/x"})
    assert second.status_code == 429
    body = second.json()
    assert body["error_code"] == "rate_limited"


def test_tool_trace_contains_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com/x"})
    assert resp.status_code == 200

    trace: dict[str, Any] = TOOL_TRACES[0]
    assert trace["tool_name"] == "archive_url"
    assert "request" in trace
    assert "response" in trace
    assert "status" in trace
    assert "duration_ms" in trace
    assert "error" in trace
    assert "policy" in trace
    assert "robots" in trace["policy"]


def test_archive_url_timeout_returns_error_without_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")
    monkeypatch.setenv("AEGI_GATEWAY_ARCHIVEBOX_TIMEOUT_S", "0.05")

    class _SlowProc:
        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.5)
            return b"", b""

        def kill(self) -> None:
            return None

    async def _mock_create_subprocess_exec(*args, **kwargs):
        return _SlowProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _mock_create_subprocess_exec)

    client = TestClient(app)
    start = time.monotonic()
    resp = client.post("/tools/archive_url", json={"url": "https://example.com/x"})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "timed out" in body["error"].lower()
    assert elapsed < 1.0
