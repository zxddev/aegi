"""审计记录器。"""

from __future__ import annotations

from baize_core.audit.sink import AuditSink
from baize_core.schemas.audit import (
    ModelTrace,
    PolicyDecisionRecord,
    ToolTrace,
    Z3ValidationTrace,
)
from baize_core.schemas.policy import PolicyDecision, PolicyRequest


class AuditRecorder:
    """审计记录器。"""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    async def record_tool_trace(self, trace: ToolTrace) -> None:
        """记录工具调用审计。"""

        await self._sink.write(trace)

    async def record_model_trace(self, trace: ModelTrace) -> None:
        """记录模型调用审计。"""

        await self._sink.write(trace)

    async def record_policy_decision(
        self, request: PolicyRequest, decision: PolicyDecision
    ) -> None:
        """记录策略决策审计。"""

        record = PolicyDecisionRecord(
            decision_id=decision.decision_id,
            request_id=request.request_id,
            action=request.action.value,
            stage=request.stage.value,
            task_id=request.task_id,
            allow=decision.allow,
            reason=decision.reason,
            enforced=decision.enforced.model_dump(),
            hitl=decision.hitl.model_dump(),
            hitl_required=decision.hitl.required,
        )
        await self._sink.write(record)

    async def record_z3_validation(self, trace: Z3ValidationTrace) -> None:
        """记录 Z3 约束校验审计。

        记录 Z3 时间线校验结果。
        """

        await self._sink.write(trace)
