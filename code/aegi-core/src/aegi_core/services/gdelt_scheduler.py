# Author: msq
"""GDELT 定时轮询调度器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aegi_core.services.gdelt_monitor import GDELTMonitor

logger = logging.getLogger(__name__)


class GDELTScheduler:
    """轻量级 GDELT 轮询调度器。"""

    def __init__(
        self,
        monitor: GDELTMonitor,
        *,
        interval_minutes: float = 15,
        enabled: bool = True,
        initial_delay_seconds: float = 60.0,
    ) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        if initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must be >= 0")

        self._monitor = monitor
        self._interval_seconds = interval_minutes * 60
        self._interval_minutes = interval_minutes
        self._enabled = enabled
        self._initial_delay_seconds = initial_delay_seconds

        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._running = False

        self._last_poll_time: datetime | None = None
        self._last_successful_poll_time: datetime | None = None
        self._next_poll_time: datetime | None = None

    async def start(self) -> None:
        """启动后台轮询任务。"""
        if not self._enabled:
            logger.info("GDELT scheduler disabled")
            return
        if self.is_running:
            logger.warning("GDELT scheduler already running")
            return

        self._stop_event = asyncio.Event()
        self._running = True
        self._next_poll_time = datetime.now(timezone.utc) + timedelta(
            seconds=self._initial_delay_seconds
        )
        self._task = asyncio.create_task(self._loop(), name="gdelt-scheduler")
        logger.info(
            "GDELT scheduler started, interval=%s min",
            self._interval_minutes,
        )

    async def stop(self) -> None:
        """优雅停止后台轮询任务。"""
        self._running = False
        self._next_poll_time = None
        self._stop_event.set()

        if self._task is None:
            return

        try:
            await self._task
        finally:
            self._task = None
        logger.info("GDELT scheduler stopped")

    async def _loop(self) -> None:
        try:
            if await self._wait_or_stopped(self._initial_delay_seconds):
                return

            while self._running:
                self._last_poll_time = datetime.now(timezone.utc)
                try:
                    logger.info(
                        "GDELT poll starting at %s", self._last_poll_time.isoformat()
                    )
                    new_events = await self._monitor.poll()
                    self._last_successful_poll_time = datetime.now(timezone.utc)
                    logger.info("GDELT poll completed: %d new events", len(new_events))
                    try:
                        csv_events = await self._monitor.poll_events()
                        logger.info(
                            "GDELT Events CSV poll completed: %d new events",
                            len(csv_events),
                        )
                    except Exception:
                        logger.exception("GDELT Events CSV poll failed")
                except Exception:
                    logger.exception("GDELT poll failed, will retry next interval")

                if not self._running:
                    break

                self._next_poll_time = datetime.now(timezone.utc) + timedelta(
                    seconds=self._interval_seconds
                )
                if await self._wait_or_stopped(self._interval_seconds):
                    break
        finally:
            self._running = False
            self._next_poll_time = None

    async def _wait_or_stopped(self, seconds: float) -> bool:
        if seconds <= 0:
            await asyncio.sleep(0)
            return not self._running
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return not self._running

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def interval_minutes(self) -> float:
        return self._interval_minutes

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def last_poll_time(self) -> datetime | None:
        return self._last_poll_time

    @property
    def last_successful_poll_time(self) -> datetime | None:
        return self._last_successful_poll_time

    @property
    def next_poll_time(self) -> datetime | None:
        return self._next_poll_time
