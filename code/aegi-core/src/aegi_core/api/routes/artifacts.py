# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends
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
