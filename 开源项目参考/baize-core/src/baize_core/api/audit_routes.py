"""Audit chain query & integrity-check routes.

This module exists to make the audit-chain API testable with dependency injection,
without requiring full AppConfig / Orchestrator wiring in tests.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException

from baize_core.api.models import (
    AuditDecisionChainResponse,
    AuditIntegrityCheckRequest,
    AuditIntegrityCheckResponse,
    AuditIntegrityIssue,
    AuditIntegrityTraceReport,
    AuditTraceChainResponse,
    GatewayToolTrace,
)
from baize_core.audit.chain_validator import AuditChainValidator
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.mcp_client import McpClient


def register_audit_chain_routes(
    app: FastAPI,
    *,
    store: PostgresStore,
    mcp_audit_client: McpClient,
) -> AuditChainValidator:
    """注册审计链路相关 API。"""

    chain_validator = AuditChainValidator(store, mcp_audit_client)

    @app.get("/audit/traces/{trace_id}", response_model=AuditTraceChainResponse)
    async def get_trace_chain(trace_id: str) -> AuditTraceChainResponse:
        """获取跨服务的审计链路。"""

        local_trace = await store.get_tool_trace(trace_id)
        gateway_raw = await mcp_audit_client.get_audit_tool_trace(trace_id)
        gateway_trace = (
            GatewayToolTrace(**cast(dict[str, Any], gateway_raw))
            if gateway_raw is not None
            else None
        )
        if local_trace is None and gateway_trace is None:
            raise HTTPException(status_code=404, detail="审计链路不存在")
        return AuditTraceChainResponse(
            trace_id=trace_id,
            local_tool_trace=local_trace,
            gateway_tool_trace=gateway_trace,
        )

    @app.get(
        "/audit/decisions/{decision_id}",
        response_model=AuditDecisionChainResponse,
    )
    async def get_decision_chain(decision_id: str) -> AuditDecisionChainResponse:
        """按策略决策 ID 查询审计链路。"""

        local_traces = await store.query_tool_traces_by_policy_decision_id(decision_id)
        gateway_raw = await mcp_audit_client.get_audit_traces_by_decision(decision_id)
        gateway_traces = [
            GatewayToolTrace(**cast(dict[str, Any], item)) for item in gateway_raw
        ]
        if not local_traces and not gateway_traces:
            raise HTTPException(status_code=404, detail="审计链路不存在")
        return AuditDecisionChainResponse(
            decision_id=decision_id,
            local_tool_traces=local_traces,
            gateway_tool_traces=gateway_traces,
        )

    @app.post(
        "/audit/integrity-check",
        response_model=AuditIntegrityCheckResponse,
    )
    async def check_audit_integrity(
        payload: AuditIntegrityCheckRequest,
    ) -> AuditIntegrityCheckResponse:
        """审计链路完整性校验。"""

        result = await chain_validator.validate_task(payload.task_id)
        return AuditIntegrityCheckResponse(
            task_id=result.task_id,
            total_traces=result.total_traces,
            matched_gateway_traces=result.matched_gateway_traces,
            broken_traces=result.broken_traces,
            ok=result.ok,
            issues=[
                AuditIntegrityIssue(
                    trace_id=issue.trace_id,
                    issue=issue.issue,
                    detail=issue.detail,
                )
                for issue in result.issues
            ],
            traces=[
                AuditIntegrityTraceReport(
                    trace_id=trace.trace_id,
                    local_tool_trace=trace.local_tool_trace,
                    gateway_tool_trace=(
                        GatewayToolTrace(**trace.gateway_tool_trace)
                        if trace.gateway_tool_trace is not None
                        else None
                    ),
                    ok=trace.ok,
                    issues=[
                        AuditIntegrityIssue(
                            trace_id=issue.trace_id,
                            issue=issue.issue,
                            detail=issue.detail,
                        )
                        for issue in trace.issues
                    ],
                )
                for trace in result.traces
            ],
        )

    return chain_validator
