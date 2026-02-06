"""trace_context 单元测试（不依赖环境变量、不使用 mock）。"""

from __future__ import annotations

from baize_mcp_gateway.trace_context import is_valid_trace_id, parse_trace_context


def test_is_valid_trace_id() -> None:
    assert is_valid_trace_id("trace_" + "0" * 32) is True
    assert is_valid_trace_id("trace_" + "a" * 32) is True
    assert is_valid_trace_id("trace_" + "A" * 32) is False
    assert is_valid_trace_id("trace_" + "0" * 31) is False
    assert is_valid_trace_id("trace_" + "0" * 33) is False
    assert is_valid_trace_id("bad") is False


def test_parse_trace_context_with_valid_headers() -> None:
    trace_id, caller_trace_id, caller_decision_id, invalid = parse_trace_context(
        "trace_" + "1" * 32,
        "  pol_123  ",
    )
    assert trace_id == "trace_" + "1" * 32
    assert caller_trace_id == "trace_" + "1" * 32
    assert caller_decision_id == "pol_123"
    assert invalid is None


def test_parse_trace_context_with_invalid_trace_header() -> None:
    trace_id, caller_trace_id, caller_decision_id, invalid = parse_trace_context(
        "trace_NOT_HEX",
        "pol_123",
    )
    assert is_valid_trace_id(trace_id) is True
    assert caller_trace_id is None
    assert caller_decision_id == "pol_123"
    assert invalid == "trace_NOT_HEX"


def test_parse_trace_context_without_headers() -> None:
    trace_id, caller_trace_id, caller_decision_id, invalid = parse_trace_context(
        None, None
    )
    assert is_valid_trace_id(trace_id) is True
    assert caller_trace_id is None
    assert caller_decision_id is None
    assert invalid is None


def test_parse_trace_context_blank_policy_decision_id() -> None:
    trace_id, caller_trace_id, caller_decision_id, invalid = parse_trace_context(
        "trace_" + "2" * 32,
        "   ",
    )
    assert trace_id == "trace_" + "2" * 32
    assert caller_trace_id == "trace_" + "2" * 32
    assert caller_decision_id is None
    assert invalid is None
