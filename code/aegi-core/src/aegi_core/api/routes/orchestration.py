# Author: msq
"""Orchestration API routes: full_analysis and run_stage.

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md (3.1–3.2)
Note: 桩实现，不注入 DB session，由 merge 协调者统一处理。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/cases/{case_uid}/pipelines", tags=["orchestration"])


class FullAnalysisRequest(BaseModel):
    """全链路分析请求。"""

    source_claim_uids: list[str] = Field(default_factory=list)
    start_from: str | None = None
    stages: list[str] | None = None


class StageResultResponse(BaseModel):
    """单阶段结果。"""

    stage: str
    status: str
    duration_ms: int
    output: Any = None
    error: str | None = None


class PipelineResultResponse(BaseModel):
    """Pipeline 结果。"""

    case_uid: str
    stages: list[StageResultResponse] = Field(default_factory=list)
    total_duration_ms: int = 0


class RunStageRequest(BaseModel):
    """单阶段执行请求。"""

    stage_name: str
    inputs: dict = Field(default_factory=dict)


@router.post("/full_analysis", response_model=PipelineResultResponse)
async def full_analysis_endpoint(
    case_uid: str,
    body: FullAnalysisRequest,
) -> PipelineResultResponse:
    """执行全链路分析 pipeline（桩实现）。"""
    return PipelineResultResponse(case_uid=case_uid)


@router.post("/run_stage", response_model=StageResultResponse)
async def run_stage_endpoint(
    case_uid: str,
    body: RunStageRequest,
) -> StageResultResponse:
    """执行单阶段（桩实现）。"""
    return StageResultResponse(stage=body.stage_name, status="skipped", duration_ms=0)
