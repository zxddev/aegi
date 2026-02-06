"""策略引擎实现。"""

from __future__ import annotations

from baize_core.config.settings import PolicyConfig
from baize_core.schemas.policy import (
    ActionType,
    EnforcedPolicy,
    HitlDecision,
    PolicyDecision,
    PolicyRequest,
    RiskLevel,
)
from baize_core.schemas.task import PathType, TaskComplexity, TaskSpec

# 快路径时间预算阈值（秒）
FAST_PATH_TIME_THRESHOLD = 30


class PolicyEngine:
    """策略引擎（deny-by-default）。

    核心职责：
    1. 检查模型/工具白名单
    2. 检查运行时预算约束（token/调用次数/超时）
    3. 返回策略决策
    4. 决定快/深路径
    """

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    def path_decision(self, task: TaskSpec) -> PathType:
        """决定任务执行路径。

        路由逻辑：
        1. 如果有首选路径，直接使用
        2. 简单任务 + 时间预算小于阈值 → 快路径
        3. 其他情况 → 深路径

        Args:
            task: 任务规范

        Returns:
            执行路径类型
        """
        # 首选路径覆盖
        if task.preferred_path is not None:
            return task.preferred_path

        # 简单任务且时间预算紧迫
        if task.complexity == TaskComplexity.SIMPLE:
            if task.time_budget_seconds < FAST_PATH_TIME_THRESHOLD:
                return PathType.FAST

        # 复杂任务始终使用深路径
        if task.complexity == TaskComplexity.COMPLEX:
            return PathType.DEEP

        # 中等复杂度根据时间预算决定
        if task.time_budget_seconds < FAST_PATH_TIME_THRESHOLD:
            return PathType.FAST

        return PathType.DEEP

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """执行策略判定。

        检查顺序：
        1. 预算检查（硬约束，超限直接拒绝）
        2. 白名单检查
        """
        # 先检查预算约束
        budget_check = self._check_budget(request)
        if budget_check is not None:
            return budget_check

        if request.action == ActionType.MODEL_CALL:
            return self._decide_model(request)
        if request.action == ActionType.TOOL_CALL:
            return self._decide_tool(request)
        return self._decide_export(request)

    def _check_budget(self, request: PolicyRequest) -> PolicyDecision | None:
        """检查运行时预算约束。

        Args:
            request: 策略请求

        Returns:
            如果预算不足返回拒绝决策，否则返回 None
        """
        if request.action == ActionType.EXPORT:
            return None
        runtime = request.runtime
        planned = request.planned_cost

        # 检查 token 预算
        if request.action == ActionType.MODEL_CALL:
            if planned.token_estimate > 0:
                if runtime.token_budget_remaining < planned.token_estimate:
                    return PolicyDecision(
                        allow=False,
                        reason=f"token 预算不足：剩余 {runtime.token_budget_remaining}，"
                        f"需要 {planned.token_estimate}",
                    )
            # 检查模型调用次数
            if runtime.model_calls_remaining <= 0:
                return PolicyDecision(
                    allow=False,
                    reason="模型调用次数已耗尽",
                )

        # 检查工具调用次数
        if request.action == ActionType.TOOL_CALL:
            if runtime.tool_calls_remaining <= 0:
                return PolicyDecision(
                    allow=False,
                    reason="工具调用次数已耗尽",
                )

        # 检查截止时间
        if runtime.deadline_ms_remaining <= 0:
            return PolicyDecision(
                allow=False,
                reason="任务已超时",
            )

        return None

    def _decide_model(self, request: PolicyRequest) -> PolicyDecision:
        """模型调用策略判定。"""
        model = request.payload.model or ""
        if model and model in self._config.allowed_models:
            return PolicyDecision(
                allow=True,
                reason="模型允许",
                enforced=self._build_enforced_policy(selected_model=model),
                hitl=self._decide_hitl(request),
            )
        if self._config.default_allow:
            return PolicyDecision(
                allow=True,
                reason="默认允许",
                enforced=self._build_enforced_policy(selected_model=model or None),
                hitl=self._decide_hitl(request),
            )
        return PolicyDecision(
            allow=False,
            reason="模型未在白名单",
            enforced=self._build_enforced_policy(),
            hitl=self._decide_hitl(request),
        )

    def _decide_tool(self, request: PolicyRequest) -> PolicyDecision:
        """工具调用策略判定。"""
        tool_name = request.payload.tool_name or ""
        if tool_name and tool_name in self._config.allowed_tools:
            return PolicyDecision(
                allow=True,
                reason="工具允许",
                enforced=self._build_enforced_policy(tool_call=True),
                hitl=self._decide_hitl(request),
            )
        if self._config.default_allow:
            return PolicyDecision(
                allow=True,
                reason="默认允许",
                enforced=self._build_enforced_policy(tool_call=True),
                hitl=self._decide_hitl(request),
            )
        return PolicyDecision(
            allow=False,
            reason="工具未在白名单",
            enforced=self._build_enforced_policy(tool_call=True),
            hitl=self._decide_hitl(request),
        )

    def _decide_export(self, request: PolicyRequest) -> PolicyDecision:
        """导出策略判定。"""
        if self._config.default_allow:
            return PolicyDecision(
                allow=True,
                reason="默认允许",
                enforced=self._build_enforced_policy(),
                hitl=self._decide_hitl(request),
            )
        return PolicyDecision(
            allow=False,
            reason="导出需要显式授权",
            enforced=self._build_enforced_policy(),
            hitl=self._decide_hitl(request),
        )

    def _build_enforced_policy(
        self,
        *,
        selected_model: str | None = None,
        tool_call: bool = False,
    ) -> EnforcedPolicy:
        """构造强制约束输出。"""

        enforced = EnforcedPolicy(
            selected_model=selected_model,
            require_archive_first=self._config.require_archive_first,
            require_citations=self._config.require_citations,
        )
        if tool_call:
            enforced.timeout_ms = self._config.enforced_timeout_ms
            enforced.max_pages = self._config.enforced_max_pages
            enforced.max_iterations = self._config.enforced_max_iterations
            enforced.min_sources = self._config.enforced_min_sources
            enforced.max_concurrency = self._config.enforced_max_concurrency
        return enforced

    def _decide_hitl(self, request: PolicyRequest) -> HitlDecision:
        """根据风险等级决定是否需要人工复核。"""

        risk_level = self._resolve_risk_level(request)
        if risk_level in self._config.hitl_risk_levels:
            return HitlDecision(required=True, reason="风险等级触发人工复核")
        return HitlDecision(required=False)

    def _resolve_risk_level(self, request: PolicyRequest) -> RiskLevel:
        """解析最终风险等级。"""

        risk_level = request.risk_level
        tool_name = request.payload.tool_name or ""
        override = self._config.tool_risk_levels.get(tool_name)
        if override is None:
            return risk_level
        return self._max_risk_level(risk_level, override)

    @staticmethod
    def _max_risk_level(left: RiskLevel, right: RiskLevel) -> RiskLevel:
        """取更高风险等级。"""

        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
        }
        return left if order[left] >= order[right] else right
