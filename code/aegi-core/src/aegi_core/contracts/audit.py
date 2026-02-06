"""Audit trail contracts – Action & ToolTrace fields + trace propagation (Gate-0).

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
        openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
Evidence: LLM calls MUST be governed by versioned policy; all invocations auditable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ToolTraceV1(BaseModel):
    uid: str
    case_uid: str
    action_uid: str
    tool_name: str
    request: dict = Field(default_factory=dict)
    response: dict = Field(default_factory=dict)
    status: str
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    policy: dict = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    created_at: datetime


class ActionV1(BaseModel):
    uid: str
    case_uid: str
    action_type: str
    actor_id: Optional[str] = None
    rationale: Optional[str] = None
    inputs: dict = Field(default_factory=dict)
    outputs: dict = Field(default_factory=dict)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    created_at: datetime
