"""多视角分析 API — persona_generator 接入。"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.api.errors import not_found
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.case import Case
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.services.persona_generator import generate_hypotheses_multi_perspective

router = APIRouter(prefix="/cases", tags=["persona"])


class MultiPerspectiveRequest(BaseModel):
    persona_count: int = 3


@router.post("/{case_uid}/analysis/multi_perspective")
async def multi_perspective_analysis(
    case_uid: str,
    body: MultiPerspectiveRequest,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    # 加载当前 case 的 assertions + source_claims
    assertions = list(
        (
            await session.execute(
                sa.select(Assertion).where(Assertion.case_uid == case_uid)
            )
        )
        .scalars()
        .all()
    )
    source_claims = list(
        (
            await session.execute(
                sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid)
            )
        )
        .scalars()
        .all()
    )

    hypotheses = await generate_hypotheses_multi_perspective(
        assertions,
        source_claims,
        case_uid=case_uid,
        llm=llm,
        persona_count=body.persona_count,
    )

    personas_used = list({h["persona"] for h in hypotheses})

    return {
        "case_uid": case_uid,
        "hypotheses": hypotheses,
        "personas_used": personas_used,
    }
