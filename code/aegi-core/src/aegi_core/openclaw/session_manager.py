"""AEGI 用户 ID 到 OpenClaw session key 的映射。

session key 格式: ``agent:team:gateway:{user_id}``

纯映射层，不做别的。权限注入和审计日志在 WS handler 里处理。
"""

from __future__ import annotations

AGENT_ID = "team"
CHANNEL = "gateway"


def session_key_for_user(user_id: str) -> str:
    """根据 AEGI 用户 ID 生成 OpenClaw session key。"""
    return f"agent:{AGENT_ID}:{CHANNEL}:{user_id}"


def user_id_from_session_key(session_key: str) -> str | None:
    """从 session key 里提取 user_id，格式不对返回 *None*。"""
    parts = session_key.split(":")
    if len(parts) == 4 and parts[0] == "agent" and parts[2] == CHANNEL:
        return parts[3]
    return None
