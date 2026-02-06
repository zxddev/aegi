"""预算扣减测试。"""

from __future__ import annotations

import pytest

from baize_core.config.settings import PolicyConfig
from baize_core.policy.budget import BudgetExhaustedError, BudgetTracker
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyPayload,
    PolicyRequest,
    RuntimeBudget,
    StageType,
)


class TestBudgetTracker:
    """BudgetTracker 单元测试。"""

    def test_初始化预算(self) -> None:
        """测试初始化预算。"""
        tracker = BudgetTracker(
            token_budget=10000,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        assert tracker.token_budget_remaining == 10000
        assert tracker.model_calls_remaining == 10
        assert tracker.tool_calls_remaining == 50

    def test_扣减token预算(self) -> None:
        """测试扣减 token 预算。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        tracker.deduct_tokens(300)
        assert tracker.token_budget_remaining == 700

    def test_扣减模型调用次数(self) -> None:
        """测试扣减模型调用次数。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        tracker.deduct_model_call()
        assert tracker.model_calls_remaining == 9

    def test_扣减工具调用次数(self) -> None:
        """测试扣减工具调用次数。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        tracker.deduct_tool_call()
        assert tracker.tool_calls_remaining == 49

    def test_token预算耗尽抛出异常(self) -> None:
        """测试 token 预算耗尽时抛出异常。"""
        tracker = BudgetTracker(
            token_budget=100,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        with pytest.raises(BudgetExhaustedError) as exc_info:
            tracker.deduct_tokens(200)
        assert "token" in str(exc_info.value).lower()

    def test_模型调用次数耗尽抛出异常(self) -> None:
        """测试模型调用次数耗尽时抛出异常。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=1,
            tool_calls=50,
            deadline_ms=60000,
        )
        tracker.deduct_model_call()
        with pytest.raises(BudgetExhaustedError) as exc_info:
            tracker.deduct_model_call()
        assert "model" in str(exc_info.value).lower()

    def test_工具调用次数耗尽抛出异常(self) -> None:
        """测试工具调用次数耗尽时抛出异常。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=10,
            tool_calls=1,
            deadline_ms=60000,
        )
        tracker.deduct_tool_call()
        with pytest.raises(BudgetExhaustedError) as exc_info:
            tracker.deduct_tool_call()
        assert "tool" in str(exc_info.value).lower()

    def test_导出运行时预算(self) -> None:
        """测试导出为 RuntimeBudget。"""
        tracker = BudgetTracker(
            token_budget=1000,
            model_calls=10,
            tool_calls=50,
            deadline_ms=60000,
        )
        runtime = tracker.to_runtime_budget()
        assert runtime.token_budget_remaining == 1000
        assert runtime.model_calls_remaining == 10
        assert runtime.tool_calls_remaining == 50


class TestPolicyEngineBudgetCheck:
    """PolicyEngine 预算检查测试。"""

    @staticmethod
    def _build_policy_config() -> PolicyConfig:
        """构造策略配置。"""

        return PolicyConfig(
            allowed_models=("test-model",),
            allowed_tools=("test-tool",),
            default_allow=False,
            enforced_timeout_ms=30000,
            enforced_max_pages=20,
            enforced_max_iterations=3,
            enforced_min_sources=3,
            enforced_max_concurrency=5,
            require_archive_first=True,
            require_citations=True,
            hitl_risk_levels=tuple(),
            tool_risk_levels={},
        )

    def test_预算充足时允许调用(self) -> None:
        """测试预算充足时策略允许。"""
        config = self._build_policy_config()
        engine = PolicyEngine(config)
        request = PolicyRequest(
            request_id="req_001",
            action=ActionType.MODEL_CALL,
            stage=StageType.OBSERVE,
            task_id="task_001",
            planned_cost=PlannedCost(token_estimate=100, tool_timeout_ms=0),
            payload=PolicyPayload(model="test-model"),
            runtime=RuntimeBudget(
                token_budget_remaining=1000,
                model_calls_remaining=10,
                tool_calls_remaining=50,
                deadline_ms_remaining=60000,
            ),
        )
        decision = engine.evaluate(request)
        assert decision.allow is True

    def test_token预算不足时拒绝调用(self) -> None:
        """测试 token 预算不足时策略拒绝。"""
        config = self._build_policy_config()
        engine = PolicyEngine(config)
        request = PolicyRequest(
            request_id="req_001",
            action=ActionType.MODEL_CALL,
            stage=StageType.OBSERVE,
            task_id="task_001",
            planned_cost=PlannedCost(token_estimate=2000, tool_timeout_ms=0),
            payload=PolicyPayload(model="test-model"),
            runtime=RuntimeBudget(
                token_budget_remaining=100,
                model_calls_remaining=10,
                tool_calls_remaining=50,
                deadline_ms_remaining=60000,
            ),
        )
        decision = engine.evaluate(request)
        assert decision.allow is False
        assert "token" in decision.reason.lower() or "预算" in decision.reason

    def test_模型调用次数不足时拒绝(self) -> None:
        """测试模型调用次数不足时策略拒绝。"""
        config = self._build_policy_config()
        engine = PolicyEngine(config)
        request = PolicyRequest(
            request_id="req_001",
            action=ActionType.MODEL_CALL,
            stage=StageType.OBSERVE,
            task_id="task_001",
            planned_cost=PlannedCost(token_estimate=100, tool_timeout_ms=0),
            payload=PolicyPayload(model="test-model"),
            runtime=RuntimeBudget(
                token_budget_remaining=1000,
                model_calls_remaining=0,
                tool_calls_remaining=50,
                deadline_ms_remaining=60000,
            ),
        )
        decision = engine.evaluate(request)
        assert decision.allow is False
        assert "调用" in decision.reason or "次数" in decision.reason

    def test_工具调用次数不足时拒绝(self) -> None:
        """测试工具调用次数不足时策略拒绝。"""
        config = self._build_policy_config()
        engine = PolicyEngine(config)
        request = PolicyRequest(
            request_id="req_001",
            action=ActionType.TOOL_CALL,
            stage=StageType.OBSERVE,
            task_id="task_001",
            planned_cost=PlannedCost(token_estimate=0, tool_timeout_ms=5000),
            payload=PolicyPayload(tool_name="test-tool"),
            runtime=RuntimeBudget(
                token_budget_remaining=1000,
                model_calls_remaining=10,
                tool_calls_remaining=0,
                deadline_ms_remaining=60000,
            ),
        )
        decision = engine.evaluate(request)
        assert decision.allow is False
        assert "工具" in decision.reason or "调用" in decision.reason
