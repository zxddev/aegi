"""AEGI → OpenClaw 反向调用。

让 AEGI 服务（pipeline、定时任务等）把任务派发给 OpenClaw agent，
或把结果注入用户聊天会话。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 单例，app 启动时设置 — 和 ws/handler.py 用同一个实例
_gateway = None


def set_gateway(client: Any) -> None:
    global _gateway
    _gateway = client


def _get_gateway():
    from aegi_core.openclaw.gateway_client import GatewayClient

    assert isinstance(_gateway, GatewayClient), "GatewayClient not initialised"
    return _gateway


async def dispatch_research(
    query: str,
    *,
    case_uid: str = "",
    user_id: str = "",
    timeout: int = 120,
) -> dict[str, Any]:
    """把调研任务派发给 crawler agent。

    pipeline 阶段检测到信息缺口时调用。
    返回 agent 的响应 payload。
    """
    gw = _get_gateway()
    from aegi_core.openclaw.session_manager import session_key_for_user

    session_key = session_key_for_user(user_id) if user_id else None

    prompt = f"请搜索并收集以下主题的最新信息：{query}"
    if case_uid:
        prompt += f"\n关联案例ID: {case_uid}，找到相关信息后请用 aegi_submit_evidence 工具提交。"

    result = await gw.agent_call(
        prompt,
        agent_id="crawler",
        session_key=session_key,
        timeout=timeout,
    )
    logger.info("dispatch_research completed: query=%s case=%s", query[:50], case_uid)
    return result


async def notify_user(
    user_id: str,
    message: str,
    *,
    label: str = "system",
) -> bool:
    """往用户聊天会话里注入一条通知消息。

    用来推送分析结果、定时告警等。
    """
    gw = _get_gateway()
    from aegi_core.openclaw.session_manager import session_key_for_user

    session_key = session_key_for_user(user_id)
    return await gw.chat_inject(session_key, message, label=label)


async def dispatch_and_notify(
    query: str,
    *,
    case_uid: str,
    user_id: str,
    timeout: int = 120,
) -> dict[str, Any]:
    """调研 + 通知：先派发 crawler，再把摘要注入用户会话。"""
    result = await dispatch_research(
        query,
        case_uid=case_uid,
        user_id=user_id,
        timeout=timeout,
    )

    # 从 agent 响应里提取文本
    summary = result.get("text", result.get("message", "研究任务已完成"))
    await notify_user(
        user_id,
        f"🔍 自动调研完成 (案例 {case_uid}):\n{summary}",
        label="auto_research",
    )
    return result
