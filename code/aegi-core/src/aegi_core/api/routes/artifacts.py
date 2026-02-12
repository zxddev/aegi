# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.artifact import ArtifactVersion


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/versions/{artifact_version_uid}")
async def get_artifact_version(
    artifact_version_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    av = await session.get(ArtifactVersion, artifact_version_uid)
    if av is None:
        raise not_found("ArtifactVersion", artifact_version_uid)

    return {
        "artifact_version_uid": av.uid,
        "artifact_identity_uid": av.artifact_identity_uid,
        "case_uid": av.case_uid,
        "content_sha256": av.content_sha256,
        "storage_ref": av.storage_ref,
        "content_type": av.content_type,
    }


@router.get("/cases/{case_uid}/list")
async def list_artifacts(
    case_uid: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    content_type: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    stmt = sa.select(ArtifactVersion).where(ArtifactVersion.case_uid == case_uid)
    count_stmt = (
        sa.select(sa.func.count())
        .select_from(ArtifactVersion)
        .where(ArtifactVersion.case_uid == case_uid)
    )

    if content_type:
        stmt = stmt.where(ArtifactVersion.content_type == content_type)
        count_stmt = count_stmt.where(ArtifactVersion.content_type == content_type)

    total = (await session.execute(count_stmt)).scalar() or 0
    rows = (
        (
            await session.execute(
                stmt.order_by(ArtifactVersion.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return {
        "items": [
            {
                "artifact_version_uid": av.uid,
                "artifact_identity_uid": av.artifact_identity_uid,
                "case_uid": av.case_uid,
                "content_sha256": av.content_sha256,
                "storage_ref": av.storage_ref,
                "content_type": av.content_type,
            }
            for av in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }
