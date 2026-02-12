# Author: msq
"""叙事 API 路由 – 构建、协同检测、溯源。

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - POST /cases/{case_uid}/narratives/build
  - POST /cases/{case_uid}/narratives/detect_coordination
  - GET /cases/{case_uid}/narratives/{narrative_uid}/trace
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.contracts.schemas import NarrativeV1, SourceClaimV1
from aegi_core.db.models.action import Action
from aegi_core.db.models.narrative import Narrative
from aegi_core.infra.llm_client import LLMClient
from aegi_core.services.coordination_detector import (
    CoordinationSignalV1,
    detect_coordination,
)
from aegi_core.services.narrative_builder import (
    abuild_narratives_with_uids,
    build_narratives_with_uids,
    trace_narrative,
)


router = APIRouter(prefix="/cases/{case_uid}/narratives", tags=["narratives"])


class BuildRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    time_window_hours: float = 168.0
    similarity_threshold: float = 0.35


class BuildResponse(BaseModel):
    narratives: list[NarrativeV1]
    source_claim_uids_map: dict[str, list[str]]
    action_uid: str


class DetectCoordinationRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    time_window_hours: float = 168.0
    similarity_threshold: float = 0.35
    burst_window_hours: float = 1.0
    coordination_similarity_threshold: float = 0.5
    min_cluster_size: int = 3


class DetectCoordinationResponse(BaseModel):
    signals: list[CoordinationSignalV1]
    action_uid: str


class TraceRequest(BaseModel):
    source_claims: list[SourceClaimV1]
    narratives: list[NarrativeV1]
    source_claim_uids_map: dict[str, list[str]]


class TraceResponse(BaseModel):
    narrative_uid: str
    chain: list[dict]


@router.post("/build")
async def build(
    case_uid: str,
    req: BuildRequest,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
) -> BuildResponse:
    """从 source claims 聚类 + 溯源构建叙事。"""
    # LLM 可用时用 embedding cosine similarity，否则 fallback 到 token-overlap
    try:
        embed_fn = llm.embed
    except Exception:  # noqa: BLE001
        embed_fn = None

    narratives, uid_map = await abuild_narratives_with_uids(
        req.source_claims,
        embed_fn=embed_fn,
        time_window_hours=req.time_window_hours,
        similarity_threshold=req.similarity_threshold,
    )

    for nar in narratives:
        sc_uids = uid_map.get(nar.uid, [])
        first_ts = min(
            (sc.created_at for sc in req.source_claims if sc.uid in sc_uids),
            default=nar.created_at,
        )
        last_ts = max(
            (sc.created_at for sc in req.source_claims if sc.uid in sc_uids),
            default=nar.created_at,
        )
        session.add(
            Narrative(
                uid=nar.uid,
                case_uid=case_uid,
                theme=nar.title,
                source_claim_uids=sc_uids,
                first_seen_at=first_ts,
                latest_seen_at=last_ts,
            )
        )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="narratives.build",
            inputs={"source_claim_count": len(req.source_claims)},
            outputs={"narrative_uids": [n.uid for n in narratives]},
        )
    )
    await session.commit()

    return BuildResponse(
        narratives=narratives,
        source_claim_uids_map=uid_map,
        action_uid=action_uid,
    )


@router.post("/detect_coordination")
async def detect(
    case_uid: str,
    req: DetectCoordinationRequest,
    session: AsyncSession = Depends(get_db_session),
    llm: LLMClient = Depends(get_llm_client),
) -> DetectCoordinationResponse:
    """检测协同传播模式。"""
    # 预计算 embedding 用于 cosine similarity
    embeddings: dict[str, list[float]] | None = None
    try:
        import asyncio

        tasks = [llm.embed(c.quote) for c in req.source_claims]
        vectors = await asyncio.gather(*tasks)
        embeddings = {c.uid: v for c, v in zip(req.source_claims, vectors)}
    except Exception:  # noqa: BLE001
        pass  # fallback 到 token-overlap

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
        embeddings=embeddings,
    )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="narratives.detect_coordination",
            inputs={"source_claim_count": len(req.source_claims)},
            outputs={"signal_count": len(signals)},
        )
    )
    await session.commit()

    return DetectCoordinationResponse(signals=signals, action_uid=action_uid)


@router.post("/{narrative_uid}/trace")
async def trace(case_uid: str, narrative_uid: str, req: TraceRequest) -> TraceResponse:
    """按时间顺序溯源叙事到 source claims。"""
    chain = trace_narrative(
        narrative_uid, req.narratives, req.source_claims, req.source_claim_uids_map
    )
    return TraceResponse(narrative_uid=narrative_uid, chain=chain)
