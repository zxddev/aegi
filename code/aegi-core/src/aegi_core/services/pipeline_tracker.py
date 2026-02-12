"""内存中的 pipeline 运行状态追踪，用于 SSE 进度推送。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunState:
    run_id: str
    case_uid: str
    playbook: str
    status: str = "pending"  # pending | running | completed | failed
    current_stage: str = ""
    stages_completed: list[str] = field(default_factory=list)
    stages_total: list[str] = field(default_factory=list)
    progress_pct: float = 0.0
    message: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PipelineTracker:
    """内存 pipeline 运行状态追踪，支持 SSE 订阅。"""

    def __init__(self) -> None:
        self._runs: dict[str, PipelineRunState] = {}
        self._events: dict[str, asyncio.Event] = {}

    def create_run(
        self,
        run_id: str,
        case_uid: str,
        playbook: str,
        stages: list[str],
    ) -> PipelineRunState:
        state = PipelineRunState(
            run_id=run_id,
            case_uid=case_uid,
            playbook=playbook,
            status="pending",
            stages_total=list(stages),
            started_at=datetime.now(timezone.utc),
        )
        self._runs[run_id] = state
        self._events[run_id] = asyncio.Event()
        return state

    def update(self, run_id: str, **kwargs: object) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        for k, v in kwargs.items():
            if hasattr(state, k):
                setattr(state, k, v)
        # 唤醒 SSE 订阅者
        evt = self._events.get(run_id)
        if evt:
            evt.set()

    def get(self, run_id: str) -> PipelineRunState | None:
        return self._runs.get(run_id)

    def subscribe(self, run_id: str) -> asyncio.Event:
        """返回一个 Event，运行状态变化时会被 set。"""
        if run_id not in self._events:
            self._events[run_id] = asyncio.Event()
        return self._events[run_id]

    def cleanup(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
        self._events.pop(run_id, None)


pipeline_tracker = PipelineTracker()
