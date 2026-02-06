"""OpenSearch 审计 Sink 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from baize_core.audit.opensearch_sink import CompositeAuditSink, OpenSearchAuditSink
from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.storage.opensearch_store import OpenSearchStore


@pytest.fixture
def mock_store() -> AsyncMock:
    """Mock OpenSearch store。"""
    store = AsyncMock(spec=OpenSearchStore)
    store.index_audit_event = AsyncMock()
    return store


class TestOpenSearchAuditSink:
    """OpenSearchAuditSink 测试。"""

    @pytest.mark.asyncio
    async def test_write_tool_trace(self, mock_store: AsyncMock) -> None:
        """测试写入工具调用审计。"""
        sink = OpenSearchAuditSink(mock_store)
        trace = ToolTrace(
            trace_id="trace_123",
            tool_name="web_crawl",
            task_id="task_456",
            started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            duration_ms=500,
            success=True,
            result_ref="output/result.json",
        )
        await sink.write(trace)
        mock_store.index_audit_event.assert_called_once()
        call_kwargs = mock_store.index_audit_event.call_args[1]
        assert call_kwargs["event_id"] == "tool_trace_123"
        assert call_kwargs["event_type"] == "tool_call"
        assert call_kwargs["tool_name"] == "web_crawl"
        assert call_kwargs["task_id"] == "task_456"
        assert call_kwargs["success"] is True
        assert call_kwargs["duration_ms"] == 500

    @pytest.mark.asyncio
    async def test_write_model_trace(self, mock_store: AsyncMock) -> None:
        """测试写入模型调用审计。"""
        sink = OpenSearchAuditSink(mock_store)
        trace = ModelTrace(
            trace_id="trace_789",
            model="gpt-4",
            stage="orient",
            task_id="task_456",
            started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            duration_ms=1200,
            success=True,
        )
        await sink.write(trace)
        mock_store.index_audit_event.assert_called_once()
        call_kwargs = mock_store.index_audit_event.call_args[1]
        assert call_kwargs["event_id"] == "model_trace_789"
        assert call_kwargs["event_type"] == "model_call"
        assert call_kwargs["model_name"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_write_policy_decision(self, mock_store: AsyncMock) -> None:
        """测试写入策略决策审计。"""
        sink = OpenSearchAuditSink(mock_store)
        decision = PolicyDecisionRecord(
            decision_id="dec_123",
            request_id="req_456",
            task_id="task_789",
            allow=True,
            reason="策略允许",
            enforced={"timeout_ms": 30000},
            hitl={"required": False},
            created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )
        await sink.write(decision)
        mock_store.index_audit_event.assert_called_once()
        call_kwargs = mock_store.index_audit_event.call_args[1]
        assert call_kwargs["event_id"] == "policy_dec_123"
        assert call_kwargs["event_type"] == "policy_decision"
        assert call_kwargs["success"] is True


class TestCompositeAuditSink:
    """CompositeAuditSink 测试。"""

    @pytest.mark.asyncio
    async def test_write_to_all_sinks(self) -> None:
        """测试写入所有 sink。"""
        sink1 = AsyncMock()
        sink2 = AsyncMock()
        composite = CompositeAuditSink([sink1, sink2])
        trace = ToolTrace(
            trace_id="trace_1",
            tool_name="test_tool",
        )
        await composite.write(trace)
        sink1.write.assert_called_once_with(trace)
        sink2.write.assert_called_once_with(trace)

    @pytest.mark.asyncio
    async def test_continues_on_sink_failure(self) -> None:
        """测试单个 sink 失败不影响其他。"""
        sink1 = AsyncMock()
        sink1.write = AsyncMock(side_effect=Exception("Sink 1 failed"))
        sink2 = AsyncMock()
        composite = CompositeAuditSink([sink1, sink2])
        trace = ToolTrace(
            trace_id="trace_1",
            tool_name="test_tool",
        )
        # 不应抛出异常
        await composite.write(trace)
        # sink2 仍然被调用
        sink2.write.assert_called_once_with(trace)
