"""Trace context parsing utilities.

Keep this module free of GatewayConfig/global side effects so it can be unit-tested
without requiring environment variables.
"""

from __future__ import annotations

import re
from uuid import uuid4

_TRACE_ID_RE = re.compile(r"^trace_[0-9a-f]{32}$")


def is_valid_trace_id(trace_id: str) -> bool:
    """校验 trace_id 格式。"""

    return bool(_TRACE_ID_RE.fullmatch(trace_id))


def parse_trace_context(
    header_trace_id: str | None,
    header_policy_decision_id: str | None,
) -> tuple[str, str | None, str | None, str | None]:
    """解析 trace 上下文请求头。

    Returns:
        trace_id: 本次请求用于审计记录的 trace_id（若请求头无效/缺失则自动生成）
        caller_trace_id: 调用方传递的 trace_id（仅当格式合法时保留，否则为 None）
        caller_policy_decision_id: 调用方传递的 policy_decision_id（空白字符串会归一化为 None）
        invalid_trace_id: 若请求头 trace_id 存在但格式非法，则返回原始值用于日志记录
    """

    invalid_trace_id: str | None = None
    if header_trace_id and not is_valid_trace_id(header_trace_id):
        invalid_trace_id = header_trace_id
        header_trace_id = None

    trace_id = header_trace_id or f"trace_{uuid4().hex}"
    caller_trace_id = header_trace_id
    caller_policy_decision_id = (
        header_policy_decision_id.strip()
        if header_policy_decision_id and header_policy_decision_id.strip()
        else None
    )
    return trace_id, caller_trace_id, caller_policy_decision_id, invalid_trace_id
