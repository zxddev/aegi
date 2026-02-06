# Author: msq

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.tool_trace import ToolTrace


router = APIRouter(prefix="/tool_traces", tags=["tool_traces"])


@router.get("/{tool_trace_uid}")
async def get_tool_trace(
    tool_trace_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    t = await session.get(ToolTrace, tool_trace_uid)
    if t is None:
        raise not_found("ToolTrace", tool_trace_uid)

    return {
        "tool_trace_uid": t.uid,
        "case_uid": t.case_uid,
        "action_uid": t.action_uid,
        "tool_name": t.tool_name,
        "status": t.status,
        "duration_ms": t.duration_ms,
        "error": t.error,
        "policy": t.policy,
        "request": t.request,
        "response": t.response,
    }
