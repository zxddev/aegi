"""LLMClient.invoke_stream() 测试 — SSE token 流式输出。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from aegi_core.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_sse_line(content: str) -> str:
    """构造一条包含指定 content token 的 SSE data 行。"""
    chunk = {"choices": [{"delta": {"content": content}}]}
    return f"data: {json.dumps(chunk)}"


def _mock_stream_factory(lines: list[str]):
    """返回一个 async context manager，其 ``aiter_lines`` 迭代 *lines*。"""

    @asynccontextmanager
    async def _mock_stream(*_args, **_kwargs):
        class _Resp:
            def raise_for_status(self):
                pass

            async def aiter_lines(self_inner):  # noqa: N805
                for line in lines:
                    yield line

        yield _Resp()

    return _mock_stream


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


async def test_invoke_stream_basic():
    """Mock httpx 流式响应，验证 token 按顺序 yield。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    lines = [
        _make_sse_line("Hello"),
        _make_sse_line(" world"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    tokens: list[str] = []
    async for token in client.invoke_stream("test prompt"):
        tokens.append(token)

    assert tokens == ["Hello", " world"]
    await client.aclose()


async def test_invoke_stream_done_signal():
    """[DONE] 终止流 — 之后的 token 被忽略。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    lines = [
        _make_sse_line("first"),
        "data: [DONE]",
        _make_sse_line("should_not_appear"),
    ]
    client._http.stream = _mock_stream_factory(lines)

    tokens: list[str] = []
    async for token in client.invoke_stream("prompt"):
        tokens.append(token)

    assert tokens == ["first"]
    await client.aclose()


async def test_invoke_stream_skips_non_data_lines():
    """不以 'data: ' 开头的行应被静默跳过。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    lines = [
        "",
        ": keepalive",
        "event: ping",
        _make_sse_line("ok"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    tokens: list[str] = []
    async for token in client.invoke_stream("prompt"):
        tokens.append(token)

    assert tokens == ["ok"]
    await client.aclose()


async def test_invoke_stream_skips_empty_content():
    """delta 的 content 为空字符串时不应 yield token。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    lines = [
        _make_sse_line(""),
        _make_sse_line("real"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    tokens: list[str] = []
    async for token in client.invoke_stream("prompt"):
        tokens.append(token)

    assert tokens == ["real"]
    await client.aclose()


async def test_invoke_stream_skips_malformed_json():
    """格式错误的 JSON data 行应被静默跳过。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    lines = [
        "data: {not valid json",
        _make_sse_line("good"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    tokens: list[str] = []
    async for token in client.invoke_stream("prompt"):
        tokens.append(token)

    assert tokens == ["good"]
    await client.aclose()


async def test_invoke_stream_increments_request_count():
    """完整流结束后 _total_requests 应加 1。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")
    assert client._total_requests == 0

    lines = [
        _make_sse_line("a"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    async for _ in client.invoke_stream("prompt"):
        pass

    assert client._total_requests == 1
    await client.aclose()


async def test_invoke_stream_passes_model_and_max_tokens():
    """验证 model 和 max_tokens 被正确传入 POST payload。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    captured_kwargs: dict = {}

    @asynccontextmanager
    async def _capture_stream(*args, **kwargs):
        captured_kwargs.update(kwargs)

        class _Resp:
            def raise_for_status(self):
                pass

            async def aiter_lines(self_inner):  # noqa: N805
                yield "data: [DONE]"

        yield _Resp()

    client._http.stream = _capture_stream

    async for _ in client.invoke_stream(
        "prompt",
        model="gpt-4",
        max_tokens=512,
        temperature=0.5,
    ):
        pass

    payload = captured_kwargs.get("json", {})
    assert payload["model"] == "gpt-4"
    assert payload["max_tokens"] == 512
    assert payload["temperature"] == 0.5
    assert payload["stream"] is True
    await client.aclose()


# ---------------------------------------------------------------------------
# 测试 — _buffered_stream（invoke() chat completions 回退）
# ---------------------------------------------------------------------------


def _make_sse_chunk(content: str, model: str = "test-model") -> str:
    """构造带 model 字段的 SSE data 行，用于 buffered stream 测试。"""
    chunk = {"model": model, "choices": [{"delta": {"content": content}}]}
    return f"data: {json.dumps(chunk)}"


async def test_invoke_buffered_stream_basic():
    """invoke() 回退到 chat completions 时应缓冲 SSE delta。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    # 让 /v1/responses 返回 404，invoke() 回退到 chat completions
    import httpx

    async def _fake_post(url, *, json=None, headers=None, **kw):
        if "/v1/responses" in url:
            resp = httpx.Response(404, request=httpx.Request("POST", url))
            raise httpx.HTTPStatusError(
                "Not Found", request=resp.request, response=resp
            )
        raise AssertionError("unexpected URL")

    client._http.post = _fake_post

    lines = [
        _make_sse_chunk("Hello"),
        _make_sse_chunk(", "),
        _make_sse_chunk("world!"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    result = await client.invoke("test prompt")

    assert result["text"] == "Hello, world!"
    assert result["model"] == "test-model"
    assert result["usage"] == {}
    assert client._total_requests == 1
    await client.aclose()


async def test_invoke_buffered_stream_empty_deltas():
    """空 content delta 在缓冲时应被跳过。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    import httpx

    async def _fake_post(url, *, json=None, headers=None, **kw):
        if "/v1/responses" in url:
            resp = httpx.Response(404, request=httpx.Request("POST", url))
            raise httpx.HTTPStatusError(
                "Not Found", request=resp.request, response=resp
            )
        raise AssertionError("unexpected URL")

    client._http.post = _fake_post

    lines = [
        _make_sse_chunk(""),
        _make_sse_chunk("ok"),
        _make_sse_chunk(""),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    result = await client.invoke("test")
    assert result["text"] == "ok"
    await client.aclose()


async def test_invoke_buffered_stream_malformed_lines():
    """格式错误的 SSE 行应被静默跳过。"""
    client = LLMClient(base_url="http://fake:8000", api_key="test")

    import httpx

    async def _fake_post(url, *, json=None, headers=None, **kw):
        if "/v1/responses" in url:
            resp = httpx.Response(404, request=httpx.Request("POST", url))
            raise httpx.HTTPStatusError(
                "Not Found", request=resp.request, response=resp
            )
        raise AssertionError("unexpected URL")

    client._http.post = _fake_post

    lines = [
        "data: {broken json",
        "",
        ": keepalive",
        _make_sse_chunk("fine"),
        "data: [DONE]",
    ]
    client._http.stream = _mock_stream_factory(lines)

    result = await client.invoke("test")
    assert result["text"] == "fine"
    await client.aclose()
