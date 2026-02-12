# Author: msq
"""流水线 API 路由：claim_extract、assertion_fuse、多语言流水线。

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (3.1, 3.2)
        openspec/changes/multilingual-evidence-chain/design.md (API Contract)
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client, get_tool_client
from aegi_core.api.errors import AegiHTTPError
from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.db.models.action import Action
from aegi_core.db.models.assertion import Assertion as AssertionRow
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.assertion_fuser import fuse_claims
from aegi_core.services.claim_extractor import LLMBackend
from aegi_core.services.claim_extractor import extract_from_chunk as svc_extract
from aegi_core.services.tool_client import ToolClient
from aegi_core.services.tool_parse_service import call_tool_doc_parse
from aegi_core.services.entity_alignment import (
    AlignEntitiesRequest,
    AlignEntitiesResponse,
    align_entities,
)
from aegi_core.services.multilingual_pipeline import (
    DetectLanguageRequest,
    DetectLanguageResponse,
    TranslateClaimsRequest,
    TranslateClaimsResponse,
    detect_language,
    translate_claims,
)

router = APIRouter(prefix="/cases/{case_uid}/pipelines", tags=["pipelines"])


class ClaimExtractRequest(BaseModel):
    chunk_uid: str
    chunk_text: str


class ClaimExtractResponse(BaseModel):
    claims: list[SourceClaimV1] = []
    action_uid: str = ""


class AssertionFuseRequest(BaseModel):
    source_claim_uids: list[str]


class AssertionFuseResponse(BaseModel):
    assertions: list[AssertionV1] = []
    conflicts: list[dict] = []
    action_uid: str = ""


@router.post("/claim_extract", response_model=ClaimExtractResponse)
async def claim_extract_endpoint(
    case_uid: str,
    body: ClaimExtractRequest,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMBackend = Depends(get_llm_client),
) -> ClaimExtractResponse:
    """从 chunk 中提取 claims。"""
    # 从 DB 查 chunk 关联的真实元数据
    from aegi_core.db.models.chunk import Chunk
    from aegi_core.db.models.evidence import Evidence

    chunk_row = (
        await session.execute(sa.select(Chunk).where(Chunk.uid == body.chunk_uid))
    ).scalar_one_or_none()
    anchor_set = chunk_row.anchor_set if chunk_row else []
    artifact_version_uid = chunk_row.artifact_version_uid if chunk_row else ""

    ev_row = (
        await session.execute(
            sa.select(Evidence.uid).where(Evidence.chunk_uid == body.chunk_uid)
        )
    ).scalar_one_or_none()
    evidence_uid = ev_row or ""

    budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)
    claims, svc_action, svc_trace, _ = await svc_extract(
        chunk_uid=body.chunk_uid,
        chunk_text=body.chunk_text,
        anchor_set=anchor_set,
        artifact_version_uid=artifact_version_uid,
        evidence_uid=evidence_uid,
        case_uid=case_uid,
        llm=llm,
        budget=budget,
    )

    for c in claims:
        session.add(
            SourceClaim(
                uid=c.uid,
                case_uid=c.case_uid,
                artifact_version_uid=c.artifact_version_uid or "pending",
                chunk_uid=c.chunk_uid,
                evidence_uid=c.evidence_uid or "pending",
                quote=c.quote,
                selectors=c.selectors,
                attributed_to=c.attributed_to,
                modality=c.modality.value if c.modality else None,
            )
        )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="pipelines.claim_extract",
            inputs={"chunk_uid": body.chunk_uid},
            outputs={"source_claim_uids": [c.uid for c in claims]},
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    return ClaimExtractResponse(claims=claims, action_uid=action_uid)


@router.post("/assertion_fuse", response_model=AssertionFuseResponse)
async def assertion_fuse_endpoint(
    case_uid: str,
    body: AssertionFuseRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AssertionFuseResponse:
    """融合 claims 为 assertions。"""
    rows = await session.execute(
        sa.select(SourceClaim).where(SourceClaim.uid.in_(body.source_claim_uids))
    )
    sc_rows = rows.scalars().all()

    claims_v1: list[SourceClaimV1] = []
    for r in sc_rows:
        claims_v1.append(
            SourceClaimV1(
                uid=r.uid,
                case_uid=r.case_uid,
                artifact_version_uid=r.artifact_version_uid,
                chunk_uid=r.chunk_uid,
                evidence_uid=r.evidence_uid,
                quote=r.quote,
                selectors=r.selectors,
                attributed_to=r.attributed_to,
                modality=r.modality,
                created_at=r.created_at,
            )
        )

    assertions, conflicts, svc_action, svc_trace = fuse_claims(
        claims_v1,
        case_uid=case_uid,
    )

    for a in assertions:
        session.add(
            AssertionRow(
                uid=a.uid,
                case_uid=a.case_uid,
                kind=a.kind,
                value=a.value,
                source_claim_uids=a.source_claim_uids,
                confidence=a.confidence,
                modality=a.modality.value if a.modality else None,
            )
        )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="pipelines.assertion_fuse",
            inputs={"source_claim_uids": body.source_claim_uids},
            outputs={
                "assertion_uids": [a.uid for a in assertions],
                "conflict_count": len(conflicts),
            },
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    return AssertionFuseResponse(
        assertions=assertions,
        conflicts=conflicts,
        action_uid=action_uid,
    )


# -- 多语言证据链端点 -------------------------------------


@router.post("/detect_language", response_model=DetectLanguageResponse)
async def detect_language_endpoint(
    case_uid: str,
    body: DetectLanguageRequest,
) -> DetectLanguageResponse:
    """检测 claims 语言。"""
    return await detect_language(body.claims)


@router.post("/translate_claims", response_model=TranslateClaimsResponse)
async def translate_claims_endpoint(
    case_uid: str,
    body: TranslateClaimsRequest,
) -> TranslateClaimsResponse:
    """翻译 claims 到目标语言。"""
    return await translate_claims(
        body.claims, body.target_language, body.budget_context
    )


@router.post("/align_entities_cross_lingual", response_model=AlignEntitiesResponse)
async def align_entities_endpoint(
    case_uid: str,
    body: AlignEntitiesRequest,
) -> AlignEntitiesResponse:
    """跨语言实体对齐。"""
    return await align_entities(body.claims, body.budget_context)


# -- 摄取：doc_parse → Chunk/Evidence 入库 --------------------------------


class IngestRequest(BaseModel):
    artifact_version_uid: str = Field(description="工件版本唯一标识符")
    file_url: str = Field(description="要处理的文件URL地址")


class IngestResponse(BaseModel):
    action_uid: str = Field(default="", description="操作记录的唯一标识符")
    tool_trace_uid: str = Field(default="", description="工具调用跟踪标识符")
    chunk_uids: list[str] = Field(default=[], description="生成的文本块唯一标识符列表")
    evidence_uids: list[str] = Field(default=[], description="生成的证据唯一标识符列表")


class IngestAndExtractResponse(BaseModel):
    action_uid: str = Field(default="", description="操作记录的唯一标识符")
    tool_trace_uid: str = Field(default="", description="工具调用跟踪标识符")
    chunk_uids: list[str] = Field(default=[], description="生成的文本块唯一标识符列表")
    evidence_uids: list[str] = Field(default=[], description="生成的证据唯一标识符列表")
    source_claim_uids: list[str] = Field(
        default=[], description="提取的源声明唯一标识符列表"
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="文档摄取",
    description="解析文档并将其转换为文本块和证据，存储到数据库中供后续声明提取使用",
)
async def ingest_endpoint(
    case_uid: str,
    body: IngestRequest,
    session: AsyncSession = Depends(get_db_session),
    tool: ToolClient = Depends(get_tool_client),
) -> IngestResponse:
    """doc_parse → Chunk/Evidence 入库，返回 chunk_uids 供下游 claim_extract 消费。"""
    try:
        result = await call_tool_doc_parse(
            session,
            tool,
            case_uid=case_uid,
            artifact_version_uid=body.artifact_version_uid,
            file_url=body.file_url,
            actor_id=None,
            rationale="pipelines.ingest",
            inputs={
                "artifact_version_uid": body.artifact_version_uid,
                "file_url": body.file_url,
            },
        )
        return IngestResponse(
            action_uid=result["action_uid"],
            tool_trace_uid=result["tool_trace_uid"],
            chunk_uids=result.get("chunk_uids", []),
            evidence_uids=result.get("evidence_uids", []),
        )
    except Exception as e:
        raise AegiHTTPError(502, "gateway_error", str(e), {}) from e


@router.post(
    "/ingest_and_extract",
    response_model=IngestAndExtractResponse,
    summary="文档摄取与声明提取",
    description="一站式处理：解析文档生成文本块，然后自动从每个文本块中提取声明",
)
async def ingest_and_extract_endpoint(
    case_uid: str,
    body: IngestRequest,
    session: AsyncSession = Depends(get_db_session),
    tool: ToolClient = Depends(get_tool_client),
    llm: LLMBackend = Depends(get_llm_client),
) -> IngestAndExtractResponse:
    """ingest → claim_extract 自动串联。"""
    try:
        from aegi_core.db.models.chunk import Chunk
        from aegi_core.db.models.evidence import Evidence

        # Step 1: 摄取
        ingest_result = await call_tool_doc_parse(
            session,
            tool,
            case_uid=case_uid,
            artifact_version_uid=body.artifact_version_uid,
            file_url=body.file_url,
            actor_id=None,
            rationale="pipelines.ingest_and_extract",
            inputs={
                "artifact_version_uid": body.artifact_version_uid,
                "file_url": body.file_url,
            },
        )

        chunk_uids = ingest_result.get("chunk_uids", [])
        all_source_claim_uids = []

        # Step 2: 从每个 chunk 提取 claims
        budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)

        for chunk_uid in chunk_uids:
            chunk_row = (
                await session.execute(sa.select(Chunk).where(Chunk.uid == chunk_uid))
            ).scalar_one_or_none()

            if not chunk_row:
                continue

            ev_row = (
                await session.execute(
                    sa.select(Evidence.uid).where(Evidence.chunk_uid == chunk_uid)
                )
            ).scalar_one_or_none()
            evidence_uid = ev_row or ""

            claims, _, _, _ = await svc_extract(
                chunk_uid=chunk_uid,
                chunk_text=chunk_row.text,
                anchor_set=chunk_row.anchor_set,
                artifact_version_uid=chunk_row.artifact_version_uid,
                evidence_uid=evidence_uid,
                case_uid=case_uid,
                llm=llm,
                budget=budget,
            )

            for c in claims:
                session.add(
                    SourceClaim(
                        uid=c.uid,
                        case_uid=c.case_uid,
                        artifact_version_uid=c.artifact_version_uid or "pending",
                        chunk_uid=c.chunk_uid,
                        evidence_uid=c.evidence_uid or "pending",
                        quote=c.quote,
                        selectors=c.selectors,
                        attributed_to=c.attributed_to,
                        modality=c.modality.value if c.modality else None,
                    )
                )

            all_source_claim_uids.extend([c.uid for c in claims])

        # Step 3: 创建 action 记录
        action_uid = f"act_{uuid4().hex}"
        session.add(
            Action(
                uid=action_uid,
                case_uid=case_uid,
                action_type="pipelines.ingest_and_extract",
                inputs={
                    "artifact_version_uid": body.artifact_version_uid,
                    "file_url": body.file_url,
                },
                outputs={
                    "chunk_uids": chunk_uids,
                    "evidence_uids": ingest_result.get("evidence_uids", []),
                    "source_claim_uids": all_source_claim_uids,
                },
                trace_id=ingest_result["tool_trace_uid"],
            )
        )
        await session.commit()

        return IngestAndExtractResponse(
            action_uid=action_uid,
            tool_trace_uid=ingest_result["tool_trace_uid"],
            chunk_uids=chunk_uids,
            evidence_uids=ingest_result.get("evidence_uids", []),
            source_claim_uids=all_source_claim_uids,
        )
    except Exception as e:
        raise AegiHTTPError(502, "gateway_error", str(e), {}) from e


# -- 归档优先流水线：archive_url → ArtifactVersion → ingest ----------


class ArchiveAndIngestRequest(BaseModel):
    url: str = Field(description="要归档并摄取的源 URL")


class ArchiveAndIngestResponse(BaseModel):
    artifact_version_uid: str = Field(description="创建的工件版本 UID")
    archive_action_uid: str = Field(description="归档操作 UID")
    ingest_action_uid: str = Field(default="", description="摄取操作 UID")
    tool_trace_uid: str = Field(default="", description="摄取工具跟踪 UID")
    chunk_uids: list[str] = Field(default=[], description="生成的文本块 UID 列表")
    evidence_uids: list[str] = Field(default=[], description="生成的证据 UID 列表")


@router.post(
    "/archive_and_ingest",
    response_model=ArchiveAndIngestResponse,
    summary="归档并摄取",
    description="归档 URL → 创建 ArtifactVersion → doc_parse 摄取，一站式完成",
)
async def archive_and_ingest_endpoint(
    case_uid: str,
    body: ArchiveAndIngestRequest,
    session: AsyncSession = Depends(get_db_session),
    tool: ToolClient = Depends(get_tool_client),
) -> ArchiveAndIngestResponse:
    """archive_url → ArtifactIdentity/Version → doc_parse 入库。"""
    from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
    from aegi_core.services.tool_archive_service import call_tool_archive_url

    try:
        # Step 1: 归档
        archive_result = await call_tool_archive_url(
            session,
            tool,
            case_uid=case_uid,
            url=body.url,
            actor_id=None,
            rationale="pipelines.archive_and_ingest",
            inputs={"url": body.url},
        )

        # Step 2: 创建 ArtifactIdentity + ArtifactVersion
        ai_uid = f"ai_{uuid4().hex}"
        av_uid = f"av_{uuid4().hex}"
        resp = archive_result.get("response", {})
        snapshot = resp.get("snapshot") if isinstance(resp, dict) else None

        session.add(ArtifactIdentity(uid=ai_uid, kind="url", canonical_url=body.url))
        session.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=ai_uid,
                case_uid=case_uid,
                storage_ref=snapshot.get("archive_path") if snapshot else None,
                content_type="text/html",
                source_meta={"url": body.url, "snapshot": snapshot},
            )
        )
        await session.flush()

        # Step 3: 摄取 (doc_parse)
        ingest_result = await call_tool_doc_parse(
            session,
            tool,
            case_uid=case_uid,
            artifact_version_uid=av_uid,
            file_url=body.url,
            actor_id=None,
            rationale="pipelines.archive_and_ingest.ingest",
            inputs={"artifact_version_uid": av_uid, "file_url": body.url},
        )
        await session.commit()

        return ArchiveAndIngestResponse(
            artifact_version_uid=av_uid,
            archive_action_uid=archive_result["action_uid"],
            ingest_action_uid=ingest_result["action_uid"],
            tool_trace_uid=ingest_result["tool_trace_uid"],
            chunk_uids=ingest_result.get("chunk_uids", []),
            evidence_uids=ingest_result.get("evidence_uids", []),
        )
    except AegiHTTPError:
        raise
    except Exception as e:
        raise AegiHTTPError(502, "gateway_error", str(e), {}) from e
