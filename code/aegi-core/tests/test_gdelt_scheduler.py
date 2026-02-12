# Author: msq
"""GDELT Scheduler 单元测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from aegi_core.services.gdelt_scheduler import GDELTScheduler


@pytest.mark.asyncio
async def test_scheduler_start_stop() -> None:
    monitor = AsyncMock()
    monitor.poll = AsyncMock(return_value=[])
    scheduler = GDELTScheduler(
        monitor=monitor,
        interval_minutes=1,
        enabled=True,
        initial_delay_seconds=300,
    )

    await scheduler.start()
    assert scheduler.is_running is True

    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_calls_poll() -> None:
    called = asyncio.Event()

    async def _poll():
        called.set()
        return []

    monitor = AsyncMock()
    monitor.poll = AsyncMock(side_effect=_poll)
    scheduler = GDELTScheduler(
        monitor=monitor,
        interval_minutes=0.01,
        enabled=True,
        initial_delay_seconds=0,
    )

    await scheduler.start()
    await asyncio.wait_for(called.wait(), timeout=1.5)
    await scheduler.stop()

    assert monitor.poll.await_count >= 1


@pytest.mark.asyncio
async def test_scheduler_handles_poll_error() -> None:
    calls = 0
    recovered = asyncio.Event()

    async def _poll():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        recovered.set()
        return []

    monitor = AsyncMock()
    monitor.poll = AsyncMock(side_effect=_poll)
    scheduler = GDELTScheduler(
        monitor=monitor,
        interval_minutes=0.01,
        enabled=True,
        initial_delay_seconds=0,
    )

    await scheduler.start()
    await asyncio.wait_for(recovered.wait(), timeout=2.5)
    await scheduler.stop()

    assert calls >= 2


@pytest.mark.asyncio
async def test_scheduler_disabled() -> None:
    monitor = AsyncMock()
    monitor.poll = AsyncMock(return_value=[])
    scheduler = GDELTScheduler(
        monitor=monitor,
        interval_minutes=1,
        enabled=False,
        initial_delay_seconds=0,
    )

    await scheduler.start()
    assert scheduler.is_running is False
    monitor.poll.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_api_status() -> None:
    pytest.importorskip("instructor")
    from httpx import ASGITransport, AsyncClient

    try:
        from aegi_core.api.main import create_app
    except ModuleNotFoundError as exc:
        pytest.skip(f"api dependencies unavailable: {exc}")

    app = create_app()
    monitor = AsyncMock()
    monitor.poll = AsyncMock(return_value=[])
    scheduler = GDELTScheduler(
        monitor=monitor,
        interval_minutes=1,
        enabled=True,
        initial_delay_seconds=300,
    )
    app.state.gdelt_scheduler = scheduler

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/gdelt/monitor/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "stopped"
        assert data["running"] is False

        start_resp = await client.post("/gdelt/monitor/start")
        assert start_resp.status_code == 200
        assert start_resp.json()["state"] == "running"

        stop_resp = await client.post("/gdelt/monitor/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["state"] == "stopped"
