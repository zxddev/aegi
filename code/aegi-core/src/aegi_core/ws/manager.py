"""WebSocket 连接管理器，用于推送通知。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

from aegi_core.ws.protocol import NotifyKind, Notify

logger = logging.getLogger(__name__)


class ConnectionManager:
    """管理活跃的 WebSocket 连接，支持推送通知。"""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def register(self, user_id: str, ws: WebSocket) -> None:
        self._connections[user_id] = ws
        logger.info(
            "ws_manager: registered user=%s (total=%d)", user_id, len(self._connections)
        )

    def unregister(self, user_id: str) -> None:
        self._connections.pop(user_id, None)
        logger.info(
            "ws_manager: unregistered user=%s (total=%d)",
            user_id,
            len(self._connections),
        )

    async def notify(
        self, user_id: str, kind: NotifyKind, payload: dict[str, Any]
    ) -> None:
        ws = self._connections.get(user_id)
        if ws is None:
            return
        frame = Notify(kind=kind, payload=payload)
        try:
            await ws.send_text(frame.model_dump_json())
        except Exception:
            logger.warning(
                "ws_manager: failed to notify user=%s", user_id, exc_info=True
            )
            self.unregister(user_id)

    async def broadcast(self, kind: NotifyKind, payload: dict[str, Any]) -> None:
        frame = Notify(kind=kind, payload=payload)
        text = frame.model_dump_json()
        dead: list[str] = []
        for uid, ws in self._connections.items():
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.unregister(uid)


ws_manager = ConnectionManager()
