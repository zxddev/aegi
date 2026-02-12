# Author: msq
"""AnalysisMemory API routes."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import (
    get_analysis_memory_qdrant_store,
    get_db_session,
    get_llm_client,
)
from aegi_core.api.errors import AegiHTTPError
from aegi_core.db.models.analysis_memory import AnalysisMemoryRecord
from aegi_core.services.analysis_memory import AnalysisMemory, AnalysisMemoryEntry

router = APIRouter(prefix="/api/memory", tags=["analysis-memory"])


class MemoryListItem(BaseModel):
    uid: str
    case_uid: str
    scenario_summary: str
    conclusion: str
    confidence: float
    outcome: str | None = None
    prediction_accuracy: float | None = None
    pattern_tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class PaginatedMemoryResponse(BaseModel):
    items: list[MemoryListItem]
    total: int


class MemoryOutcomeRequest(BaseModel):
    outcome: str
    accuracy: float = Field(ge=0.0, le=1.0)
    lessons_learned: str | None = None


class PatternStatsResponse(BaseModel):
    pattern_tag: str
    count: int
    avg_accuracy: float | None = None
    recent_case: dict | None = None


@router.get("", response_model=PaginatedMemoryResponse)
async def list_memory(
    case_uid: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedMemoryResponse:
    filters = []
    if case_uid:
        filters.append(AnalysisMemoryRecord.case_uid == case_uid)

    count_stmt = sa.select(sa.func.count()).select_from(AnalysisMemoryRecord)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await session.execute(count_stmt)).scalar() or 0

    rows_stmt = (
        sa.select(AnalysisMemoryRecord)
        .order_by(AnalysisMemoryRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows = (await session.execute(rows_stmt)).scalars().all()

    return PaginatedMemoryResponse(
        items=[
            MemoryListItem(
                uid=row.uid,
                case_uid=row.case_uid,
                scenario_summary=row.scenario_summary,
                conclusion=row.conclusion,
                confidence=float(row.confidence),
                outcome=row.outcome,
                prediction_accuracy=row.prediction_accuracy,
                pattern_tags=row.pattern_tags or [],
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
            )
            for row in rows
        ],
        total=total,
    )


@router.post("/{uid}/outcome", response_model=AnalysisMemoryEntry)
async def update_memory_outcome(
    uid: str,
    body: MemoryOutcomeRequest,
    session: AsyncSession = Depends(get_db_session),
    llm=Depends(get_llm_client),
    qdrant=Depends(get_analysis_memory_qdrant_store),
) -> AnalysisMemoryEntry:
    service = AnalysisMemory(session, qdrant=qdrant, llm=llm)
    try:
        return await service.update_outcome(
            uid,
            outcome=body.outcome,
            accuracy=body.accuracy,
            lessons_learned=body.lessons_learned,
        )
    except ValueError:
        raise AegiHTTPError(404, "not_found", f"Memory entry {uid} not found", {})


@router.get("/patterns", response_model=list[PatternStatsResponse])
async def pattern_stats(
    pattern_tag: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    llm=Depends(get_llm_client),
    qdrant=Depends(get_analysis_memory_qdrant_store),
) -> list[PatternStatsResponse]:
    service = AnalysisMemory(session, qdrant=qdrant, llm=llm)
    if pattern_tag:
        stat = await service.get_pattern_stats(pattern_tag)
        return [PatternStatsResponse.model_validate(stat)]

    rows = (
        (
            await session.execute(
                sa.select(AnalysisMemoryRecord).order_by(
                    AnalysisMemoryRecord.created_at.desc()
                )
            )
        )
        .scalars()
        .all()
    )
    tag_map: dict[str, list[AnalysisMemoryRecord]] = {}
    for row in rows:
        for tag in row.pattern_tags or []:
            tag_map.setdefault(tag, []).append(row)

    stats = []
    for tag, tag_rows in tag_map.items():
        accuracies = [
            float(item.prediction_accuracy)
            for item in tag_rows
            if item.prediction_accuracy is not None
        ]
        recent = tag_rows[0]
        stats.append(
            PatternStatsResponse(
                pattern_tag=tag,
                count=len(tag_rows),
                avg_accuracy=(
                    (sum(accuracies) / len(accuracies)) if accuracies else None
                ),
                recent_case={
                    "uid": recent.uid,
                    "case_uid": recent.case_uid,
                    "conclusion": recent.conclusion,
                    "prediction_accuracy": recent.prediction_accuracy,
                    "created_at": recent.created_at.isoformat(),
                },
            )
        )

    stats.sort(key=lambda item: item.count, reverse=True)
    return stats[:limit]


@router.get("/recall", response_model=list[AnalysisMemoryEntry])
async def recall_memory(
    scenario: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    session: AsyncSession = Depends(get_db_session),
    llm=Depends(get_llm_client),
    qdrant=Depends(get_analysis_memory_qdrant_store),
) -> list[AnalysisMemoryEntry]:
    service = AnalysisMemory(session, qdrant=qdrant, llm=llm)
    return await service.recall(scenario, top_k=top_k)

