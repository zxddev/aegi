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

from aegi_core.api.deps import (
    get_db_session,
    get_llm_client,
    get_neo4j_store,
    get_qdrant_store,
)
from aegi_core.api.errors import AegiHTTPError, not_found
from aegi_core.contracts.llm_governance import GroundingLevel
from aegi_core.db.models.action import Action
from aegi_core.db.models.case import Case
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.answer_renderer import (
    EvidenceCitation,
    format_evidence_context,
    generate_grounded_answer,
    render_answer,
)
from aegi_core.services.query_planner import RiskFlag, aplan_query


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
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> dict:
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)

    trace_id = f"chat_{uuid4().hex}"

    # 1) 查询规划（LLM 驱动，无 LLM 时 fallback 到规则版本）
    plan = await aplan_query(
        body.question,
        case_uid,
        time_range=body.time_range,
        language=body.language,
        llm=llm,
    )

    # 2) 语义检索：embed 问题 → Qdrant 搜索 → 反查 SourceClaim
    matched: list[SourceClaim] = []
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

    # 5) 图谱增强：从 Neo4j 检索相关实体，展开 2-hop 邻居 + 路径发现
    graph_context = ""
    keywords = [w for w in body.question.lower().split() if len(w) > 2]
    if keywords:
        entities = await neo4j.search_entities(keywords, case_uid, limit=5)
        if entities:
            graph_parts: list[str] = []
            entity_uids: list[str] = []
            for ent in entities:
                ent_uid = ent.get("uid", "")
                ent_name = ent.get("name", "")
                ent_type = ent.get("type", "")
                entity_uids.append(ent_uid)
                graph_parts.append(f"[{ent_type}] {ent_name} (uid={ent_uid})")
                # 2-hop 邻居
                hop1 = await neo4j.get_neighbors(ent_uid, limit=10)
                for nb in hop1:
                    nb_data = nb["neighbor"]
                    nb_uid = nb_data.get("uid", "")
                    nb_name = nb_data.get("name", nb_data.get("label", ""))
                    graph_parts.append(
                        f"  --{nb['rel_type']}--> [{nb_data.get('type', '')}] {nb_name}"
                    )
                    # 第 2 跳
                    hop2 = await neo4j.get_neighbors(nb_uid, limit=5)
                    for nb2 in hop2:
                        nb2_data = nb2["neighbor"]
                        nb2_name = nb2_data.get("name", nb2_data.get("label", ""))
                        if nb2_data.get("uid") != ent_uid:
                            graph_parts.append(f"    --{nb2['rel_type']}--> {nb2_name}")

            # 匹配到的实体间路径发现
            if len(entity_uids) >= 2:
                for i in range(min(len(entity_uids) - 1, 3)):
                    paths = await neo4j.find_path(
                        entity_uids[i],
                        entity_uids[i + 1],
                        max_depth=4,
                    )
                    for p in paths:
                        node_names = [
                            n.get("name", n.get("label", n.get("uid", "")))
                            for n in p.get("nodes", [])
                        ]
                        if node_names:
                            graph_parts.append(f"  路径: {' → '.join(node_names)}")

            # 有 time_range 时查实体时间线
            if body.time_range and entity_uids:
                for uid in entity_uids[:3]:
                    timeline = await neo4j.get_entity_timeline(uid, limit=5)
                    for t in timeline:
                        ev = t["event"]
                        graph_parts.append(
                            f"  时间线: [{ev.get('timestamp_ref', '?')}] {ev.get('label', '')}"
                        )

            graph_context = "\n".join(graph_parts)

    # 6) 判定风险
    if not matched:
        plan.risk_flags.append(RiskFlag.EVIDENCE_INSUFFICIENT)
    if len(matched) < 2:
        plan.risk_flags.append(RiskFlag.SOURCES_INSUFFICIENT)

    # 7) 渲染回答：有证据时调用 LLM grounded QA，无证据走 cannot_answer
    if citations:
        evidence_context, index_map = format_evidence_context(citations)
        # 将图谱上下文拼入证据上下文
        if graph_context:
            evidence_context = (
                f"=== 知识图谱相关实体与关系 ===\n{graph_context}\n\n"
                f"=== 证据引用 ===\n{evidence_context}"
            )
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

    # 8) 记录 action + trace 持久化（存入 Action.outputs）
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
