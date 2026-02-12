"""AEGI WebSocket 协议帧定义。

前端（Vue）和 AEGI 后端之间的所有帧都在这里定义。
前端不会接触到 OpenClaw Gateway 的内部细节。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class ToolStatus(str, Enum):
    running = "running"
    done = "done"
    error = "error"


class NotifyKind(str, Enum):
    alert = "alert"
    crawler_done = "crawler_done"
    cron_result = "cron_result"
    pipeline_progress = "pipeline_progress"
    collection_done = "collection_done"


# ---------------------------------------------------------------------------
# 客户端 → 服务端帧
# ---------------------------------------------------------------------------


class ChatSend(BaseModel):
    type: Literal["chat.send"] = "chat.send"
    id: str
    message: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ChatAbort(BaseModel):
    type: Literal["chat.abort"] = "chat.abort"
    id: str


class ChatHistory(BaseModel):
    type: Literal["chat.history"] = "chat.history"
    limit: int = 50


# ---------------------------------------------------------------------------
# 服务端 → 客户端帧
# ---------------------------------------------------------------------------


class ChatDelta(BaseModel):
    type: Literal["chat.delta"] = "chat.delta"
    id: str
    text: str


class ChatTool(BaseModel):
    type: Literal["chat.tool"] = "chat.tool"
    id: str
    tool: str
    status: ToolStatus
    summary: str = ""


class ChatDone(BaseModel):
    type: Literal["chat.done"] = "chat.done"
    id: str


class ChatError(BaseModel):
    type: Literal["chat.error"] = "chat.error"
    id: str
    message: str


class Notify(BaseModel):
    type: Literal["notify"] = "notify"
    kind: NotifyKind
    payload: dict[str, Any] = Field(default_factory=dict)


class HistoryResult(BaseModel):
    type: Literal["chat.history.result"] = "chat.history.result"
    messages: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 联合类型，用于解析
# ---------------------------------------------------------------------------

ClientFrame = ChatSend | ChatAbort | ChatHistory
ServerFrame = ChatDelta | ChatTool | ChatDone | ChatError | Notify | HistoryResult
