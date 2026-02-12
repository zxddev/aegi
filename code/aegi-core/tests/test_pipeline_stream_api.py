"""SSE 流式 API 端点测试（pipeline_stream.py）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.main import app


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _parse_sse_events(body: str) -> list[dict]:
    """解析 SSE body 文本为 data dict 列表。"""
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Chat 流式测试
# ---------------------------------------------------------------------------


async def test_chat_stream_sse():
    """POST /chat/stream 返回带流式 token 的 SSE 事件。"""
    mock_llm = MagicMock()

    async def _fake_stream(prompt, **kwargs):
        yield "Hello"
        yield " world"

    mock_llm.invoke_stream = _fake_stream

    with patch(
        "aegi_core.api.routes.pipeline_stream.get_llm_client",
        return_value=mock_llm,
    ):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat/stream",
                json={"message": "test"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            events = _parse_sse_events(resp.text)
            texts = [e["text"] for e in events if "text" in e]
            assert "Hello" in texts
            assert " world" in texts


async def test_chat_stream_done_event():
    """POST /chat/stream 发出最终的 'done' SSE 事件。"""
    mock_llm = MagicMock()

    async def _fake_stream(prompt, **kwargs):
        yield "tok"

    mock_llm.invoke_stream = _fake_stream

    with patch(
        "aegi_core.api.routes.pipeline_stream.get_llm_client",
        return_value=mock_llm,
    ):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat/stream",
                json={"message": "hi"},
            )
            assert resp.status_code == 200
            # body 里应包含 "event: done" 行
            assert "event: done" in resp.text


async def test_chat_stream_error_event():
    """POST /chat/stream LLM 抛异常时发出 error SSE 事件。"""
    mock_llm = MagicMock()

    async def _failing_stream(prompt, **kwargs):
        raise RuntimeError("LLM exploded")
        # 让它成为 async generator
        yield  # pragma: no cover  # noqa: E501

    mock_llm.invoke_stream = _failing_stream

    with patch(
        "aegi_core.api.routes.pipeline_stream.get_llm_client",
        return_value=mock_llm,
    ):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat/stream",
                json={"message": "boom"},
            )
            assert resp.status_code == 200
            assert "event: error" in resp.text
            events = _parse_sse_events(resp.text)
            error_events = [e for e in events if "error" in e]
            assert len(error_events) >= 1
            assert "LLM exploded" in error_events[0]["error"]


# ---------------------------------------------------------------------------
# 订阅 run 测试
# ---------------------------------------------------------------------------


async def test_subscribe_run_not_found():
    """GET .../runs/{run_id}/stream 不存在的 run 返回 error SSE。"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/cases/c1/pipelines/runs/nonexistent/stream",
        )
        # SSE 端点始终返回 200
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        assert any("error" in e for e in events)
        assert any("not found" in e.get("error", "") for e in events)


async def test_chat_stream_validation_error():
    """POST /chat/stream 缺少 'message' 字段时返回 422。"""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={})
        assert resp.status_code == 422
