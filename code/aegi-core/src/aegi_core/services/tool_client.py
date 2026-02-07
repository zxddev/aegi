# Author: msq

from __future__ import annotations

from time import monotonic

import httpx

from aegi_core.api.errors import AegiHTTPError


class ToolClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def archive_url(self, url: str) -> dict:
        """URL 归档抓取。"""
        return await self._post("/tools/archive_url", {"url": url})

    async def _post(self, path: str, payload: dict) -> dict:
        """通用 POST 请求，含 retry + 错误处理。"""
        import asyncio

        start = monotonic()
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, json=payload)
                break
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        else:
            raise last_exc  # type: ignore[misc]
        duration_ms = int((monotonic() - start) * 1000)
        try:
            data = resp.json()
        except Exception:
            data = {
                "error_code": "invalid_response",
                "message": "Invalid gateway response",
                "details": {},
            }
        if resp.status_code >= 400:
            if isinstance(data, dict) and {"error_code", "message", "details"}.issubset(
                data.keys()
            ):
                raise AegiHTTPError(
                    resp.status_code,
                    data["error_code"],
                    data["message"],
                    data["details"],
                )
            raise AegiHTTPError(
                resp.status_code, "gateway_error", "Gateway error", {"body": data}
            )
        if isinstance(data, dict):
            data.setdefault("duration_ms", duration_ms)
        return data

    async def meta_search(self, q: str, **kwargs: object) -> dict:
        """元搜索。"""
        return await self._post("/tools/meta_search", {"q": q, **kwargs})

    async def doc_parse(self, artifact_version_uid: str) -> dict:
        """文档解析。"""
        return await self._post(
            "/tools/doc_parse", {"artifact_version_uid": artifact_version_uid}
        )
