# Author: msq
"""Admin endpoints for system monitoring."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aegi_core.api.deps import get_llm_client
from aegi_core.infra.llm_client import LLMClient

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usage")
async def get_usage(
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    """Return cumulative LLM token usage statistics for this process."""
    return llm.get_usage_stats()
