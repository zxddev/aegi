# Author: msq

from __future__ import annotations

from time import monotonic

import httpx

from aegi_core.api.errors import AegiHTTPError


class ToolClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def archive_url(self, url: str) -> dict:
        start = monotonic()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/tools/archive_url", json={"url": url}
            )

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
