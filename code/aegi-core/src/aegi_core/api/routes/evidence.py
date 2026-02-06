from __future__ import annotations

from fastapi import APIRouter, Depends
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
