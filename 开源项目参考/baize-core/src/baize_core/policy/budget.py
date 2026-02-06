"""预算追踪器。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# 从统一异常模块导入，保持向后兼容性
from baize_core.exceptions import BudgetExhaustedError
from baize_core.schemas.policy import RuntimeBudget

# 无限制预算常量（用于无预算追踪场景）
UNLIMITED_TOKEN_BUDGET = 999_999
UNLIMITED_CALL_BUDGET = 999
UNLIMITED_DEADLINE_MS = 999_999

# 重新导出以保持向后兼容性
__all__ = [
    "UNLIMITED_TOKEN_BUDGET",
    "UNLIMITED_CALL_BUDGET",
    "UNLIMITED_DEADLINE_MS",
    "unlimited_runtime_budget",
    "BudgetExhaustedError",
    "BudgetTracker",
]


def unlimited_runtime_budget() -> RuntimeBudget:
    """创建无限制的运行时预算（用于无预算追踪场景）。

    Returns:
        无限制的运行时预算
    """
    return RuntimeBudget(
        token_budget_remaining=UNLIMITED_TOKEN_BUDGET,
        model_calls_remaining=UNLIMITED_CALL_BUDGET,
        tool_calls_remaining=UNLIMITED_CALL_BUDGET,
        deadline_ms_remaining=UNLIMITED_DEADLINE_MS,
    )


@dataclass
class BudgetTracker:
    """运行时预算追踪器。

    用于跟踪任务执行过程中的资源消耗，包括 token 预算、模型调用次数、
    工具调用次数和截止时间。
    """

    token_budget: int
    model_calls: int
    tool_calls: int
    deadline_ms: int

    _token_budget_remaining: int = field(init=False)
    _model_calls_remaining: int = field(init=False)
    _tool_calls_remaining: int = field(init=False)
    _start_time_ms: int = field(init=False)

    def __post_init__(self) -> None:
        """初始化剩余预算。"""
        self._token_budget_remaining = self.token_budget
        self._model_calls_remaining = self.model_calls
        self._tool_calls_remaining = self.tool_calls
        self._start_time_ms = int(time.time() * 1000)

    @property
    def token_budget_remaining(self) -> int:
        """剩余 token 预算。"""
        return self._token_budget_remaining

    @property
    def model_calls_remaining(self) -> int:
        """剩余模型调用次数。"""
        return self._model_calls_remaining

    @property
    def tool_calls_remaining(self) -> int:
        """剩余工具调用次数。"""
        return self._tool_calls_remaining

    @property
    def deadline_ms_remaining(self) -> int:
        """剩余截止时间（毫秒）。"""
        elapsed = int(time.time() * 1000) - self._start_time_ms
        remaining = self.deadline_ms - elapsed
        return max(0, remaining)

    def check_token_budget(self, required: int) -> None:
        """检查 token 预算是否充足。

        Args:
            required: 需要的 token 数量

        Raises:
            BudgetExhaustedError: 预算不足时抛出
        """
        if required > self._token_budget_remaining:
            raise BudgetExhaustedError(
                resource="token",
                remaining=self._token_budget_remaining,
                required=required,
            )

    def check_model_call(self) -> None:
        """检查模型调用次数是否充足。

        Raises:
            BudgetExhaustedError: 调用次数耗尽时抛出
        """
        if self._model_calls_remaining <= 0:
            raise BudgetExhaustedError(
                resource="model 调用次数",
                remaining=self._model_calls_remaining,
                required=1,
            )

    def check_tool_call(self) -> None:
        """检查工具调用次数是否充足。

        Raises:
            BudgetExhaustedError: 调用次数耗尽时抛出
        """
        if self._tool_calls_remaining <= 0:
            raise BudgetExhaustedError(
                resource="tool 调用次数",
                remaining=self._tool_calls_remaining,
                required=1,
            )

    def deduct_tokens(self, amount: int) -> None:
        """扣减 token 预算。

        Args:
            amount: 扣减数量

        Raises:
            BudgetExhaustedError: 预算不足时抛出
        """
        self.check_token_budget(amount)
        self._token_budget_remaining -= amount

    def deduct_model_call(self) -> None:
        """扣减模型调用次数。

        Raises:
            BudgetExhaustedError: 调用次数耗尽时抛出
        """
        self.check_model_call()
        self._model_calls_remaining -= 1

    def deduct_tool_call(self) -> None:
        """扣减工具调用次数。

        Raises:
            BudgetExhaustedError: 调用次数耗尽时抛出
        """
        self.check_tool_call()
        self._tool_calls_remaining -= 1

    def to_runtime_budget(self) -> RuntimeBudget:
        """导出为 RuntimeBudget 对象。

        Returns:
            当前剩余预算的 RuntimeBudget 表示
        """
        return RuntimeBudget(
            token_budget_remaining=self._token_budget_remaining,
            model_calls_remaining=self._model_calls_remaining,
            tool_calls_remaining=self._tool_calls_remaining,
            deadline_ms_remaining=self.deadline_ms_remaining,
        )
