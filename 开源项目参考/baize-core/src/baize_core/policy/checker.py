"""策略检查公共逻辑。

提供策略检查的公共方法，消除 LlmRunner 和 ToolRunner 中的重复代码。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from baize_core.exceptions import (
    HumanReviewRequiredError,
    PolicyDeniedError,
)
from baize_core.policy.budget import unlimited_runtime_budget
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyDecision,
    PolicyPayload,
    PolicyRequest,
    RuntimeBudget,
    StageType,
)
from baize_core.schemas.review_request import ReviewCreateRequest

if TYPE_CHECKING:
    from baize_core.audit.recorder import AuditRecorder
    from baize_core.policy.budget import BudgetTracker
    from baize_core.policy.engine import PolicyEngine
    from baize_core.storage.postgres import PostgresStore

# 重新导出异常类和 unlimited_runtime_budget 以便使用者从 checker 模块导入
__all__ = [
    "PolicyCheckerMixin",
    "PolicyDeniedError",
    "HumanReviewRequiredError",
    "unlimited_runtime_budget",
]


class PolicyCheckerMixin:
    """策略检查公共逻辑 Mixin。

    提供策略检查相关的公共方法，供 LlmRunner 和 ToolRunner 复用。

    要求子类提供以下属性：
    - _policy_engine: PolicyEngine
    - _recorder: AuditRecorder
    - _review_store: PostgresStore
    - _budget_tracker: BudgetTracker | None
    """

    _policy_engine: PolicyEngine
    _recorder: AuditRecorder
    _review_store: PostgresStore
    _budget_tracker: BudgetTracker | None

    def _get_runtime_budget(self) -> RuntimeBudget:
        """获取运行时预算。

        如果有预算追踪器，返回当前剩余预算；
        否则返回无限制预算。

        Returns:
            运行时预算
        """
        if self._budget_tracker is not None:
            return self._budget_tracker.to_runtime_budget()
        return unlimited_runtime_budget()

    def _build_policy_request(
        self,
        *,
        action: ActionType,
        stage: StageType,
        task_id: str,
        section_id: str | None = None,
        payload: PolicyPayload,
        planned_cost: PlannedCost,
    ) -> PolicyRequest:
        """构建策略请求。

        Args:
            action: 动作类型
            stage: 编排阶段
            task_id: 任务 ID
            section_id: 章节 ID（可选）
            payload: 策略负载
            planned_cost: 计划成本

        Returns:
            策略请求
        """
        return PolicyRequest(
            request_id=str(uuid4()),
            action=action,
            stage=stage,
            task_id=task_id,
            section_id=section_id,
            planned_cost=planned_cost,
            payload=payload,
            runtime=self._get_runtime_budget(),
        )

    async def _check_policy(
        self,
        request: PolicyRequest,
    ) -> PolicyDecision:
        """执行策略检查并记录审计。

        Args:
            request: 策略请求

        Returns:
            策略决策

        Raises:
            HumanReviewRequiredError: 需要人工复核
            PolicyDeniedError: 策略拒绝
        """
        decision = self._policy_engine.evaluate(request)
        await self._recorder.record_policy_decision(request, decision)

        if decision.hitl.required:
            await self._request_human_review(request.task_id, decision.hitl.reason)

        if not decision.allow:
            raise PolicyDeniedError(request.action, decision.reason)

        return decision

    async def _request_human_review(self, task_id: str, reason: str) -> None:
        """请求人工复核。

        Args:
            task_id: 任务 ID
            reason: 复核原因

        Raises:
            HumanReviewRequiredError: 始终抛出，表示需要人工复核
        """
        review = await self._review_store.create_review_request(
            ReviewCreateRequest(task_id=task_id, reason=reason)
        )
        raise HumanReviewRequiredError(review.review_id)
