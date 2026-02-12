# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
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


@router.get("/cases/{case_uid}/list")
async def list_source_claims(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    attributed_to: str | None = None,
    language: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid)
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(SourceClaim)
        .where(SourceClaim.case_uid == case_uid)
    )

    if attributed_to:
        stmt = stmt.where(SourceClaim.attributed_to == attributed_to)
        count_stmt = count_stmt.where(SourceClaim.attributed_to == attributed_to)
    if language:
        stmt = stmt.where(SourceClaim.language == language)
        count_stmt = count_stmt.where(SourceClaim.language == language)

    total = (await session.execute(count_stmt)).scalar() or 0
    rows = (
        (
            await session.execute(
                stmt.order_by(SourceClaim.created_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "items": [
            {
                "source_claim_uid": sc.uid,
                "case_uid": sc.case_uid,
                "artifact_version_uid": sc.artifact_version_uid,
                "chunk_uid": sc.chunk_uid,
                "evidence_uid": sc.evidence_uid,
                "quote": sc.quote,
                "selectors": sc.selectors,
                "attributed_to": sc.attributed_to,
                "language": sc.language,
            }
            for sc in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
