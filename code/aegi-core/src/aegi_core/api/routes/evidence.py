# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence


router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("/{evidence_uid}")
async def get_evidence(
    evidence_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    ev = await session.get(Evidence, evidence_uid)
    if ev is None:
        raise not_found("Evidence", evidence_uid)

    chunk = await session.get(Chunk, ev.chunk_uid)
    if chunk is None:
        raise not_found("Chunk", ev.chunk_uid)

    return {
        "evidence_uid": ev.uid,
        "case_uid": ev.case_uid,
        "artifact_version_uid": ev.artifact_version_uid,
        "chunk_uid": ev.chunk_uid,
        "chunk": {
            "text": chunk.text,
            "anchor_set": chunk.anchor_set,
            "anchor_health": chunk.anchor_health,
        },
    }


@router.get("/cases/{case_uid}/list")
async def list_evidence(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(Evidence)
        .where(Evidence.case_uid == case_uid)
    )
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        sa.select(Evidence)
        .where(Evidence.case_uid == case_uid)
        .order_by(Evidence.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    return {
        "items": [
            {
                "evidence_uid": ev.uid,
                "case_uid": ev.case_uid,
                "artifact_version_uid": ev.artifact_version_uid,
                "chunk_uid": ev.chunk_uid,
                "kind": ev.kind,
            }
            for ev in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
