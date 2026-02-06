"""数据库审计落地。"""

from __future__ import annotations

from pydantic import BaseModel

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.storage.postgres import PostgresStore


class DbAuditSink:
    """数据库审计落地。"""

    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    async def write(self, record: BaseModel) -> None:
        """写入审计记录。"""

        if isinstance(record, ToolTrace):
            await self._store.record_tool_trace(record)
            return
        if isinstance(record, ModelTrace):
            await self._store.record_model_trace(record)
            return
        if isinstance(record, PolicyDecisionRecord):
            await self._store.record_policy_decision(record)
            return
        raise ValueError(f"不支持的审计记录类型: {type(record).__name__}")
