"""把 OpenClaw Gateway 的 ``ChatEvent`` 转成 AEGI WS 协议帧。"""

from __future__ import annotations

from aegi_core.openclaw.gateway_client import ChatEvent
from aegi_core.ws.protocol import (
    ChatDelta,
    ChatDone,
    ChatError,
    ChatTool,
    ServerFrame,
    ToolStatus,
)


def chat_event_to_frame(evt: ChatEvent) -> ServerFrame | None:
    """把单个 Gateway ChatEvent 转成 AEGI server frame。

    不需要转发给前端的事件返回 *None*。
    """
    if evt.state == "final":
        if evt.text:
            return ChatDelta(id=evt.run_id, text=evt.text)
        return ChatDone(id=evt.run_id)

    if evt.state == "error":
        return ChatError(id=evt.run_id, message=evt.error or "unknown error")

    if evt.tool:
        status = ToolStatus.running if evt.tool_status != "done" else ToolStatus.done
        return ChatTool(id=evt.run_id, tool=evt.tool, status=status, summary=evt.text)

    if evt.text:
        return ChatDelta(id=evt.run_id, text=evt.text)

    return None
