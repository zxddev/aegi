# Author: msq
"""审计追踪契约 — Action & ToolTrace 字段 + trace 传播 (Gate-0)。

来源: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
      openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
约束: LLM 调用必须受版本化策略管控；所有调用可审计。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ToolTraceV1(BaseModel):
    uid: str
    case_uid: str
    action_uid: str
    tool_name: str
    request: dict = Field(default_factory=dict)
    response: dict = Field(default_factory=dict)
    status: str
    duration_ms: int | None = None
    error: str | None = None
    policy: dict = Field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None
    created_at: datetime


class ActionV1(BaseModel):
    uid: str
    case_uid: str
    action_type: str
    actor_id: str | None = None
    rationale: str | None = None
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None
    created_at: datetime
