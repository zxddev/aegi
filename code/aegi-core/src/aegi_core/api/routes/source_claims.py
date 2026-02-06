from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.source_claim import SourceClaim


router = APIRouter(prefix="/source_claims", tags=["source_claims"])


@router.get("/{source_claim_uid}")
async def get_source_claim(
    source_claim_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    sc = await session.get(SourceClaim, source_claim_uid)
    if sc is None:
        raise not_found("SourceClaim", source_claim_uid)

    return {
        "source_claim_uid": sc.uid,
        "case_uid": sc.case_uid,
        "artifact_version_uid": sc.artifact_version_uid,
        "chunk_uid": sc.chunk_uid,
        "evidence_uid": sc.evidence_uid,
        "quote": sc.quote,
        "selectors": sc.selectors,
    }
