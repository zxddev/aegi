"""策略引擎契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_decision_id() -> str:
    """生成策略决策 ID。"""

    return f"pol_{uuid4().hex}"


class ActionType(str, Enum):
    """策略请求动作类型。"""

    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    EXPORT = "export"


class StageType(str, Enum):
    """编排阶段。"""

    OUTLINE = "outline"
    PLANNING = "planning"
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"
    SYNTHESIS = "synthesis"


class RiskLevel(str, Enum):
    """风险级别。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SensitivityLevel(str, Enum):
    """敏感级别。"""

    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


class PlannedCost(BaseModel):
    """成本预估。"""

    token_estimate: int = Field(ge=0)
    tool_timeout_ms: int = Field(ge=0)


class RuntimeBudget(BaseModel):
    """运行预算。"""

    token_budget_remaining: int = Field(ge=0)
    model_calls_remaining: int = Field(ge=0)
    tool_calls_remaining: int = Field(ge=0)
    deadline_ms_remaining: int = Field(ge=0)


class PolicyPayload(BaseModel):
    """策略载荷。"""

    model: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None


class PolicyRequest(BaseModel):
    """策略请求。"""

    request_id: str = Field(min_length=1)
    action: ActionType
    stage: StageType
    task_id: str = Field(min_length=1)
    section_id: str | None = None
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    risk_level: RiskLevel = RiskLevel.LOW
    planned_cost: PlannedCost
    payload: PolicyPayload
    runtime: RuntimeBudget


class EnforcedPolicy(BaseModel):
    """策略约束输出。"""

    selected_model: str | None = None
    timeout_ms: int | None = None
    max_concurrency: int | None = None
    max_pages: int | None = None
    max_iterations: int | None = None
    min_sources: int | None = None
    require_archive_first: bool = True
    require_citations: bool = True


class HitlDecision(BaseModel):
    """人工复核要求。"""

    required: bool = False
    reason: str | None = None


class PolicyDecision(BaseModel):
    """策略决策。"""

    decision_id: str = Field(default_factory=generate_decision_id)
    allow: bool
    reason: str
    enforced: EnforcedPolicy = Field(default_factory=EnforcedPolicy)
    hitl: HitlDecision = Field(default_factory=HitlDecision)


@dataclass(frozen=True)
class PolicyViolation:
    """策略违规记录。"""

    request_id: str
    reason: str
