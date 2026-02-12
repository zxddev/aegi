"""OSINT 管道阶段测试 — should_skip 逻辑。"""

from __future__ import annotations

import pytest

from aegi_core.services.stages.osint_collect import OSINTCollectStage
from aegi_core.services.stages.base import StageContext


def test_osint_stage_skip_no_query():
    """config 为空的 StageContext -> should_skip 返回原因字符串。"""
    stage = OSINTCollectStage()
    ctx = StageContext(case_uid="test", config={})
    reason = stage.should_skip(ctx)
    assert reason is not None
    assert "osint_query" in reason


def test_osint_stage_skip_returns_reason():
    """显式检查: 空 config 意味着跳过并给出原因。"""
    stage = OSINTCollectStage()
    ctx = StageContext(case_uid="test", config={})
    assert stage.should_skip(ctx) is not None


def test_osint_stage_has_query():
    """有 osint_query 时，should_skip 返回 None（不跳过）。"""
    stage = OSINTCollectStage()
    ctx = StageContext(case_uid="test", config={"osint_query": "test query"})
    assert stage.should_skip(ctx) is None


def test_osint_stage_name():
    """阶段名应为 'osint_collect'。"""
    stage = OSINTCollectStage()
    assert stage.name == "osint_collect"
