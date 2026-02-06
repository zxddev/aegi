# Author: msq
"""Coordination detection – time-burst + similarity analysis.

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - Short-time high-similarity batch propagation = suspected coordination.
  - Output MUST include false_positive_explanation (spec.md).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from aegi_core.contracts.schemas import SourceClaimV1


class CoordinationSignalV1(BaseModel):
    """Coordination detection output (local to this feature, not in shared contracts)."""

    group_id: str
    narrative_uid: str
    source_claim_uids: list[str] = Field(default_factory=list)
    similarity_score: float
    time_burst_score: float
    confidence: float
    false_positive_explanation: str


def _pairwise_similarity(quotes: list[str]) -> float:
    """Average pairwise token-overlap similarity."""
    if len(quotes) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(quotes)):
        for j in range(i + 1, len(quotes)):
            total += SequenceMatcher(
                None, quotes[i].lower().split(), quotes[j].lower().split()
            ).ratio()
            count += 1
    return total / count if count else 0.0


def _time_burst_score(claims: list[SourceClaimV1], burst_window_hours: float) -> float:
    """Fraction of claims that fall within the burst window from the earliest."""
    if len(claims) < 2:
        return 0.0
    sorted_c = sorted(claims, key=lambda c: c.created_at)
    earliest = sorted_c[0].created_at
    window = timedelta(hours=burst_window_hours)
    in_window = sum(1 for c in sorted_c if (c.created_at - earliest) <= window)
    return in_window / len(claims)


def detect_coordination(
    source_claim_uids_map: dict[str, list[str]],
    claims: list[SourceClaimV1],
    *,
    burst_window_hours: float = 1.0,
    similarity_threshold: float = 0.5,
    min_cluster_size: int = 3,
    confidence_threshold: float = 0.6,
) -> list[CoordinationSignalV1]:
    """Detect coordinated propagation patterns across narrative clusters.

    Args:
        source_claim_uids_map: Mapping narrative_uid -> source_claim_uids.
        claims: All source claims.
        burst_window_hours: Time window for burst detection.
        similarity_threshold: Min avg similarity to flag coordination.
        min_cluster_size: Min claims in a cluster to consider.
        confidence_threshold: Below this, mark as low_confidence.

    Returns:
        List of CoordinationSignalV1 signals.
    """
    claim_map = {c.uid: c for c in claims}
    signals: list[CoordinationSignalV1] = []

    for nar_uid, sc_uids in source_claim_uids_map.items():
        cluster_claims = [claim_map[uid] for uid in sc_uids if uid in claim_map]
        if len(cluster_claims) < min_cluster_size:
            continue

        quotes = [c.quote for c in cluster_claims]
        sim = _pairwise_similarity(quotes)
        burst = _time_burst_score(cluster_claims, burst_window_hours)
        confidence = (sim + burst) / 2.0

        if sim < similarity_threshold:
            continue

        explanation = ""
        if confidence < confidence_threshold:
            explanation = (
                f"low_confidence: similarity={sim:.2f}, burst={burst:.2f}; "
                "natural propagation cannot be ruled out"
            )
        else:
            explanation = (
                f"high similarity ({sim:.2f}) with time burst ({burst:.2f}) "
                "suggests coordinated dissemination"
            )

        signals.append(
            CoordinationSignalV1(
                group_id=f"coord-{uuid.uuid4().hex[:8]}",
                narrative_uid=nar_uid,
                source_claim_uids=sc_uids,
                similarity_score=round(sim, 4),
                time_burst_score=round(burst, 4),
                confidence=round(confidence, 4),
                false_positive_explanation=explanation,
            )
        )

    return signals
