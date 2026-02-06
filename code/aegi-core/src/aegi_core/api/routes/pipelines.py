# Author: msq
"""Pipeline API routes: claim_extract, assertion_fuse, multilingual pipelines.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (3.1, 3.2)
        openspec/changes/multilingual-evidence-chain/design.md (API Contract)
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.db.models.action import Action
from aegi_core.db.models.assertion import Assertion as AssertionRow
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.services.assertion_fuser import fuse_claims
from aegi_core.services.claim_extractor import LLMBackend
from aegi_core.services.claim_extractor import extract_from_chunk as svc_extract
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
    """Extract claims from a chunk."""
    budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)
    claims, svc_action, svc_trace, _ = await svc_extract(
        chunk_uid=body.chunk_uid,
        chunk_text=body.chunk_text,
        anchor_set=[],
        artifact_version_uid="",
        evidence_uid="",
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
    """Fuse claims into assertions."""
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


# -- Multilingual evidence chain endpoints -------------------------------------


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
    return await translate_claims(body.claims, body.target_language, body.budget_context)


@router.post("/align_entities_cross_lingual", response_model=AlignEntitiesResponse)
async def align_entities_endpoint(
    case_uid: str,
    body: AlignEntitiesRequest,
) -> AlignEntitiesResponse:
    """跨语言实体对齐。"""
    return await align_entities(body.claims, body.budget_context)
