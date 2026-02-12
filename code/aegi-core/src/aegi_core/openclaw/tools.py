"""OpenClaw agent 回调 AEGI 的 REST 端点。

这些端点注册为 OpenClaw agent 配置里的自定义工具。
agent 在 tool-use 循环中调用这些 HTTP 接口。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import (
    get_db_session,
    get_llm_client,
    get_neo4j_store,
    get_qdrant_store,
)
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services import case_service, ingest_helpers
from aegi_core.services.pipeline_orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw/tools", tags=["openclaw-tools"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------


class SubmitEvidenceReq(BaseModel):
    user: str
    content: str
    source: str
    case_id: str | None = None


class CreateCaseReq(BaseModel):
    user: str
    title: str
    description: str = ""


class QueryKGReq(BaseModel):
    user: str
    query: str
    limit: int = 20


class RunPipelineReq(BaseModel):
    user: str
    case_id: str
    playbook: str = "default"


class GetReportReq(BaseModel):
    user: str
    case_id: str


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] = {}
    error: str = ""


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/submit_evidence", response_model=ToolResult)
async def submit_evidence(
    req: SubmitEvidenceReq,
    db: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
    qdrant: QdrantStore = Depends(get_qdrant_store),
) -> ToolResult:
    """Agent 把采集到的证据提交到 AEGI。"""
    try:
        case_uid = req.case_id
        if not case_uid:
            result = await case_service.create_case(
                db,
                title=f"Evidence from {req.source[:60]}",
                actor_id=req.user,
                rationale="auto-created by openclaw agent",
                inputs={"source": req.source},
            )
            case_uid = result["case_uid"]

        # 创建 artifact 链: Identity → Version → Chunk → Evidence
        sha = hashlib.sha256(req.content.encode()).hexdigest()
        aid_uid = f"aid_{uuid4().hex}"
        av_uid = f"av_{uuid4().hex}"
        chunk_uid = f"chk_{uuid4().hex}"
        ev_uid = f"ev_{uuid4().hex}"

        db.add(ArtifactIdentity(uid=aid_uid, kind="text", canonical_url=req.source))
        await db.flush()
        db.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=aid_uid,
                case_uid=case_uid,
                content_sha256=sha,
                content_type="text/plain",
                source_meta={"source": req.source, "submitted_by": req.user},
            )
        )
        await db.flush()
        db.add(
            Chunk(
                uid=chunk_uid,
                artifact_version_uid=av_uid,
                ordinal=0,
                text=req.content,
                anchor_set=[],
            )
        )
        await db.flush()
        db.add(
            Evidence(
                uid=ev_uid,
                case_uid=case_uid,
                artifact_version_uid=av_uid,
                chunk_uid=chunk_uid,
                kind="text",
                pii_flags={},
                retention_policy={},
            )
        )
        await db.commit()

        # 把 chunk 向量化写入 Qdrant 供语义搜索
        await ingest_helpers.embed_and_index_chunk(
            chunk_uid=chunk_uid,
            text=req.content,
            llm=llm,
            qdrant=qdrant,
            metadata={"case_uid": case_uid, "evidence_uid": ev_uid},
        )

        return ToolResult(
            ok=True,
            data={
                "evidence_uid": ev_uid,
                "case_uid": case_uid,
                "chunk_uid": chunk_uid,
            },
        )
    except Exception as exc:
        logger.exception("submit_evidence failed")
        return ToolResult(ok=False, error=str(exc))


@router.post("/create_case", response_model=ToolResult)
async def create_case(
    req: CreateCaseReq,
    db: AsyncSession = Depends(get_db_session),
) -> ToolResult:
    """Agent 创建新的分析案例。"""
    try:
        result = await case_service.create_case(
            db,
            title=req.title,
            actor_id=req.user,
            rationale=req.description or "created by openclaw agent",
            inputs={"description": req.description},
        )
        return ToolResult(ok=True, data=result)
    except Exception as exc:
        logger.exception("create_case failed")
        return ToolResult(ok=False, error=str(exc))


@router.post("/query_kg", response_model=ToolResult)
async def query_kg(
    req: QueryKGReq,
    neo4j: Neo4jStore = Depends(get_neo4j_store),
    llm: LLMClient = Depends(get_llm_client),
    qdrant: QdrantStore = Depends(get_qdrant_store),
) -> ToolResult:
    """Agent 查询知识图谱 + 向量库。"""
    try:
        keywords = req.query.split()[:10]
        kg_results = await neo4j.search_entities(keywords, case_uid="", limit=req.limit)
        vector_results = await ingest_helpers.semantic_search(
            query=req.query,
            llm=llm,
            qdrant=qdrant,
            limit=req.limit,
        )
        return ToolResult(
            ok=True,
            data={
                "kg_entities": kg_results[: req.limit],
                "semantic_matches": vector_results[: req.limit],
            },
        )
    except Exception as exc:
        logger.exception("query_kg failed")
        return ToolResult(ok=False, error=str(exc))


async def _auto_extract_claims(
    db: AsyncSession,
    llm: LLMClient,
    case_uid: str,
) -> list:
    """没有 SourceClaim 时，用 LLM 从证据 chunk 里自动提取。"""
    import json as _json
    import uuid as _uuid
    from datetime import datetime, timezone

    import httpx

    from aegi_core.contracts.schemas import Modality, SourceClaimV1

    stmt = (
        select(Evidence, Chunk)
        .join(Chunk, Evidence.chunk_uid == Chunk.uid)
        .where(Evidence.case_uid == case_uid)
    )
    pairs = (await db.execute(stmt)).all()
    if not pairs:
        return []

    all_claims: list[SourceClaimV1] = []
    now = datetime.now(timezone.utc)

    for ev, chunk in pairs:
        prompt = (
            "Extract factual claims from the following text. "
            "Return a JSON array of objects, each with: "
            '"quote" (the exact text), "attributed_to" (source if identifiable, else null).\n\n'
            f"Text:\n{chunk.text}"
        )
        try:
            # 直接用 chat completions API（proxy 可能不支持 /v1/responses）
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{llm._base_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {llm._api_key}"},
                    json={
                        "model": llm._default_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2048,
                        "temperature": 0.0,
                    },
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]

            from aegi_core.infra.llm_client import parse_llm_json

            raw = parse_llm_json(text)
            if not isinstance(raw, list):
                raw = [raw] if raw else []
        except Exception as exc:
            logger.warning("Claim extraction failed for chunk %s: %s", chunk.uid, exc)
            continue

        for item in raw:
            if not isinstance(item, dict):
                continue
            quote = item.get("quote", "")
            if not quote:
                continue
            uid = _uuid.uuid4().hex
            claim = SourceClaimV1(
                uid=uid,
                case_uid=case_uid,
                artifact_version_uid=chunk.artifact_version_uid,
                chunk_uid=chunk.uid,
                evidence_uid=ev.uid,
                quote=quote,
                selectors=[{"type": "TextQuoteSelector", "exact": quote}],
                attributed_to=item.get("attributed_to"),
                modality=Modality.TEXT,
                created_at=now,
            )
            db.add(
                SourceClaim(
                    uid=uid,
                    case_uid=case_uid,
                    artifact_version_uid=chunk.artifact_version_uid,
                    chunk_uid=chunk.uid,
                    evidence_uid=ev.uid,
                    quote=quote,
                    selectors=[{"type": "TextQuoteSelector", "exact": quote}],
                    attributed_to=item.get("attributed_to"),
                    modality="text",
                )
            )
            all_claims.append(claim)

    if all_claims:
        await db.flush()
        logger.info("Auto-extracted %d claims for case %s", len(all_claims), case_uid)
    return all_claims


@router.post("/run_pipeline", response_model=ToolResult)
async def run_pipeline(
    req: RunPipelineReq,
    db: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> ToolResult:
    """Agent 触发案例的分析 pipeline。"""
    try:
        from aegi_core.contracts.schemas import SourceClaimV1

        stmt = select(SourceClaim).where(SourceClaim.case_uid == req.case_id)
        rows = (await db.execute(stmt)).scalars().all()
        source_claims = [
            SourceClaimV1(
                uid=r.uid,
                case_uid=r.case_uid,
                artifact_version_uid=r.artifact_version_uid,
                chunk_uid=r.chunk_uid,
                evidence_uid=r.evidence_uid,
                quote=r.quote,
                selectors=r.selectors or [],
                attributed_to=r.attributed_to,
                modality=r.modality,
                created_at=r.created_at,
            )
            for r in rows
        ]

        # 没有 claim 时自动从证据 chunk 提取
        if not source_claims:
            source_claims = await _auto_extract_claims(db, llm, req.case_id)

        orchestrator = PipelineOrchestrator(llm=llm, neo4j_store=neo4j)
        pr = await orchestrator.run_playbook(
            playbook_name=req.playbook,
            case_uid=req.case_id,
            source_claims=source_claims,
        )
        stages_summary = [
            {"stage": s.stage, "status": s.status, "duration_ms": s.duration_ms}
            for s in pr.stages
        ]
        return ToolResult(
            ok=True,
            data={
                "case_uid": pr.case_uid,
                "total_duration_ms": pr.total_duration_ms,
                "stages": stages_summary,
            },
        )
    except Exception as exc:
        logger.exception("run_pipeline failed")
        return ToolResult(ok=False, error=str(exc))


@router.post("/get_report", response_model=ToolResult)
async def get_report(
    req: GetReportReq,
    db: AsyncSession = Depends(get_db_session),
) -> ToolResult:
    """Agent 获取案例的证据摘要和 KG 统计。"""
    try:
        from aegi_core.db.models.assertion import Assertion
        from aegi_core.db.models.hypothesis import Hypothesis
        from aegi_core.db.models.narrative import Narrative

        ev_count = (
            await db.execute(
                select(sa.func.count())
                .select_from(Evidence)
                .where(Evidence.case_uid == req.case_id)
            )
        ).scalar() or 0
        sc_count = (
            await db.execute(
                select(sa.func.count())
                .select_from(SourceClaim)
                .where(SourceClaim.case_uid == req.case_id)
            )
        ).scalar() or 0
        a_count = (
            await db.execute(
                select(sa.func.count())
                .select_from(Assertion)
                .where(Assertion.case_uid == req.case_id)
            )
        ).scalar() or 0
        h_count = (
            await db.execute(
                select(sa.func.count())
                .select_from(Hypothesis)
                .where(Hypothesis.case_uid == req.case_id)
            )
        ).scalar() or 0

        h_rows = (
            (
                await db.execute(
                    select(Hypothesis)
                    .where(Hypothesis.case_uid == req.case_id)
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
        hypotheses = [
            {"uid": h.uid, "label": h.label, "confidence": h.confidence} for h in h_rows
        ]

        n_rows = (
            (
                await db.execute(
                    select(Narrative).where(Narrative.case_uid == req.case_id).limit(5)
                )
            )
            .scalars()
            .all()
        )
        narratives = [{"uid": n.uid, "title": n.title} for n in n_rows]

        return ToolResult(
            ok=True,
            data={
                "case_uid": req.case_id,
                "evidence_count": ev_count,
                "source_claim_count": sc_count,
                "assertion_count": a_count,
                "hypothesis_count": h_count,
                "hypotheses": hypotheses,
                "narratives": narratives,
            },
        )
    except Exception as exc:
        logger.exception("get_report failed")
        return ToolResult(ok=False, error=str(exc))


# ---------------------------------------------------------------------------
# Playbook + Stage 自省
# ---------------------------------------------------------------------------


@router.get("/playbooks")
async def list_playbooks_endpoint() -> dict:
    from aegi_core.services.stages.playbook import list_playbooks, get_playbook

    names = list_playbooks()
    return {
        "playbooks": [
            {
                "name": n,
                "description": get_playbook(n).description,
                "stages": get_playbook(n).stages,
            }
            for n in names
        ]
    }


@router.get("/stages")
async def list_stages_endpoint() -> dict:
    from aegi_core.services.stages.base import stage_registry

    return {"stages": stage_registry.all_names()}


# ---------------------------------------------------------------------------
# 反向调用端点 (AEGI → OpenClaw)
# ---------------------------------------------------------------------------


class DispatchResearchReq(BaseModel):
    user: str
    query: str
    case_id: str = ""
    timeout: int = 120


class NotifyUserReq(BaseModel):
    user: str
    message: str
    label: str = "system"


@router.post("/dispatch_research", response_model=ToolResult)
async def dispatch_research_endpoint(req: DispatchResearchReq) -> ToolResult:
    """AEGI 触发 OpenClaw crawler agent 去调研某个主题。"""
    try:
        from aegi_core.openclaw.dispatch import dispatch_research

        result = await dispatch_research(
            req.query,
            case_uid=req.case_id,
            user_id=req.user,
            timeout=req.timeout,
        )
        return ToolResult(ok=True, data={"agent_response": result})
    except Exception as exc:
        logger.exception("dispatch_research failed")
        return ToolResult(ok=False, error=str(exc))


@router.post("/notify_user", response_model=ToolResult)
async def notify_user_endpoint(req: NotifyUserReq) -> ToolResult:
    """AEGI 往用户聊天会话里注入一条通知。"""
    try:
        from aegi_core.openclaw.dispatch import notify_user

        ok = await notify_user(req.user, req.message, label=req.label)
        return ToolResult(ok=ok)
    except Exception as exc:
        logger.exception("notify_user failed")
        return ToolResult(ok=False, error=str(exc))
