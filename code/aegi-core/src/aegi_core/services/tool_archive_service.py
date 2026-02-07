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


async def call_tool_archive_url(
    session: AsyncSession,
    tool: ToolClient,
    *,
    case_uid: str,
    url: str,
    actor_id: str | None,
    rationale: str | None,
    inputs: dict,
) -> dict:
    """创建 Action，调用 ToolClient.archive_url，记录 ToolTrace。"""
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    action_uid = f"act_{uuid4().hex}"
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="tool.archive_url",
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
        resp = await tool.archive_url(url=url)
        duration_ms = int((monotonic() - start) * 1000)

        policy = resp.get("policy") if isinstance(resp, dict) else {}
        if not isinstance(policy, dict):
            policy = {}

        trace = ToolTrace(
            uid=tool_trace_uid,
            case_uid=case_uid,
            action_uid=action_uid,
            tool_name="archive_url",
            request={"url": url},
            response=resp if isinstance(resp, dict) else {"raw": resp},
            status="ok" if isinstance(resp, dict) else "unknown",
            duration_ms=duration_ms,
            error=None,
            policy=policy,
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
            tool_name="archive_url",
            request={"url": url},
            response={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
            status="denied" if exc.status_code in (403, 429) else "error",
            duration_ms=duration_ms,
            error=exc.error_code,
            policy={
                "allowed": False,
                "reason": exc.error_code,
                "details": exc.details,
            },
        )
        session.add(trace)

        action.outputs = {
            "tool_trace_uid": tool_trace_uid,
            "error_code": exc.error_code,
        }
        await session.commit()
        raise
