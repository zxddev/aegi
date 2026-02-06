# Author: msq
"""Orchestration API routes: full_analysis and run_stage.

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md (3.1–3.2)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client, get_neo4j_store
from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services.pipeline_orchestrator import PipelineOrchestrator, StageResult

router = APIRouter(prefix="/cases/{case_uid}/pipelines", tags=["orchestration"])


class FullAnalysisRequest(BaseModel):
    source_claim_uids: list[str] = Field(default_factory=list)
    start_from: str | None = None
    stages: list[str] | None = None


class StageResultResponse(BaseModel):
    stage: str
    status: str
    duration_ms: int
    output: Any = None
    error: str | None = None


class PipelineResultResponse(BaseModel):
    case_uid: str
    stages: list[StageResultResponse] = Field(default_factory=list)
    total_duration_ms: int = 0


class RunStageRequest(BaseModel):
    stage_name: str
    inputs: dict = Field(default_factory=dict)


def _stage_to_response(sr: StageResult) -> StageResultResponse:
    output = sr.output
    if isinstance(output, list):
        output = [
            o.model_dump()
            if hasattr(o, "model_dump")
            else o.__dict__
            if hasattr(o, "__dict__") and not isinstance(o, dict)
            else o
            for o in output
        ]
    elif hasattr(output, "model_dump"):
        output = output.model_dump()
    return StageResultResponse(
        stage=sr.stage,
        status=sr.status,
        duration_ms=sr.duration_ms,
        output=output,
        error=sr.error,
    )


async def _load_source_claims(
    db: AsyncSession,
    case_uid: str,
    uids: list[str] | None = None,
) -> list[SourceClaimV1]:
    """Load SourceClaims from DB, convert to contract schema."""
    stmt = select(SourceClaim).where(SourceClaim.case_uid == case_uid)
    if uids:
        stmt = stmt.where(SourceClaim.uid.in_(uids))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        SourceClaimV1(
            uid=r.uid,
            case_uid=r.case_uid,
            artifact_version_uid=r.artifact_version_uid,
            chunk_uid=r.chunk_uid,
            evidence_uid=r.evidence_uid,
            quote=r.quote,
            selectors=r.selectors or [],
            attributed_to=r.attributed_to,
            modality=r.modality,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/full_analysis", response_model=PipelineResultResponse)
async def full_analysis_endpoint(
    case_uid: str,
    body: FullAnalysisRequest,
    db: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> PipelineResultResponse:
    """执行全链路分析 pipeline（async，使用 LLM + Neo4j）。"""
    source_claims = await _load_source_claims(
        db,
        case_uid,
        body.source_claim_uids or None,
    )

    orchestrator = PipelineOrchestrator(llm=llm, neo4j_store=neo4j)
    result = await orchestrator.run_full_async(
        case_uid=case_uid,
        source_claims=source_claims,
        stages=body.stages,
        start_from=body.start_from,
    )
    return PipelineResultResponse(
        case_uid=result.case_uid,
        stages=[_stage_to_response(s) for s in result.stages],
        total_duration_ms=result.total_duration_ms,
    )


@router.post("/run_stage", response_model=StageResultResponse)
async def run_stage_endpoint(
    case_uid: str,
    body: RunStageRequest,
) -> StageResultResponse:
    """执行单阶段（同步模式）。"""
    orchestrator = PipelineOrchestrator()
    sr = orchestrator.run_stage(body.stage_name, {"case_uid": case_uid, **body.inputs})
    return _stage_to_response(sr)
