"""OpenSearch 审计落地。

将审计事件写入 OpenSearch 以支持全文搜索和聚合分析。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.storage.opensearch_store import OpenSearchStore

logger = logging.getLogger(__name__)


class OpenSearchAuditSink:
    """OpenSearch 审计落地实现。

    实现 AuditSink 协议，将审计记录写入 OpenSearch。
    """

    def __init__(self, store: OpenSearchStore) -> None:
        """初始化 OpenSearch 审计 sink。

        Args:
            store: OpenSearch 存储实例
        """
        self._store = store

    async def write(self, record: BaseModel) -> None:
        """写入审计记录到 OpenSearch。

        根据记录类型映射到对应的事件类型。
        """
        if isinstance(record, ToolTrace):
            await self._write_tool_trace(record)
        elif isinstance(record, ModelTrace):
            await self._write_model_trace(record)
        elif isinstance(record, PolicyDecisionRecord):
            await self._write_policy_decision(record)
        else:
            # 通用记录
            await self._write_generic(record)

    async def _write_tool_trace(self, trace: ToolTrace) -> None:
        """写入工具调用审计。"""
        await self._store.index_audit_event(
            event_id=f"tool_{trace.trace_id}",
            event_type="tool_call",
            timestamp=trace.started_at,
            task_id=trace.task_id,
            trace_id=trace.trace_id,
            tool_name=trace.tool_name,
            model_name=None,
            success=trace.success,
            duration_ms=trace.duration_ms,
            error_type=trace.error_type,
            error_message=trace.error_message,
            output_ref=trace.result_ref,
            metadata={
                "policy_decision_id": trace.policy_decision_id,
            },
        )

    async def _write_model_trace(self, trace: ModelTrace) -> None:
        """写入模型调用审计。"""
        await self._store.index_audit_event(
            event_id=f"model_{trace.trace_id}",
            event_type="model_call",
            timestamp=trace.started_at,
            task_id=trace.task_id,
            trace_id=trace.trace_id,
            tool_name=None,
            model_name=trace.model,
            success=trace.success,
            duration_ms=trace.duration_ms,
            error_type=trace.error_type,
            error_message=trace.error_message,
            output_ref=trace.result_ref,
            metadata={
                "stage": trace.stage,
                "policy_decision_id": trace.policy_decision_id,
            },
        )

    async def _write_policy_decision(self, decision: PolicyDecisionRecord) -> None:
        """写入策略决策审计。"""
        await self._store.index_audit_event(
            event_id=f"policy_{decision.decision_id}",
            event_type="policy_decision",
            timestamp=decision.created_at,
            task_id=decision.task_id,
            trace_id=decision.request_id,
            tool_name=None,
            model_name=None,
            success=decision.allow,
            duration_ms=None,
            error_type=None,
            error_message=decision.reason if not decision.allow else None,
            metadata={
                "enforced": decision.enforced,
                "hitl": decision.hitl,
            },
        )

    async def _write_generic(self, record: BaseModel) -> None:
        """写入通用记录。"""
        data = record.model_dump(mode="json")
        await self._store.index_audit_event(
            event_id=f"generic_{uuid4().hex}",
            event_type="generic",
            timestamp=datetime.now(UTC),
            metadata=data,
        )


class CompositeAuditSink:
    """组合审计落地。

    将审计记录同时写入多个 sink。
    """

    def __init__(self, sinks: list[Any]) -> None:
        """初始化组合 sink。

        Args:
            sinks: sink 列表，每个都应实现 AuditSink 协议
        """
        self._sinks = sinks

    async def write(self, record: BaseModel) -> None:
        """写入审计记录到所有 sink。

        任一 sink 失败会记录警告但不中断其他 sink。
        """
        for sink in self._sinks:
            try:
                await sink.write(record)
            except Exception as e:
                logger.warning("审计写入失败 (%s): %s", type(sink).__name__, e)
