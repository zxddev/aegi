# Author: msq
from __future__ import annotations

from time import monotonic
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.db.models.action import Action
from aegi_core.db.models.case import Case
from aegi_core.db.models.tool_trace import ToolTrace
from aegi_core.services.tool_client import ToolClient


async def call_tool_meta_search(
    session: AsyncSession,
    tool: ToolClient,
    *,
    case_uid: str,
    q: str,
    actor_id: str | None,
    rationale: str | None,
    inputs: dict,
) -> dict:
    """创建 Action，调用 ToolClient.meta_search，记录 ToolTrace。"""
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    action_uid = f"act_{uuid4().hex}"
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="tool.meta_search",
        actor_id=actor_id,
        rationale=rationale,
        inputs=inputs,
        outputs={},
    )
    session.add(action)
    await session.flush()

    start = monotonic()
    tool_trace_uid = f"tt_{uuid4().hex}"

    try:
        resp = await tool.meta_search(q=q)
        duration_ms = int((monotonic() - start) * 1000)

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="meta_search",
            request={"q": q},
            response={"ok": True, "result_count": len(resp.get("results", []))},
            status="ok",
            duration_ms=duration_ms,
            error=None,
            policy={},
        )
        session.add(trace)

        action.outputs = {"tool_trace_uid": tool_trace_uid}
        await session.commit()

        return {
            "action_uid": action_uid,
            "tool_trace_uid": tool_trace_uid,
            "response": resp,
        }
    except AegiHTTPError as exc:
        duration_ms = int((monotonic() - start) * 1000)

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="meta_search",
            request={"q": q},
            response={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
            status="error",
            duration_ms=duration_ms,
            error=exc.error_code,
            policy={},
        )
        session.add(trace)

        action.outputs = {
            "tool_trace_uid": tool_trace_uid,
            "error_code": exc.error_code,
        }
        await session.commit()
        raise
