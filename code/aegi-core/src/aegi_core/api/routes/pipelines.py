# Author: msq
"""Pipeline API routes: claim_extract, assertion_fuse.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (3.1, 3.2)
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1

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
