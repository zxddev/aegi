from __future__ import annotations

from baize_core.config.settings import PolicyConfig
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyPayload,
    PolicyRequest,
    RuntimeBudget,
    StageType,
)


def _build_policy_config(
    *, allowed_tools: tuple[str, ...], allowed_models: tuple[str, ...] = ()
) -> PolicyConfig:
    """构造策略配置。"""

    return PolicyConfig(
        allowed_models=allowed_models,
        allowed_tools=allowed_tools,
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


def test_policy_engine_denies_unknown_tool() -> None:
    config = _build_policy_config(allowed_tools=("known",))
    engine = PolicyEngine(config)
    request = PolicyRequest(
        request_id="req-1",
        action=ActionType.TOOL_CALL,
        stage=StageType.OBSERVE,
        task_id="task-1",
        planned_cost=PlannedCost(token_estimate=0, tool_timeout_ms=0),
        payload=PolicyPayload(tool_name="unknown", tool_input={}),
        runtime=RuntimeBudget(
            token_budget_remaining=1000,
            model_calls_remaining=10,
            tool_calls_remaining=10,
            deadline_ms_remaining=60000,
        ),
    )
    decision = engine.evaluate(request)
    assert decision.allow is False
    assert "白名单" in decision.reason
