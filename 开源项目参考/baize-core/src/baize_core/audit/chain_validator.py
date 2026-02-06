"""审计链路完整性校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from baize_core.schemas.audit import ToolTrace
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.mcp_client import McpClient


@dataclass(frozen=True)
class ChainIssue:
    """审计链路问题。"""

    trace_id: str
    issue: str
    detail: str | None = None


@dataclass(frozen=True)
class ChainTraceReport:
    """单条工具调用的链路校验结果。"""

    trace_id: str
    local_tool_trace: ToolTrace
    gateway_tool_trace: dict[str, Any] | None
    ok: bool
    issues: tuple[ChainIssue, ...]


@dataclass(frozen=True)
class ChainValidationResult:
    """按 task_id 生成的链路完整性报告。"""

    task_id: str
    total_traces: int
    matched_gateway_traces: int
    broken_traces: int
    ok: bool
    issues: tuple[ChainIssue, ...]
    traces: tuple[ChainTraceReport, ...]


class AuditChainValidator:
    """审计链路完整性校验器。"""

    def __init__(self, store: PostgresStore, mcp_client: McpClient) -> None:
        self._store = store
        self._mcp_client = mcp_client

    async def validate_chain(self, task_id: str) -> ChainValidationResult:
        """校验任务的审计链路是否闭合。"""

        return await self.validate_task(task_id)

    async def validate_task(self, task_id: str) -> ChainValidationResult:
        """按 task_id 生成审计链路完整性报告。"""

        tool_traces = await self._store.list_tool_traces_by_task(task_id)
        issues: list[ChainIssue] = []
        trace_reports: list[ChainTraceReport] = []
        matched_gateway_traces = 0
        broken_traces = 0

        for trace in tool_traces:
            trace_issues: list[ChainIssue] = []
            if not trace.policy_decision_id:
                trace_issues.append(
                    ChainIssue(
                        trace_id=trace.trace_id,
                        issue="missing_policy_decision",
                        detail="baize-core tool_trace 缺少 policy_decision_id",
                    )
                )

            gateway_trace = await self._mcp_client.get_audit_tool_trace(trace.trace_id)
            if gateway_trace is None:
                trace_issues.append(
                    ChainIssue(
                        trace_id=trace.trace_id,
                        issue="missing_gateway_trace",
                        detail="MCP Gateway 未找到对应 trace_id",
                    )
                )
            else:
                matched_gateway_traces += 1
                expected_decision = trace.policy_decision_id
                gateway_decision = gateway_trace.get("policy_decision_id")
                gateway_caller_decision = gateway_trace.get("caller_policy_decision_id")

                if expected_decision:
                    if gateway_decision and gateway_decision != expected_decision:
                        trace_issues.append(
                            ChainIssue(
                                trace_id=trace.trace_id,
                                issue="policy_decision_mismatch",
                                detail=(
                                    f"baize-core={expected_decision}, "
                                    f"gateway.policy_decision_id={gateway_decision}"
                                ),
                            )
                        )
                    if (
                        gateway_caller_decision
                        and gateway_caller_decision != expected_decision
                    ):
                        trace_issues.append(
                            ChainIssue(
                                trace_id=trace.trace_id,
                                issue="caller_policy_decision_mismatch",
                                detail=(
                                    f"baize-core={expected_decision}, "
                                    f"gateway.caller_policy_decision_id={gateway_caller_decision}"
                                ),
                            )
                        )
                    if not gateway_decision and not gateway_caller_decision:
                        trace_issues.append(
                            ChainIssue(
                                trace_id=trace.trace_id,
                                issue="missing_gateway_policy_decision",
                                detail="MCP Gateway 审计记录缺少 policy_decision_id/caller_policy_decision_id",
                            )
                        )

                gateway_caller_trace_id = gateway_trace.get("caller_trace_id")
                if (
                    gateway_caller_trace_id
                    and gateway_caller_trace_id != trace.trace_id
                ):
                    trace_issues.append(
                        ChainIssue(
                            trace_id=trace.trace_id,
                            issue="caller_trace_mismatch",
                            detail=(
                                f"baize-core={trace.trace_id}, "
                                f"gateway.caller_trace_id={gateway_caller_trace_id}"
                            ),
                        )
                    )

            if trace_issues:
                broken_traces += 1
                issues.extend(trace_issues)
            trace_reports.append(
                ChainTraceReport(
                    trace_id=trace.trace_id,
                    local_tool_trace=trace,
                    gateway_tool_trace=gateway_trace,
                    ok=not trace_issues,
                    issues=tuple(trace_issues),
                )
            )

        return ChainValidationResult(
            task_id=task_id,
            total_traces=len(tool_traces),
            matched_gateway_traces=matched_gateway_traces,
            broken_traces=broken_traces,
            ok=not issues,
            issues=tuple(issues),
            traces=tuple(trace_reports),
        )
