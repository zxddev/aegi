"""审计记录结构。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ToolTrace(BaseModel):
    """工具调用审计记录。"""

    trace_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    task_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = Field(default=0, ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    success: bool = True
    error_type: str | None = None
    error_message: str | None = None
    result_ref: str | None = None
    policy_decision_id: str | None = None


class ModelTrace(BaseModel):
    """模型调用审计记录。"""

    trace_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    task_id: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = Field(default=0, ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    success: bool = True
    error_type: str | None = None
    error_message: str | None = None
    result_ref: str | None = None
    policy_decision_id: str | None = None


class PolicyDecisionRecord(BaseModel):
    """策略决策审计记录。"""

    decision_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    action: str | None = None
    stage: str | None = None
    task_id: str | None = None
    allow: bool
    reason: str
    enforced: dict[str, object] = Field(default_factory=dict)
    hitl: dict[str, object] = Field(default_factory=dict)
    hitl_required: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None


class Z3ValidationTrace(BaseModel):
    """Z3 约束校验审计记录。

    记录 Z3 时间线校验结果， 记录到审计日志。
    """

    trace_id: str = Field(min_length=1)
    task_id: str | None = None
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = Field(default=0, ge=0)

    # 校验结果
    result: str = Field(description="valid/invalid/unknown")
    checked_constraints: int = Field(default=0, ge=0)
    passed_constraints: int = Field(default=0, ge=0)

    # 违反记录
    violations: list[dict[str, object]] = Field(default_factory=list)

    # 校验上下文
    event_count: int = Field(default=0, ge=0)
    entity_count: int = Field(default=0, ge=0)
