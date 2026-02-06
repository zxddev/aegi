# Author: msq
"""Pipeline API routes: detect_language, translate_claims, align_entities.

Source: openspec/changes/multilingual-evidence-chain/design.md
Evidence: API Contract — 3 POST endpoints under /cases/{case_uid}/pipelines/.
"""

from __future__ import annotations

from fastapi import APIRouter

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
        body.claims,
        body.target_language,
        body.budget_context,
    )


@router.post("/align_entities_cross_lingual", response_model=AlignEntitiesResponse)
async def align_entities_endpoint(
    case_uid: str,
    body: AlignEntitiesRequest,
) -> AlignEntitiesResponse:
    """跨语言实体对齐。"""
    return await align_entities(body.claims, body.budget_context)
