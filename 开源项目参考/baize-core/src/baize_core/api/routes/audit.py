"""审计接口。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from baize_core.api.models import (
    AuditQueryRequest,
    AuditQueryResponse,
    AuditSummaryResponse,
    ReplayResponse,
)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_router(orchestrator: Any, replay_service: Any) -> APIRouter:
    """审计相关路由。"""
    router = APIRouter()

    @router.post("/audit/query", response_model=AuditQueryResponse)
    async def query_audit(request: AuditQueryRequest) -> AuditQueryResponse:
        """查询审计记录。"""
        start_dt = _parse_time(request.start_time)
        end_dt = _parse_time(request.end_time)

        tool_traces = await orchestrator.store.query_tool_traces(
            task_id=request.task_id,
            tool_name=request.tool_name,
            success=request.success,
            start_time=start_dt,
            end_time=end_dt,
            limit=request.limit,
            offset=request.offset,
        )
        model_traces = await orchestrator.store.query_model_traces(
            task_id=request.task_id,
            model_name=request.model_name,
            start_time=start_dt,
            end_time=end_dt,
            limit=request.limit,
            offset=request.offset,
        )
        policy_decisions = await orchestrator.store.query_policy_decisions(
            task_id=request.task_id,
            start_time=start_dt,
            end_time=end_dt,
            limit=request.limit,
            offset=request.offset,
        )
        has_more = (
            len(tool_traces) >= request.limit
            or len(model_traces) >= request.limit
            or len(policy_decisions) >= request.limit
        )
        return AuditQueryResponse(
            tool_traces=tool_traces,
            model_traces=model_traces,
            policy_decisions=policy_decisions,
            total_count=len(tool_traces) + len(model_traces) + len(policy_decisions),
            has_more=has_more,
        )

    @router.get("/audit/summary", response_model=AuditSummaryResponse)
    async def get_audit_summary(
        start_time: str | None = Query(default=None, description="开始时间"),
        end_time: str | None = Query(default=None, description="结束时间"),
        task_id: str | None = Query(default=None, description="任务 ID"),
    ) -> AuditSummaryResponse:
        """获取审计摘要统计。"""
        start_dt = _parse_time(start_time)
        end_dt = _parse_time(end_time)

        tool_stats = await orchestrator.store.get_tool_trace_stats(
            task_id=task_id,
            start_time=start_dt,
            end_time=end_dt,
        )
        model_stats = await orchestrator.store.get_model_trace_stats(
            task_id=task_id,
            start_time=start_dt,
            end_time=end_dt,
        )
        policy_stats = await orchestrator.store.get_policy_decision_stats(
            task_id=task_id,
            start_time=start_dt,
            end_time=end_dt,
        )
        tool_success_rate = 0.0
        if tool_stats.get("total", 0) > 0:
            tool_success_rate = tool_stats.get("success", 0) / tool_stats["total"]

        model_success_rate = 0.0
        if model_stats.get("total", 0) > 0:
            model_success_rate = model_stats.get("success", 0) / model_stats["total"]

        return AuditSummaryResponse(
            start_time=start_time,
            end_time=end_time,
            tool_calls_total=tool_stats.get("total", 0),
            tool_calls_success=tool_stats.get("success", 0),
            tool_calls_failed=tool_stats.get("failed", 0),
            tool_success_rate=tool_success_rate,
            model_calls_total=model_stats.get("total", 0),
            model_calls_success=model_stats.get("success", 0),
            model_calls_failed=model_stats.get("failed", 0),
            model_success_rate=model_success_rate,
            total_input_tokens=model_stats.get("input_tokens", 0),
            total_output_tokens=model_stats.get("output_tokens", 0),
            total_tokens=model_stats.get("total_tokens", 0),
            policy_decisions_total=policy_stats.get("total", 0),
            policy_allows=policy_stats.get("allows", 0),
            policy_denies=policy_stats.get("denies", 0),
            tool_breakdown=tool_stats.get("by_tool", {}),
            model_breakdown=model_stats.get("by_model", {}),
            error_breakdown=tool_stats.get("by_error", {}),
        )

    @router.get("/audit/tasks/{task_id}", response_model=ReplayResponse)
    async def get_task_audit(task_id: str) -> ReplayResponse:
        """获取任务的完整审计记录。"""
        return await replay_service.replay_task(task_id)

    @router.get("/audit/tools/{trace_id}")
    async def get_tool_trace(trace_id: str) -> dict:
        """获取单个工具调用详情。"""
        trace = await orchestrator.store.get_tool_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="工具调用记录不存在")
        return trace.model_dump()

    @router.get("/audit/models/{trace_id}")
    async def get_model_trace(trace_id: str) -> dict:
        """获取单个模型调用详情。"""
        trace = await orchestrator.store.get_model_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="模型调用记录不存在")
        return trace.model_dump()

    @router.get("/replay/{task_id}", response_model=ReplayResponse)
    async def replay_task(task_id: str) -> ReplayResponse:
        """回放任务审计链路。"""
        replay = await replay_service.replay_task(task_id)
        return ReplayResponse(**replay)

    return router
