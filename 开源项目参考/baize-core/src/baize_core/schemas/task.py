"""任务输入输出契约。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from baize_core.schemas.policy import SensitivityLevel


class TaskComplexity(str, Enum):
    """任务复杂度。"""

    SIMPLE = "simple"  # 简单查询，秒级响应
    MODERATE = "moderate"  # 中等复杂度，分钟级
    COMPLEX = "complex"  # 复杂分析，需要深度研究


class PathType(str, Enum):
    """执行路径类型。"""

    FAST = "fast_path"  # 快路径：ReAct 检索链，秒级
    DEEP = "deep_path"  # 深路径：OODA 状态机，分钟级


class TaskSpec(BaseModel):
    """任务规范。

    Attributes:
        task_id: 任务唯一标识
        objective: 任务目标描述
        constraints: 约束条件列表
        time_window: 时间窗口（如 "2024-01"）
        region: 地理区域
        sensitivity: 敏感级别
        complexity: 任务复杂度（用于路径选择）
        time_budget_seconds: 时间预算（秒），用于路径决策
        preferred_path: 首选路径（可选，覆盖自动决策）
        retention_days: 任务数据保留天数（可选，覆盖默认策略）
    """

    task_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    time_window: str | None = None
    region: str | None = None
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    retention_days: int | None = Field(default=None, ge=1)

    # 路径路由相关字段
    complexity: TaskComplexity = TaskComplexity.MODERATE
    time_budget_seconds: int = Field(default=300, ge=1)  # 默认 5 分钟
    preferred_path: PathType | None = None


class TaskResponse(BaseModel):
    """任务响应。"""

    task_id: str
    status: str
    message: str | None = None
    path_used: PathType | None = None
