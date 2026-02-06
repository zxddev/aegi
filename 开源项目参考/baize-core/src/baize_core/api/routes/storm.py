"""STORM 接口。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException

from baize_core.api.models import StormRunRequest, StormRunResponse
from baize_core.schemas.evidence import Report
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.storm import StormOutline


def get_router(orchestrator: Any) -> APIRouter:
    """STORM 路由。"""
    router = APIRouter()

    @router.post("/storm/run", response_model=StormRunResponse)
    async def run_storm(payload: StormRunRequest) -> StormRunResponse:
        """运行 STORM 研究流程。"""
        try:
            result = await orchestrator.run_storm(
                task=payload.task,
                report_config=payload.report_config,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        outline = cast(StormOutline | None, result.get("outline"))
        report_record = cast(Report | None, result.get("report_record"))
        review = cast(ReviewResult | None, result.get("review"))
        if outline is None or report_record is None or review is None:
            raise HTTPException(status_code=500, detail="STORM 输出不完整")
        return StormRunResponse(
            outline_uid=outline.outline_uid,
            report_uid=report_record.report_uid,
            report_ref=report_record.content_ref,
            review=review,
        )

    return router
