"""审计回放服务测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from baize_core.replay.service import ReplayService


class TestReplayService:
    """ReplayService 单元测试。"""

    @pytest.fixture
    def mock_store(self) -> MagicMock:
        """创建模拟存储。"""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_replay_task_返回完整审计链路(self, mock_store: MagicMock) -> None:
        """测试 replay_task 返回完整审计链路。"""
        # 模拟数据库查询结果
        mock_report = MagicMock()
        mock_report.report_uid = "rpt_1"
        mock_report.task_id = "task_1"
        mock_report.outline_uid = "outline_1"
        mock_report.report_type = "strategic"
        mock_report.content_ref = "minio://bucket/report"
        mock_report.conflict_notes = None

        mock_tool_trace = MagicMock()
        mock_tool_trace.trace_id = "trace_tool_1"
        mock_tool_trace.tool_name = "meta_search"
        mock_tool_trace.task_id = "task_1"
        mock_tool_trace.started_at = datetime.now(UTC)
        mock_tool_trace.duration_ms = 100
        mock_tool_trace.success = True
        mock_tool_trace.error_type = None
        mock_tool_trace.error_message = None
        mock_tool_trace.result_ref = None
        mock_tool_trace.policy_decision_id = "pd_1"

        mock_policy_decision = MagicMock()
        mock_policy_decision.decision_id = "pd_1"
        mock_policy_decision.request_id = "req_1"
        mock_policy_decision.task_id = "task_1"
        mock_policy_decision.allow = True
        mock_policy_decision.action = "tool_call"
        mock_policy_decision.stage = "observe"
        mock_policy_decision.reason = "允许执行"
        mock_policy_decision.enforced = {}
        mock_policy_decision.hitl = {}
        mock_policy_decision.created_at = datetime.now(UTC)

        mock_model_trace = MagicMock()
        mock_model_trace.trace_id = "trace_model_1"
        mock_model_trace.model = "gpt-4"
        mock_model_trace.stage = "observe"
        mock_model_trace.task_id = "task_1"
        mock_model_trace.started_at = datetime.now(UTC)
        mock_model_trace.duration_ms = 500
        mock_model_trace.success = True
        mock_model_trace.error_type = None
        mock_model_trace.error_message = None
        mock_model_trace.result_ref = "摘要..."
        mock_model_trace.policy_decision_id = "pd_2"

        # 设置模拟会话
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # 模拟不同查询的返回结果
        reports_result = MagicMock()
        reports_result.scalars.return_value.all.return_value = [mock_report]

        references_result = MagicMock()
        references_result.scalars.return_value.all.return_value = []

        tool_traces_result = MagicMock()
        tool_traces_result.scalars.return_value.all.return_value = [mock_tool_trace]

        policy_decisions_result = MagicMock()
        policy_decisions_result.scalars.return_value.all.return_value = [
            mock_policy_decision
        ]

        model_traces_result = MagicMock()
        model_traces_result.scalars.return_value.all.return_value = [mock_model_trace]

        # 每次调用 execute 返回不同结果
        execute_results = [
            reports_result,  # _load_reports 第一次查询
            references_result,  # _load_reports 第二次查询
            tool_traces_result,  # _load_tool_traces
            policy_decisions_result,  # _load_policy_decisions
            model_traces_result,  # _load_model_traces
        ]
        mock_session.execute = AsyncMock(side_effect=execute_results)

        mock_store.session_factory.return_value = mock_session

        service = ReplayService(store=mock_store)
        result = await service.replay_task("task_1")

        # 验证结果结构
        assert result["task_id"] == "task_1"
        assert len(result["reports"]) == 1
        assert len(result["tool_traces"]) == 1
        assert len(result["policy_decisions"]) == 1
        assert len(result["model_traces"]) == 1

    @pytest.mark.asyncio
    async def test_replay_task_无数据返回空列表(self, mock_store: MagicMock) -> None:
        """测试 replay_task 无数据时返回空列表。"""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=empty_result)

        mock_store.session_factory.return_value = mock_session

        service = ReplayService(store=mock_store)
        result = await service.replay_task("nonexistent_task")

        assert result["task_id"] == "nonexistent_task"
        assert result["reports"] == []
        assert result["tool_traces"] == []
        assert result["policy_decisions"] == []
        assert result["model_traces"] == []
