"""EventBus 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from aegi_core.services.event_bus import (
    AegiEvent,
    EventBus,
    get_event_bus,
    reset_event_bus,
)


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


def _make_event(**kw) -> AegiEvent:
    defaults = {
        "event_type": "test.event",
        "case_uid": "case_001",
        "payload": {"summary": "test"},
    }
    defaults.update(kw)
    return AegiEvent(**defaults)


# ── 基本注册和触发 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_and_emit_and_wait():
    bus = EventBus()
    received = []

    async def handler(event: AegiEvent):
        received.append(event.event_type)

    bus.on("test.event", handler)
    await bus.emit_and_wait(_make_event())
    assert received == ["test.event"]


@pytest.mark.asyncio
async def test_wildcard_handler():
    bus = EventBus()
    received = []

    async def handler(event: AegiEvent):
        received.append(event.event_type)

    bus.on("*", handler)
    await bus.emit_and_wait(_make_event(event_type="foo"))
    await bus.emit_and_wait(_make_event(event_type="bar"))
    assert received == ["foo", "bar"]


@pytest.mark.asyncio
async def test_no_handlers_does_not_error():
    bus = EventBus()
    await bus.emit_and_wait(_make_event())  # should not raise


@pytest.mark.asyncio
async def test_off_removes_handler():
    bus = EventBus()
    received = []

    async def handler(event: AegiEvent):
        received.append(1)

    bus.on("test.event", handler)
    bus.off("test.event", handler)
    await bus.emit_and_wait(_make_event())
    assert received == []


# ── 异常隔离 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_exception_does_not_affect_others():
    bus = EventBus()
    received = []

    async def bad_handler(event: AegiEvent):
        raise RuntimeError("boom")

    async def good_handler(event: AegiEvent):
        received.append("ok")

    bus.on("test.event", bad_handler)
    bus.on("test.event", good_handler)
    await bus.emit_and_wait(_make_event())
    assert received == ["ok"]


# ── 发射后不管（fire-and-forget） ─────────────────────────────────


@pytest.mark.asyncio
async def test_emit_fire_and_forget():
    bus = EventBus()
    received = []

    async def handler(event: AegiEvent):
        await asyncio.sleep(0.01)
        received.append(1)

    bus.on("test.event", handler)
    await bus.emit(_make_event())
    # handler 还没执行完
    assert received == []
    await bus.drain()
    assert received == [1]


# ── drain ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drain_waits_for_all():
    bus = EventBus()
    received = []

    async def slow_handler(event: AegiEvent):
        await asyncio.sleep(0.02)
        received.append("done")

    bus.on("test.event", slow_handler)
    await bus.emit(_make_event())
    await bus.drain()
    assert received == ["done"]


# ── 全局单例 ─────────────────────────────────────────────


def test_get_event_bus_singleton():
    bus1 = get_event_bus()
    bus2 = get_event_bus()
    assert bus1 is bus2


def test_reset_event_bus():
    bus1 = get_event_bus()
    reset_event_bus()
    bus2 = get_event_bus()
    assert bus1 is not bus2


# ── AegiEvent 默认值 ──────────────────────────────────────────


def test_event_auto_generates_source_event_uid():
    e = _make_event()
    assert e.source_event_uid != ""
    assert len(e.source_event_uid) == 32  # uuid4 hex


def test_event_preserves_explicit_source_event_uid():
    e = _make_event(source_event_uid="my-uid")
    assert e.source_event_uid == "my-uid"


def test_event_is_frozen():
    e = _make_event()
    with pytest.raises(AttributeError):
        e.event_type = "changed"  # type: ignore[misc]
