# Author: msq

from __future__ import annotations

from typing import Any


TOOL_TRACES: list[dict[str, Any]] = []


def record_tool_trace(trace: dict[str, Any]) -> None:
    TOOL_TRACES.append(trace)


def clear_tool_traces() -> None:
    TOOL_TRACES.clear()
