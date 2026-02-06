"""约束类型与基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConstraintType(Enum):
    """约束类型。"""

    TIMELINE = "timeline"  # 时间线约束
    MUTEX = "mutex"  # 互斥约束
    IMPLICATION = "implication"  # 蕴含约束
    RANGE = "range"  # 范围约束


class ValidationResult(Enum):
    """校验结果。"""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass
class ConstraintViolation:
    """约束违反记录。"""

    constraint_type: ConstraintType
    message: str
    evidence: list[str] = field(default_factory=list)
    severity: str = "error"  # error, warning


@dataclass
class ValidationReport:
    """校验报告。"""

    result: ValidationResult
    violations: list[ConstraintViolation]
    checked_constraints: int
    passed_constraints: int

    @property
    def is_valid(self) -> bool:
        """是否通过校验。"""
        return self.result == ValidationResult.VALID


@dataclass
class TimelineEvent:
    """时间线事件。"""

    event_id: str
    timestamp: datetime
    description: str
    entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    time_end: datetime | None = None  # 事件结束时间（可选）
    event_type: str = ""  # 事件类型（用于因果关系检查）
    state: str = ""  # 实体状态（用于互斥检查）


@dataclass
class CausalityRule:
    """因果关系规则。

    表示 cause_type 事件必须早于 effect_type 事件。
    """

    cause_type: str
    effect_type: str
    description: str = ""


@dataclass
class MutexState:
    """互斥状态规则。

    表示 state_a 和 state_b 不能同时为真。
    """

    state_a: str
    state_b: str
    entity_type: str = ""  # 适用的实体类型


# 预定义的因果关系规则（按军事领域知识）
DEFAULT_CAUSALITY_RULES = [
    CausalityRule(
        cause_type="deployment",
        effect_type="combat",
        description="部署事件必须早于作战事件",
    ),
    CausalityRule(
        cause_type="mobilization",
        effect_type="deployment",
        description="动员事件必须早于部署事件",
    ),
    CausalityRule(
        cause_type="procurement",
        effect_type="deployment",
        description="采购事件必须早于部署事件",
    ),
    CausalityRule(
        cause_type="training",
        effect_type="combat",
        description="训练事件必须早于作战事件",
    ),
]

# 预定义的互斥状态规则
DEFAULT_MUTEX_STATES = [
    MutexState(
        state_a="destroyed",
        state_b="operational",
        entity_type="equipment",
    ),
    MutexState(
        state_a="retreating",
        state_b="advancing",
        entity_type="unit",
    ),
    MutexState(
        state_a="captured",
        state_b="operational",
        entity_type="facility",
    ),
]


class ConstraintValidator(ABC):
    """约束校验器抽象基类。"""

    @abstractmethod
    def validate(self, data: Any) -> ValidationReport:
        """执行校验。"""
