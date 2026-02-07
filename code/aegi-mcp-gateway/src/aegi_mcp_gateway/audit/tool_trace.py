# Author: msq

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TOOL_TRACES: list[dict[str, Any]] = []

_TRACE_DIR: Path | None = None


def _get_trace_dir() -> Path | None:
    raw = os.getenv("AEGI_GATEWAY_TRACE_DIR")
    if not raw:
        return None
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def record_tool_trace(trace: dict[str, Any]) -> None:
    TOOL_TRACES.append(trace)
    # 持久化到 JSONL 文件
    global _TRACE_DIR  # noqa: PLW0603
    if _TRACE_DIR is None:
        _TRACE_DIR = _get_trace_dir()
    if _TRACE_DIR is not None:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            with open(_TRACE_DIR / f"traces-{today}.jsonl", "a") as f:
                f.write(json.dumps(trace, default=str) + "\n")
        except Exception:
            logger.warning("tool_trace 持久化失败", exc_info=True)


def clear_tool_traces() -> None:
    TOOL_TRACES.clear()
