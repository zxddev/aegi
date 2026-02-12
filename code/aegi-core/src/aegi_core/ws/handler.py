"""AEGI 前端的 FastAPI WebSocket 端点。

处理 JWT 认证，把聊天消息路由到 OpenClaw Gateway，
再把响应流式推回给用户。
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.action import Action
from aegi_core.db.session import get_engine
from aegi_core.openclaw.event_bridge import chat_event_to_frame
from aegi_core.openclaw.gateway_client import GatewayClient
from aegi_core.openclaw.session_manager import session_key_for_user
from aegi_core.ws.protocol import (
    ChatDone,
    ChatError,
    HistoryResult,
    ServerFrame,
)
from aegi_core.ws.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# app 启动时注入 — 见下面的集成说明
_gateway: GatewayClient | None = None


def set_gateway_client(client: GatewayClient) -> None:
    global _gateway
    _gateway = client


def _get_gateway() -> GatewayClient:
    assert _gateway is not None, "GatewayClient not initialised"
    return _gateway


# ---------------------------------------------------------------------------
# 认证桩 — 后续替换成真正的 JWT 校验
# ---------------------------------------------------------------------------


async def _authenticate(ws: WebSocket) -> str | None:
    """从 WebSocket 连接中提取并校验 user_id。

    JWT token 通过 query 参数 ``?token=xxx`` 或第一条消息传入。
    返回 *user_id*，失败返回 *None*。
    """
    token = ws.query_params.get("token", "")
    if not token:
        return None
    # TODO: 校验 JWT，提取 user_id
    # 开发阶段先把 token 值当 user_id 用
    return token


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def _send_frame(ws: WebSocket, frame: ServerFrame) -> None:
    await ws.send_text(frame.model_dump_json())


def _build_permission_prompt(user_id: str) -> str:
    """构建 extraSystemPrompt，把用户权限注入 agent 上下文。"""
    # TODO: 从 AEGI 数据库查真实权限
    return f"当前用户: {user_id}, 权限级别: analyst"


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    user_id = await _authenticate(ws)
    if not user_id:
        await _send_frame(ws, ChatError(id="auth", message="authentication required"))
        await ws.close(code=4001, reason="auth_failed")
        return

    session_key = session_key_for_user(user_id)
    gateway = _get_gateway()
    logger.info("ws connected user=%s session=%s", user_id, session_key)

    ws_manager.register(user_id, ws)
    try:
        while True:
            raw = await ws.receive_text()
            frame = json.loads(raw)
            ftype = frame.get("type")

            if ftype == "chat.send":
                await _handle_chat_send(ws, gateway, session_key, user_id, frame)
            elif ftype == "chat.abort":
                await gateway.chat_abort(session_key, frame.get("id"))
            elif ftype == "chat.history":
                await _handle_chat_history(ws, gateway, session_key, frame)
            else:
                await _send_frame(
                    ws,
                    ChatError(
                        id=frame.get("id", "?"), message=f"unknown type: {ftype}"
                    ),
                )

    except WebSocketDisconnect:
        logger.info("ws disconnected user=%s", user_id)
    finally:
        ws_manager.unregister(user_id)


async def _audit_chat_send(user_id: str, message: str, msg_id: str) -> None:
    """把 WS 聊天消息记录为 Action 审计条目。"""
    try:
        engine = get_engine()
        async with AsyncSession(engine, expire_on_commit=False) as audit_session:
            audit_session.add(
                Action(
                    uid=f"act_{uuid4().hex}",
                    case_uid=None,
                    action_type="ws.chat_send",
                    actor_id=user_id,
                    inputs={"message": message[:500], "msg_id": msg_id},
                    outputs={},
                )
            )
            await audit_session.commit()
    except Exception:
        logger.warning("Audit log failed for ws.chat_send", exc_info=True)


async def _handle_chat_send(
    ws: WebSocket,
    gateway: GatewayClient,
    session_key: str,
    user_id: str,
    frame: dict[str, Any],
) -> None:
    msg_id = frame.get("id", "?")
    message = frame.get("message", "").strip()
    if not message:
        await _send_frame(ws, ChatError(id=msg_id, message="empty message"))
        return

    # 审计日志 — 记录 WS 聊天消息
    await _audit_chat_send(user_id, message, msg_id)

    try:
        permission_prompt = _build_permission_prompt(user_id)
        got_done = False
        async for evt in gateway.chat_send(
            session_key, message, extra_system_prompt=permission_prompt
        ):
            out = chat_event_to_frame(evt)
            if out:
                await _send_frame(ws, out)
                if isinstance(out, ChatDone):
                    got_done = True
        if not got_done:
            await _send_frame(ws, ChatDone(id=msg_id))
    except Exception as exc:
        logger.exception("chat_send failed user=%s", user_id)
        await _send_frame(ws, ChatError(id=msg_id, message=str(exc)))


async def _handle_chat_history(
    ws: WebSocket,
    gateway: GatewayClient,
    session_key: str,
    frame: dict[str, Any],
) -> None:
    limit = frame.get("limit", 50)
    messages = await gateway.chat_history(session_key, limit)
    await _send_frame(ws, HistoryResult(messages=messages))
