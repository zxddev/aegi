# Author: msq
"""Pipeline API routes: claim_extract, assertion_fuse, multilingual pipelines.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (3.1, 3.2)
        openspec/changes/multilingual-evidence-chain/design.md (API Contract)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
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


class AssertionFuseRequest(BaseModel):
    source_claim_uids: list[str]


class AssertionFuseResponse(BaseModel):
    assertions: list[AssertionV1] = []


@router.post("/claim_extract", response_model=ClaimExtractResponse)
async def claim_extract_endpoint(
    case_uid: str,
    body: ClaimExtractRequest,
) -> ClaimExtractResponse:
    """Extract claims from a chunk (stub — real impl via DI)."""
    return ClaimExtractResponse()


@router.post("/assertion_fuse", response_model=AssertionFuseResponse)
async def assertion_fuse_endpoint(
    case_uid: str,
    body: AssertionFuseRequest,
) -> AssertionFuseResponse:
    """Fuse claims into assertions (stub — real impl via DI)."""
    return AssertionFuseResponse()


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
