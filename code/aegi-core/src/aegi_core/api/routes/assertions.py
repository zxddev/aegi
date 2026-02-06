# Author: msq
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.db.models.assertion import Assertion


router = APIRouter(prefix="/assertions", tags=["assertions"])


@router.get("/{assertion_uid}")
async def get_assertion(
    assertion_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    a = await session.get(Assertion, assertion_uid)
    if a is None:
        raise not_found("Assertion", assertion_uid)

    return {
        "assertion_uid": a.uid,
        "case_uid": a.case_uid,
        "kind": a.kind,
        "source_claim_uids": a.source_claim_uids,
        "value": a.value,
        "confidence": a.confidence,
    }
