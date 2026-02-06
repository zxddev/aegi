# Author: msq
"""Narrative API routes – build, detect coordination, trace.

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - POST /cases/{case_uid}/narratives/build
  - POST /cases/{case_uid}/narratives/detect_coordination
  - GET /cases/{case_uid}/narratives/{narrative_uid}/trace
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aegi_core.contracts.schemas import NarrativeV1, SourceClaimV1
from aegi_core.services.coordination_detector import CoordinationSignalV1, detect_coordination
from aegi_core.services.narrative_builder import build_narratives_with_uids, trace_narrative


router = APIRouter(prefix="/cases/{case_uid}/narratives", tags=["narratives"])


class BuildRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    time_window_hours: float = 168.0
    similarity_threshold: float = 0.35


class BuildResponse(BaseModel):
    narratives: list[NarrativeV1]
    source_claim_uids_map: dict[str, list[str]]


class DetectCoordinationRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    time_window_hours: float = 168.0
    similarity_threshold: float = 0.35
    burst_window_hours: float = 1.0
    coordination_similarity_threshold: float = 0.5
    min_cluster_size: int = 3


class DetectCoordinationResponse(BaseModel):
    signals: list[CoordinationSignalV1]


class TraceRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    narratives: list[NarrativeV1]
    source_claim_uids_map: dict[str, list[str]]


class TraceResponse(BaseModel):
    narrative_uid: str
    chain: list[dict]


@router.post("/build")
async def build(case_uid: str, req: BuildRequest) -> BuildResponse:
    """Build narratives from source claims via clustering + tracing."""
    narratives, uid_map = build_narratives_with_uids(
        req.source_claims,
        time_window_hours=req.time_window_hours,
        similarity_threshold=req.similarity_threshold,
    )
    return BuildResponse(narratives=narratives, source_claim_uids_map=uid_map)


@router.post("/detect_coordination")
async def detect(case_uid: str, req: DetectCoordinationRequest) -> DetectCoordinationResponse:
    """Detect coordinated propagation patterns."""
    narratives, uid_map = build_narratives_with_uids(
        req.source_claims,
        time_window_hours=req.time_window_hours,
        similarity_threshold=req.similarity_threshold,
    )
    signals = detect_coordination(
        uid_map,
        req.source_claims,
        burst_window_hours=req.burst_window_hours,
        similarity_threshold=req.coordination_similarity_threshold,
        min_cluster_size=req.min_cluster_size,
    )
    return DetectCoordinationResponse(signals=signals)


@router.post("/{narrative_uid}/trace")
async def trace(case_uid: str, narrative_uid: str, req: TraceRequest) -> TraceResponse:
    """Trace a narrative back to its source claims in time order."""
    chain = trace_narrative(
        narrative_uid, req.narratives, req.source_claims, req.source_claim_uids_map
    )
    return TraceResponse(narrative_uid=narrative_uid, chain=chain)
