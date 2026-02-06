"""报告接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from baize_core.api.models import ReportExportRequest
from baize_core.schemas.review import ReviewResult


def get_router(orchestrator: Any) -> APIRouter:
    """报告相关路由。"""
    router = APIRouter()

    @router.post("/reports/export", response_model=ReviewResult)
    async def export_report(payload: ReportExportRequest) -> ReviewResult:
        """导出报告前的引用审查。"""
        if payload.report is None:
            raise HTTPException(status_code=400, detail="导出需要报告")
        task_id = payload.report.task_id
        await orchestrator.enforce_export_policy(task_id=task_id)
        if payload.task is not None:
            return await orchestrator.run_ooda(
                task=payload.task,
                claims=payload.claims,
                evidence=payload.evidence,
                chunks=payload.chunks,
                artifacts=payload.artifacts,
                report=payload.report,
            )
        return await orchestrator.review_output(
            claims=payload.claims,
            evidence=payload.evidence,
            chunks=payload.chunks,
            artifacts=payload.artifacts,
            report=payload.report,
        )

    return router
