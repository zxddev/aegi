# Author: msq
"""LLM 客户端 — 通过 OpenAI Responses API 调用 LiteLLM Proxy。"""

from __future__ import annotations

import json as _json
import re as _re
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from aegi_core.settings import settings as _settings

from aegi_core.contracts.llm_governance import (
    BudgetContext,
    LLMInvocationRequest,
    LLMInvocationResult,
    GroundingLevel,
)

_T = TypeVar("_T", bound=BaseModel)


def parse_llm_json(text: str) -> dict | list | None:
    """从 LLM 输出文本中提取 JSON，处理 markdown fence 和格式噪声。"""
    text = text.strip()
    # 剥离 markdown 代码块
    if "```" in text:
        for block in text.split("```"):
            block = block.strip().removeprefix("json").strip()
            if block.startswith(("{", "[")):
                text = block
                break
    # 直接解析
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        pass
    # regex fallback: 提取最外层 {} 或 []
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = _re.search(pattern, text, _re.DOTALL)
        if m:
            try:
                return _json.loads(m.group())
            except _json.JSONDecodeError:
                pass
    return None


class LLMClient:
    """LiteLLM Proxy /v1/responses 的轻量封装。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_model: str = "default",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        hdrs = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            hdrs.update(extra_headers)
        self._http = httpx.AsyncClient(timeout=120, headers=hdrs)
        # Instructor client — 走 Chat Completions API 用于结构化输出
        self._instructor = instructor.from_openai(
            AsyncOpenAI(
                base_url=f"{base_url.rstrip('/')}/v1",
                api_key=api_key,
                timeout=120,
                default_headers=extra_headers or {},
            )
        )
        # Token/费用追踪
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_requests: int = 0

    async def aclose(self) -> None:
        """关闭底层 HTTP 连接池。"""
        await self._http.aclose()

    def get_usage_stats(self) -> dict:
        """返回累计 token 用量统计。"""
        total = self._total_prompt_tokens + self._total_completion_tokens
        return {
            "total_requests": self._total_requests,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": total,
        }

    async def _post_with_retry(
        self,
        url: str,
        payload: dict,
        *,
        retries: int = 3,
        backoff: float = 0.5,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """带指数退避重试的 POST 请求。"""
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = await self._http.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code < 500
                ):
                    raise
                if attempt < retries - 1:
                    await asyncio.sleep(backoff * (2**attempt))
        raise last_exc  # type: ignore[misc]

    async def invoke(
        self,
        prompt: str,
        *,
        model: str | None = None,
        request: LLMInvocationRequest | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """调用 LLM 并返回解析后的响应。

        返回 dict，包含 keys: text, model, usage, raw。
        """
        req_model = request.model_id if request else None
        if req_model == "default":
            req_model = None
        model = model or req_model or self._default_model
        budget = (
            request.budget_context
            if request
            else BudgetContext(max_tokens=4096, max_cost_usd=1.0)
        )

        payload: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "stream": False,
        }
        if max_tokens or budget.max_tokens:
            payload["max_output_tokens"] = max_tokens or budget.max_tokens

        try:
            resp = await self._post_with_retry(
                f"{self._base_url}/v1/responses", payload
            )
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # 回退到 Chat Completions API — 始终用 stream 模式，
                # 因为后端即使 stream:false 也返回 SSE。
                chat_payload: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": True,
                    "temperature": temperature,
                }
                if max_tokens or budget.max_tokens:
                    chat_payload["max_tokens"] = max_tokens or budget.max_tokens
                text, model_id = await self._buffered_stream(
                    f"{self._base_url}/v1/chat/completions",
                    chat_payload,
                )
                self._total_requests += 1
                return {
                    "text": text,
                    "model": model_id or model,
                    "usage": {},
                    "raw": {},
                }
            raise

        # 从 Responses API 格式中提取文本
        # reasoning model 会先输出 reasoning，再输出 message
        text = ""
        reasoning = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")
            elif item.get("type") == "reasoning":
                for content in item.get("content", []):
                    if content.get("type") == "reasoning_text":
                        reasoning += content.get("text", "")
        # fallback: reasoning model token 不足时只有 reasoning 无 message
        if not text and reasoning:
            text = reasoning

        usage = data.get("usage", {})
        self._total_prompt_tokens += usage.get("input_tokens", 0) or usage.get(
            "prompt_tokens", 0
        )
        self._total_completion_tokens += usage.get("output_tokens", 0) or usage.get(
            "completion_tokens", 0
        )
        self._total_requests += 1
        return {
            "text": text,
            "model": data.get("model", model),
            "usage": usage,
            "raw": data,
        }

    async def invoke_as_backend(
        self,
        request: LLMInvocationRequest,
        prompt: str,
    ) -> list[dict]:
        """适配 claim_extractor/hypothesis_engine 的 LLMBackend 协议。

        调用 LLM，从响应文本解析 JSON list。解析失败时把原始文本包在 dict 里返回。
        """
        result = await self.invoke(prompt, request=request)
        parsed = parse_llm_json(result["text"])
        if parsed is None:
            return [{"raw_text": result["text"].strip()}]
        return parsed if isinstance(parsed, list) else [parsed]

    async def invoke_structured(
        self,
        prompt: str,
        response_model: type[_T],
        *,
        model: str | None = None,
        request: LLMInvocationRequest | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> _T:
        """调用 LLM 并返回 Pydantic 结构化输出（走 Responses API，同 invoke）。

        验证失败时自动重试 max_retries 次。
        """
        last_exc: Exception | None = None
        for _attempt in range(1 + max_retries):
            result = await self.invoke(
                prompt,
                model=model,
                request=request,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            parsed = parse_llm_json(result["text"])
            if parsed is None:
                last_exc = ValueError(f"LLM 未返回有效 JSON: {result['text'][:200]}")
                continue
            try:
                return response_model.model_validate(parsed)
            except Exception as exc:
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    async def invoke_governed(
        self,
        request: LLMInvocationRequest,
        prompt: str,
    ) -> LLMInvocationResult:
        """受治理的调用，返回 LLMInvocationResult。"""
        result = await self.invoke(prompt, request=request)
        usage = result["usage"]
        prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0) or usage.get(
            "output_tokens", 0
        )
        total = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
        return LLMInvocationResult(
            model_id=result["model"],
            prompt_version=request.prompt_version,
            tokens_used=total,
            cost_usd=0.0,
            grounding_level=GroundingLevel.HYPOTHESIS,
            trace_id=request.trace_id,
        )

    async def _buffered_stream(
        self,
        url: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        """发送 stream:true 请求，把所有 delta 拼成完整字符串。

        返回 (full_text, model_id)。复用和 ``invoke_stream`` 相同的 SSE 解析逻辑。
        """
        parts: list[str] = []
        model_id: str = ""
        async with self._http.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data_str)
                    if not model_id:
                        model_id = chunk.get("model", "")
                    delta = chunk["choices"][0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        parts.append(text)
                except (_json.JSONDecodeError, KeyError, IndexError):
                    continue
        return "".join(parts), model_id

    async def invoke_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        """通过 /v1/chat/completions stream=true 流式返回 LLM token。"""
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with self._http.stream(
            "POST",
            f"{self._base_url}/v1/chat/completions",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        yield text
                except (_json.JSONDecodeError, KeyError, IndexError):
                    continue

        self._total_requests += 1

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """从本地 vLLM BGE-M3 服务获取 embedding 向量。"""

        resp = await self._post_with_retry(
            f"{_settings.embedding_base_url}/v1/embeddings",
            {"model": model or _settings.embedding_model, "input": text},
            headers={"Authorization": f"Bearer {_settings.embedding_api_key}"},
        )
        data = resp.json()
        return data["data"][0]["embedding"]
