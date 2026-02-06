# Author: msq
from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.contracts.llm_governance import LLMInvocationRequest
from aegi_core.db.session import ENGINE
from aegi_core.services.tool_client import ToolClient
from aegi_core.settings import settings


class GatewayLLMBackend:
    """LLMBackend that delegates to the MCP gateway."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def invoke(self, request: LLMInvocationRequest, prompt: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/llm/invoke",
                json={"request": request.model_dump(), "prompt": prompt},
            )
            resp.raise_for_status()
            return resp.json()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        yield session


def get_tool_client() -> ToolClient:
    return ToolClient(base_url=settings.mcp_gateway_base_url)


def get_llm_backend() -> GatewayLLMBackend:
    return GatewayLLMBackend(base_url=settings.mcp_gateway_base_url)
