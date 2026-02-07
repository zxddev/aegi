# Author: msq
"""对话式分析与证据问答 API。

Source: openspec/changes/conversational-analysis-evidence-qa/design.md
Evidence:
  - POST /cases/{case_uid}/analysis/chat -> AnswerV1
  - GET /cases/{case_uid}/analysis/chat/{trace_id} -> QueryPlan + citations
  - 响应统一包含 trace_id 和 citations
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client, get_qdrant_store
from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.contracts.llm_governance import GroundingLevel
from aegi_core.db.models.action import Action
from aegi_core.db.models.case import Case
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.answer_renderer import (
    EvidenceCitation,
    format_evidence_context,
    generate_grounded_answer,
    render_answer,
)
from aegi_core.services.query_planner import RiskFlag, plan_query

router = APIRouter(prefix="/cases", tags=["chat"])


class ChatRequestIn(BaseModel):
    question: str
    time_range: dict | None = None
    language: str | None = None


@router.post("/{case_uid}/analysis/chat")
async def chat(
    case_uid: str,
    body: ChatRequestIn,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
    qdrant: QdrantStore = Depends(get_qdrant_store),
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

    # 2) 语义检索：embed 问题 → Qdrant 搜索 → 反查 SourceClaim
    matched: list[SourceClaim] = []
    try:
        embedding = await llm.embed(body.question)
        hits = await qdrant.search(embedding, limit=10, score_threshold=0.3)
        if hits:
            hit_chunk_uids = [h.chunk_uid for h in hits]
            rows = await session.execute(
                sa.select(SourceClaim).where(
                    SourceClaim.case_uid == case_uid,
                    SourceClaim.chunk_uid.in_(hit_chunk_uids),
                )
            )
            matched = list(rows.scalars().all())
    except Exception:  # noqa: BLE001 — Qdrant/embedding 不可用时降级
        import logging

        logging.getLogger(__name__).warning("语义检索降级", exc_info=True)

    # 3) 降级：语义检索无结果时回退关键词匹配
    if not matched:
        rows = await session.execute(
            sa.select(SourceClaim).where(SourceClaim.case_uid == case_uid)
        )
        all_claims = rows.scalars().all()
        keywords = body.question.lower().split()
        for sc in all_claims:
            quote_lower = (sc.quote or "").lower()
            if any(kw in quote_lower for kw in keywords if len(kw) > 2):
                matched.append(sc)

    # 4) 构建 citations
    citations = [
        EvidenceCitation(
            source_claim_uid=sc.uid,
            quote=sc.quote or "",
            evidence_uid=sc.evidence_uid or "",
            artifact_version_uid=sc.artifact_version_uid or "",
        )
        for sc in matched
    ]

    # 5) 判定风险
    if not matched:
        plan.risk_flags.append(RiskFlag.EVIDENCE_INSUFFICIENT)
    if len(matched) < 2:
        plan.risk_flags.append(RiskFlag.SOURCES_INSUFFICIENT)

    # 6) 渲染回答：有证据时调用 LLM grounded QA，无证据走 cannot_answer
    if citations:
        evidence_context, index_map = format_evidence_context(citations)
        answer = await generate_grounded_answer(
            question=body.question,
            evidence_context=evidence_context,
            index_map=index_map,
            llm=llm,
            trace_id=trace_id,
        )
    else:
        answer = render_answer(
            answer_text="",
            requested_type=GroundingLevel.HYPOTHESIS,
            evidence_citations=[],
            trace_id=trace_id,
        )

    # 7) 记录 action + trace 持久化（存入 Action.outputs）
    trace_data = {
        "trace_id": trace_id,
        "case_uid": case_uid,
        "query_plan": plan.model_dump(),
        "citations": [c.model_dump() for c in citations],
        "answer": answer.model_dump(),
    }
    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="analysis.chat",
            inputs=body.model_dump(exclude_none=True),
            outputs=trace_data,
            trace_id=trace_id,
        )
    )
    await session.commit()

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

    # 从 Action 表读取持久化的 trace
    row = await session.execute(
        sa.select(Action).where(
            Action.case_uid == case_uid,
            Action.action_type == "analysis.chat",
            Action.trace_id == trace_id,
        )
    )
    action = row.scalars().first()
    if action is None or not action.outputs:
        raise AegiHTTPError(
            404, "trace_not_found", "Chat trace not found", {"trace_id": trace_id}
        )

    return action.outputs
