"""路径路由测试。"""

from __future__ import annotations

from baize_core.config.settings import PolicyConfig
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.task import PathType, TaskComplexity, TaskSpec


def _build_policy_config(*, default_allow: bool) -> PolicyConfig:
    """构造策略配置。"""

    return PolicyConfig(
        allowed_models=tuple(),
        allowed_tools=tuple(),
        default_allow=default_allow,
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


class TestPathRouting:
    """路径路由测试。"""

    def test_简单任务短时间预算使用快路径(self) -> None:
        """简单任务 + 短时间预算 → 快路径。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        task = TaskSpec(
            task_id="task_001",
            objective="查询最新新闻",
            complexity=TaskComplexity.SIMPLE,
            time_budget_seconds=10,
        )

        path = engine.path_decision(task)
        assert path == PathType.FAST

    def test_复杂任务使用深路径(self) -> None:
        """复杂任务始终使用深路径。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        task = TaskSpec(
            task_id="task_002",
            objective="分析地区安全形势",
            complexity=TaskComplexity.COMPLEX,
            time_budget_seconds=600,
        )

        path = engine.path_decision(task)
        assert path == PathType.DEEP

    def test_中等复杂度长时间预算使用深路径(self) -> None:
        """中等复杂度 + 长时间预算 → 深路径。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        task = TaskSpec(
            task_id="task_003",
            objective="研究军事演习动态",
            complexity=TaskComplexity.MODERATE,
            time_budget_seconds=300,
        )

        path = engine.path_decision(task)
        assert path == PathType.DEEP

    def test_中等复杂度短时间预算使用快路径(self) -> None:
        """中等复杂度 + 短时间预算 → 快路径。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        task = TaskSpec(
            task_id="task_004",
            objective="查询舰艇位置",
            complexity=TaskComplexity.MODERATE,
            time_budget_seconds=20,
        )

        path = engine.path_decision(task)
        assert path == PathType.FAST

    def test_首选路径覆盖自动决策(self) -> None:
        """首选路径覆盖自动决策。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        # 本应使用快路径，但首选深路径
        task = TaskSpec(
            task_id="task_005",
            objective="简单查询",
            complexity=TaskComplexity.SIMPLE,
            time_budget_seconds=10,
            preferred_path=PathType.DEEP,
        )

        path = engine.path_decision(task)
        assert path == PathType.DEEP

    def test_默认时间预算使用深路径(self) -> None:
        """默认时间预算（5分钟）使用深路径。"""
        config = _build_policy_config(default_allow=True)
        engine = PolicyEngine(config)

        task = TaskSpec(
            task_id="task_006",
            objective="研究报告",
            # 使用默认值
        )

        path = engine.path_decision(task)
        assert path == PathType.DEEP
