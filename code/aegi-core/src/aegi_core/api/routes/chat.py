# Author: msq
"""对话式分析与证据问答 API。

Source: openspec/changes/conversational-analysis-evidence-qa/design.md
Evidence:
  - POST /cases/{case_uid}/analysis/chat -> AnswerV1
  - GET /cases/{case_uid}/analysis/chat/{trace_id} -> QueryPlan + citations
  - 响应统一包含 trace_id 和 citations
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.contracts.llm_governance import GroundingLevel
from aegi_core.db.models.action import Action
from aegi_core.db.models.case import Case
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.answer_renderer import EvidenceCitation, render_answer
from aegi_core.services.query_planner import RiskFlag, plan_query

router = APIRouter(prefix="/cases", tags=["chat"])

# -- 内存存储（P1 阶段，无新 DB 表） ------------------------------------------
_trace_store: dict[str, dict] = {}


class ChatRequestIn(BaseModel):
    question: str
    time_range: Optional[dict] = None
    language: Optional[str] = None


@router.post("/{case_uid}/analysis/chat")
async def chat(
    case_uid: str,
    body: ChatRequestIn,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    trace_id = f"chat_{uuid4().hex}"

    # 1) 查询规划
    plan = plan_query(
        body.question,
        case_uid,
        time_range=body.time_range,
        language=body.language,
    )

    # 2) 检索 source claims
    result = await session.execute(sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid))
    claims = result.scalars().all()

    # 3) 简单关键词匹配（P1）
    keywords = body.question.lower().split()
    matched: list[SourceClaim] = []
    for sc in claims:
        quote_lower = (sc.quote or "").lower()
        if any(kw in quote_lower for kw in keywords if len(kw) > 2):
            matched.append(sc)

    # 4) 构建 citations
    citations = [
        EvidenceCitation(
            source_claim_uid=sc.uid,
            quote=sc.quote or "",
            evidence_uid=sc.evidence_uid or "",
        )
        for sc in matched
    ]

    # 5) 判定风险
    if not matched:
        plan.risk_flags.append(RiskFlag.EVIDENCE_INSUFFICIENT)
    if len(matched) < 2:
        plan.risk_flags.append(RiskFlag.SOURCES_INSUFFICIENT)

    # 6) 渲染回答
    requested_type = GroundingLevel.FACT if citations else GroundingLevel.HYPOTHESIS
    answer_text = f"基于 {len(citations)} 条证据的分析结果。" if citations else ""
    answer = render_answer(
        answer_text=answer_text,
        requested_type=requested_type,
        evidence_citations=citations,
        trace_id=trace_id,
    )

    # 7) 记录 action
    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="analysis.chat",
            inputs=body.model_dump(exclude_none=True),
            outputs={"trace_id": trace_id, "answer_type": answer.answer_type.value},
        )
    )
    await session.commit()

    # 8) 存储 trace（P1 内存）
    _trace_store[trace_id] = {
        "trace_id": trace_id,
        "case_uid": case_uid,
        "query_plan": plan.model_dump(),
        "citations": [c.model_dump() for c in citations],
        "answer": answer.model_dump(),
    }

    return answer.model_dump()


@router.get("/{case_uid}/analysis/chat/{trace_id}")
async def get_chat_trace(
    case_uid: str,
    trace_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    trace = _trace_store.get(trace_id)
    if trace is None or trace.get("case_uid") != case_uid:
        raise AegiHTTPError(404, "trace_not_found", "Chat trace not found", {"trace_id": trace_id})

    return trace
