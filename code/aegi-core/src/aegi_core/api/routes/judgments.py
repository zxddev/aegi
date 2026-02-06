# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.judgment import Judgment


router = APIRouter(prefix="/judgments", tags=["judgments"])


@router.get("/{judgment_uid}")
async def get_judgment(
    judgment_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    j = await session.get(Judgment, judgment_uid)
    if j is None:
        raise not_found("Judgment", judgment_uid)

    return {
        "judgment_uid": j.uid,
        "case_uid": j.case_uid,
        "title": j.title,
        "assertion_uids": j.assertion_uids,
    }
