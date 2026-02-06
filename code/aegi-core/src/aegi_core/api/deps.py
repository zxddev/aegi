from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.session import ENGINE
from aegi_core.services.tool_client import ToolClient
from aegi_core.settings import settings


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        yield session


def get_tool_client() -> ToolClient:
    return ToolClient(base_url=settings.mcp_gateway_base_url)
