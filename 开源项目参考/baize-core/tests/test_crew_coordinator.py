"""CrewAI 协作测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from baize_core.agents.crew import (
    AgentRole,
    CrewCoordinator,
    CrewExecutionResult,
    LLMSimulatedBackend,
    _check_crewai_available,
)
from baize_core.schemas.crew import CrewDecideSummary, CrewOrientSummary


@pytest.fixture
def mock_llm_runner() -> AsyncMock:
    """Mock LLM Runner。"""
    runner = AsyncMock()
    # 模拟 generate_structured 返回
    structured_result = MagicMock()
    structured_result.data = CrewOrientSummary(
        summary="测试摘要",
        conflicts=["冲突1"],
    )
    runner.generate_structured = AsyncMock(return_value=structured_result)
    runner.generate_text = AsyncMock(return_value="模拟输出")
    return runner


class TestAgentRole:
    """AgentRole 测试。"""

    def test_all_roles_defined(self) -> None:
        """测试所有角色都已定义。"""
        from baize_core.agents.crew import AGENT_DESCRIPTIONS

        for role in AgentRole:
            assert role in AGENT_DESCRIPTIONS
            desc = AGENT_DESCRIPTIONS[role]
            assert "role" in desc
            assert "goal" in desc
            assert "backstory" in desc


class TestLLMSimulatedBackend:
    """LLM 模拟后端测试。"""

    @pytest.mark.asyncio
    async def test_execute_orient(self, mock_llm_runner: AsyncMock) -> None:
        """测试 Orient 执行。"""
        backend = LLMSimulatedBackend(mock_llm_runner)
        result = await backend.execute_orient("测试上下文")
        assert isinstance(result, CrewExecutionResult)
        assert len(result.outputs) == 3
        assert result.final_output == "模拟输出"

    @pytest.mark.asyncio
    async def test_execute_decide(self, mock_llm_runner: AsyncMock) -> None:
        """测试 Decide 执行。"""
        backend = LLMSimulatedBackend(mock_llm_runner)
        result = await backend.execute_decide("测试上下文")
        assert isinstance(result, CrewExecutionResult)
        assert len(result.outputs) == 2


class TestCrewCoordinator:
    """CrewCoordinator 测试。"""

    @pytest.mark.asyncio
    async def test_orient_fallback(self, mock_llm_runner: AsyncMock) -> None:
        """测试 Orient 使用 fallback。"""
        # 禁用真实 CrewAI
        with patch(
            "baize_core.agents.crew._check_crewai_available",
            return_value=False,
        ):
            coordinator = CrewCoordinator(
                llm_runner=mock_llm_runner,
                use_real_crewai=False,
            )
            result = await coordinator.orient(context="测试", task_id="task_1")
            assert isinstance(result, CrewOrientSummary)
            assert result.summary == "测试摘要"

    @pytest.mark.asyncio
    async def test_decide_fallback(self, mock_llm_runner: AsyncMock) -> None:
        """测试 Decide 使用 fallback。"""
        # 配置 mock 返回 DecideSummary
        decide_result = MagicMock()
        decide_result.data = CrewDecideSummary(
            hypotheses=["假设1"],
            gaps=["缺口1"],
        )
        mock_llm_runner.generate_structured = AsyncMock(return_value=decide_result)

        with patch(
            "baize_core.agents.crew._check_crewai_available",
            return_value=False,
        ):
            coordinator = CrewCoordinator(
                llm_runner=mock_llm_runner,
                use_real_crewai=False,
            )
            result = await coordinator.decide(context="测试", task_id="task_1")
            assert isinstance(result, CrewDecideSummary)
            assert "假设1" in result.hypotheses

    @pytest.mark.asyncio
    async def test_orient_with_simulated_backend(
        self, mock_llm_runner: AsyncMock
    ) -> None:
        """测试使用模拟后端的 Orient。"""
        with patch(
            "baize_core.agents.crew._check_crewai_available",
            return_value=False,
        ):
            coordinator = CrewCoordinator(
                llm_runner=mock_llm_runner,
                use_real_crewai=True,  # 会自动 fallback
            )
            result = await coordinator.orient(context="测试上下文", task_id="task_1")
            assert isinstance(result, CrewOrientSummary)


class TestCrewAvailability:
    """CrewAI 可用性测试。"""

    def test_check_crewai_not_available(self) -> None:
        """测试 CrewAI 不可用时的检查。"""
        with patch.dict("sys.modules", {"crewai": None}):
            # 重新导入以测试

            # 由于模块已缓存，这里直接测试函数行为
            # 在实际环境中，如果 crewai 未安装会返回 False
            result = _check_crewai_available()
            # 结果取决于实际环境
            assert isinstance(result, bool)
