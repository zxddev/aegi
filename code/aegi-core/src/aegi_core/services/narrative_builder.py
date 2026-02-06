# Author: msq
"""Narrative builder – clustering + source tracing.

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - Clustering: semantic similarity + time window constraint.
  - Tracing: earliest created_at = source node.
  - Conflicting narratives MUST coexist (spec.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher

from aegi_core.contracts.schemas import NarrativeV1, SourceClaimV1


def _similarity(a: str, b: str) -> float:
    """Token-overlap similarity ratio."""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def build_narratives(
    claims: list[SourceClaimV1],
    *,
    time_window_hours: float = 168.0,
    similarity_threshold: float = 0.35,
) -> list[NarrativeV1]:
    """Cluster source claims into narratives by semantic similarity within a time window.

    Args:
        claims: Source claims to cluster.
        time_window_hours: Max hours between first and last claim in a cluster.
        similarity_threshold: Min similarity ratio to join a cluster.

    Returns:
        List of NarrativeV1 (one per cluster). Conflicting narratives are preserved.
    """
    if not claims:
        return []

    sorted_claims = sorted(claims, key=lambda c: c.created_at)
    clusters: list[list[SourceClaimV1]] = []

    for claim in sorted_claims:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            time_diff = abs((claim.created_at - representative.created_at).total_seconds())
            if time_diff > time_window_hours * 3600:
                continue
            if _similarity(claim.quote, representative.quote) >= similarity_threshold:
                cluster.append(claim)
                placed = True
                break
        if not placed:
            clusters.append([claim])

    now = datetime.now(timezone.utc)
    narratives: list[NarrativeV1] = []
    for cluster in clusters:
        narratives.append(
            NarrativeV1(
                uid=f"nar-{uuid.uuid4().hex[:12]}",
                case_uid=cluster[0].case_uid,
                title=cluster[0].quote[:120],
                assertion_uids=[],
                hypothesis_uids=[],
                created_at=now,
            )
        )
    return narratives


def trace_narrative(
    narrative_uid: str,
    narratives: list[NarrativeV1],
    claims: list[SourceClaimV1],
    source_claim_uids_map: dict[str, list[str]],
) -> list[dict]:
    """Return time-ordered propagation chain for a narrative.

    Args:
        narrative_uid: UID of the narrative to trace.
        narratives: All built narratives.
        claims: All source claims.
        source_claim_uids_map: Mapping narrative_uid -> source_claim_uids.

    Returns:
        List of dicts with uid, quote, attributed_to, created_at (sorted by time).
    """
    sc_uids = source_claim_uids_map.get(narrative_uid, [])
    claim_map = {c.uid: c for c in claims}
    chain = []
    for uid in sc_uids:
        c = claim_map.get(uid)
        if c:
            chain.append({
                "uid": c.uid,
                "quote": c.quote,
                "attributed_to": c.attributed_to,
                "created_at": c.created_at.isoformat(),
            })
    chain.sort(key=lambda x: x["created_at"])
    return chain


def build_narratives_with_uids(
    claims: list[SourceClaimV1],
    *,
    time_window_hours: float = 168.0,
    similarity_threshold: float = 0.35,
) -> tuple[list[NarrativeV1], dict[str, list[str]]]:
    """Build narratives and return (narratives, {narrative_uid: [source_claim_uids]}).

    Same clustering logic as build_narratives but also returns the UID mapping
    needed for tracing and coordination detection.
    """
    if not claims:
        return [], {}

    sorted_claims = sorted(claims, key=lambda c: c.created_at)
    clusters: list[list[SourceClaimV1]] = []

    for claim in sorted_claims:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            time_diff = abs((claim.created_at - representative.created_at).total_seconds())
            if time_diff > time_window_hours * 3600:
                continue
            if _similarity(claim.quote, representative.quote) >= similarity_threshold:
                cluster.append(claim)
                placed = True
                break
        if not placed:
            clusters.append([claim])

    now = datetime.now(timezone.utc)
    narratives: list[NarrativeV1] = []
    uid_map: dict[str, list[str]] = {}
    for cluster in clusters:
        sc_uids = [c.uid for c in cluster]
        nar_uid = f"nar-{uuid.uuid4().hex[:12]}"
        narratives.append(
            NarrativeV1(
                uid=nar_uid,
                case_uid=cluster[0].case_uid,
                title=cluster[0].quote[:120],
                assertion_uids=[],
                hypothesis_uids=[],
                created_at=now,
            )
        )
        uid_map[nar_uid] = sc_uids
    return narratives, uid_map
