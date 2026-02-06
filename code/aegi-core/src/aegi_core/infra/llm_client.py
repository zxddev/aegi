# Author: msq
"""LLM client — calls LiteLLM Proxy via OpenAI Responses API."""

from __future__ import annotations

import json as _json
from typing import Any

import httpx

from aegi_core.settings import settings as _settings

from aegi_core.contracts.llm_governance import (
    BudgetContext,
    LLMInvocationRequest,
    LLMInvocationResult,
    GroundingLevel,
)


class LLMClient:
    """Thin wrapper around LiteLLM Proxy /v1/responses endpoint."""

    def __init__(self, base_url: str, api_key: str, default_model: str = "default") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._http = httpx.AsyncClient(
            timeout=120,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        """关闭底层 HTTP 连接池。"""
        await self._http.aclose()

    async def invoke(
        self,
        prompt: str,
        *,
        model: str | None = None,
        request: LLMInvocationRequest | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Call LLM and return parsed response.

        Returns dict with keys: text, model, usage, raw.
        """
        model = model or (request.model_id if request else self._default_model)
        budget = (
            request.budget_context if request else BudgetContext(max_tokens=4096, max_cost_usd=1.0)
        )

        payload: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "stream": False,
        }
        if max_tokens or budget.max_tokens:
            payload["max_output_tokens"] = max_tokens or budget.max_tokens

        resp = await self._http.post(
            f"{self._base_url}/v1/responses",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from Responses API format
        text = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text += content.get("text", "")

        usage = data.get("usage", {})
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
        """Adapter for claim_extractor/hypothesis_engine LLMBackend protocol.

        Calls LLM, parses JSON list from response text. Falls back to
        returning the raw text wrapped in a dict if JSON parsing fails.
        """

        result = await self.invoke(prompt, request=request)
        text = result["text"].strip()
        # Try to extract JSON array from response
        # LLM may wrap it in ```json ... ```
        if "```" in text:
            for block in text.split("```"):
                block = block.strip().removeprefix("json").strip()
                if block.startswith("["):
                    text = block
                    break
        try:
            parsed = _json.loads(text)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except _json.JSONDecodeError:
            return [{"raw_text": text}]

    async def invoke_governed(
        self,
        request: LLMInvocationRequest,
        prompt: str,
    ) -> LLMInvocationResult:
        """Governed invocation that returns LLMInvocationResult."""
        result = await self.invoke(prompt, request=request)
        usage = result["usage"]
        return LLMInvocationResult(
            model_id=result["model"],
            prompt_version=request.prompt_version,
            tokens_used=usage.get("total_tokens", 0),
            cost_usd=0.0,
            grounding_level=GroundingLevel.HYPOTHESIS,
            trace_id=request.trace_id,
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """Get embedding vector from local vLLM BGE-M3 service."""

        resp = await self._http.post(
            f"{_settings.embedding_base_url}/v1/embeddings",
            json={"model": model or _settings.embedding_model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
