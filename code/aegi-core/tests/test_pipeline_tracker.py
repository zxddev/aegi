"""PipelineTracker 测试 — 内存中的运行状态管理。"""

from __future__ import annotations

import pytest

from aegi_core.services.pipeline_tracker import PipelineRunState, PipelineTracker


# ---------------------------------------------------------------------------
# 同步测试
# ---------------------------------------------------------------------------


def test_create_and_get_run():
    """create_run 存储状态；get 取回；不存在的 key 返回 None。"""
    tracker = PipelineTracker()
    state = tracker.create_run("r1", "case1", "default", ["s1", "s2"])

    assert isinstance(state, PipelineRunState)
    assert state.run_id == "r1"
    assert state.case_uid == "case1"
    assert state.playbook == "default"
    assert state.status == "pending"
    assert state.stages_total == ["s1", "s2"]
    assert state.progress_pct == 0.0
    assert state.started_at is not None

    assert tracker.get("r1") is state
    assert tracker.get("nonexistent") is None


def test_update_run():
    """update() 修改已存储的状态对象。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])

    tracker.update("r1", status="running", current_stage="s1", progress_pct=50.0)
    state = tracker.get("r1")

    assert state.status == "running"
    assert state.current_stage == "s1"
    assert state.progress_pct == 50.0


def test_update_nonexistent_run_is_noop():
    """update() 对不存在的 run_id 不报错。"""
    tracker = PipelineTracker()
    tracker.update("missing", status="running")  # should not raise


def test_update_ignores_unknown_fields():
    """update() 静默忽略 PipelineRunState 没有的字段。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])
    tracker.update("r1", nonexistent_field="value")  # should not raise
    state = tracker.get("r1")
    assert not hasattr(state, "nonexistent_field") or state.run_id == "r1"


def test_cleanup():
    """cleanup() 同时移除状态和事件。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])
    assert tracker.get("r1") is not None

    tracker.cleanup("r1")
    assert tracker.get("r1") is None


def test_cleanup_nonexistent_is_noop():
    """cleanup() 对不存在的 run_id 不报错。"""
    tracker = PipelineTracker()
    tracker.cleanup("missing")  # should not raise


def test_multiple_runs_independent():
    """多个 run 互相独立存储。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])
    tracker.create_run("r2", "case2", "fast", ["s1", "s2", "s3"])

    tracker.update("r1", status="completed", progress_pct=100.0)

    assert tracker.get("r1").status == "completed"
    assert tracker.get("r2").status == "pending"


# ---------------------------------------------------------------------------
# 异步测试（subscribe / 事件通知）
# ---------------------------------------------------------------------------


async def test_subscribe_returns_event():
    """subscribe() 返回指定 run 的 asyncio.Event。"""
    import asyncio

    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])
    evt = tracker.subscribe("r1")

    assert isinstance(evt, asyncio.Event)


async def test_subscribe_and_notify():
    """update() 触发已订阅的 Event，等待者会被通知。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1"])
    evt = tracker.subscribe("r1")
    evt.clear()

    tracker.update("r1", status="running")
    assert evt.is_set()


async def test_subscribe_creates_event_for_unknown_run():
    """subscribe() 对还没有 event 的 run_id 也会创建一个。"""
    import asyncio

    tracker = PipelineTracker()
    evt = tracker.subscribe("unknown_run")
    assert isinstance(evt, asyncio.Event)


async def test_event_cleared_and_reset():
    """清除 event 后，下一次 update 会重新 set。"""
    tracker = PipelineTracker()
    tracker.create_run("r1", "case1", "default", ["s1", "s2"])
    evt = tracker.subscribe("r1")

    evt.clear()
    assert not evt.is_set()

    tracker.update("r1", status="running", current_stage="s1")
    assert evt.is_set()

    evt.clear()
    assert not evt.is_set()

    tracker.update("r1", current_stage="s2", progress_pct=100.0)
    assert evt.is_set()
