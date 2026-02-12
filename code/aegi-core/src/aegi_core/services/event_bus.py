"""AEGI 事件驱动层的进程内 asyncio 事件总线。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

EventHandler = Callable[["AegiEvent"], Awaitable[None]]


@dataclass(frozen=True)
class AegiEvent:
    """不可变事件对象，在整个事件链中流转。"""

    event_type: str
    case_uid: str | None
    payload: dict[str, Any]
    entities: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    severity: str = "medium"
    source_event_uid: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.source_event_uid:
            object.__setattr__(self, "source_event_uid", uuid.uuid4().hex)


class EventBus:
    """进程内 asyncio 事件总线。

    - 按 event_type 注册 handler
    - 通配符 "*" 监听所有事件
    - emit 是 fire-and-forget（创建 asyncio.Task，非阻塞）
    - handler 异常会被捕获并记录日志，不会向上传播
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running_tasks: set[asyncio.Task] = set()

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)
        logger.info("EventBus: 注册 handler %s -> %s", event_type, handler.__name__)

    def off(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event: AegiEvent) -> None:
        handlers = list(self._handlers.get(event.event_type, []))
        handlers.extend(self._handlers.get("*", []))
        if not handlers:
            logger.debug("EventBus: %s 无 handler", event.event_type)
            return
        for handler in handlers:
            task = asyncio.create_task(self._safe_call(handler, event))
            self._running_tasks.add(task)
            task.add_done_callback(self._running_tasks.discard)

    async def emit_and_wait(self, event: AegiEvent) -> None:
        """发送事件并等待所有 handler 完成（用于测试）。"""
        handlers = list(self._handlers.get(event.event_type, []))
        handlers.extend(self._handlers.get("*", []))
        await asyncio.gather(
            *(self._safe_call(h, event) for h in handlers),
            return_exceptions=True,
        )

    async def _safe_call(self, handler: EventHandler, event: AegiEvent) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "EventBus: handler %s 处理事件 %s 失败",
                handler.__name__,
                event.event_type,
            )

    async def drain(self) -> None:
        """等待所有运行中的 handler 完成（优雅关闭）。"""
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)


# 模块级单例
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> None:
    """重置全局 bus（用于测试）。"""
    global _bus
    _bus = None
