# Author: msq
"""Tests for narrative intelligence detection.

Source: openspec/changes/narrative-intelligence-detection/tasks.md (3.1–3.3)
Evidence:
  - Narrative chain MUST be replayable to source_claim (spec.md).
  - Coordination detection MUST include false_positive_explanation (spec.md).
  - Conflicting narratives MUST coexist (spec.md).
"""

from __future__ import annotations

import json
from pathlib import Path

from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.services.coordination_detector import detect_coordination
from aegi_core.services.narrative_builder import (
    build_narratives,
    build_narratives_with_uids,
    trace_narrative,
)

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"


def _load_claims(fixture_dir: str) -> list[SourceClaimV1]:
    path = FIXTURES / fixture_dir / "source_claims.json"
    raw = json.loads(path.read_text())
    return [SourceClaimV1.model_validate(c) for c in raw]


# ---------------------------------------------------------------------------
# Fixture 001: single narrative, natural propagation
# ---------------------------------------------------------------------------


class TestNarrative001NaturalPropagation:
    """defgeo-narrative-001: single narrative from 3 claims spread over days."""

    def test_build_produces_single_narrative(self) -> None:
        claims = _load_claims("defgeo-narrative-001")
        narratives = build_narratives(claims, time_window_hours=168.0)
        assert len(narratives) == 1
        assert narratives[0].case_uid == "case-nar-001"

    def test_trace_returns_time_ordered_chain(self) -> None:
        claims = _load_claims("defgeo-narrative-001")
        narratives, uid_map = build_narratives_with_uids(
            claims, time_window_hours=168.0
        )
        assert len(narratives) == 1
        nar = narratives[0]
        chain = trace_narrative(nar.uid, narratives, claims, uid_map)
        assert len(chain) == 3
        # 时间升序
        timestamps = [c["created_at"] for c in chain]
        assert timestamps == sorted(timestamps)
        # 每个节点可追溯到 source_claim
        chain_uids = {c["uid"] for c in chain}
        assert chain_uids == {"sc-nar-001-a", "sc-nar-001-b", "sc-nar-001-c"}

    def test_no_coordination_for_natural_spread(self) -> None:
        claims = _load_claims("defgeo-narrative-001")
        _, uid_map = build_narratives_with_uids(claims, time_window_hours=168.0)
        signals = detect_coordination(uid_map, claims, min_cluster_size=3)
        # 自然传播：时间跨度大，不应触发协同信号
        for s in signals:
            assert s.confidence < 0.6


# ---------------------------------------------------------------------------
# Fixture 002: suspected coordinated propagation
# ---------------------------------------------------------------------------


class TestNarrative002CoordinatedPropagation:
    """defgeo-narrative-002: 5 near-identical claims within 20 minutes."""

    def test_build_produces_single_narrative(self) -> None:
        claims = _load_claims("defgeo-narrative-002")
        narratives = build_narratives(claims, time_window_hours=168.0)
        assert len(narratives) == 1

    def test_coordination_detected_with_explanation(self) -> None:
        claims = _load_claims("defgeo-narrative-002")
        _, uid_map = build_narratives_with_uids(claims, time_window_hours=168.0)
        signals = detect_coordination(
            uid_map, claims, burst_window_hours=1.0, min_cluster_size=3
        )
        assert len(signals) >= 1
        sig = signals[0]
        assert sig.similarity_score > 0.4
        assert sig.time_burst_score > 0.8
        assert sig.confidence > 0.5
        assert sig.false_positive_explanation != ""

    def test_coordination_signal_has_source_claim_uids(self) -> None:
        claims = _load_claims("defgeo-narrative-002")
        _, uid_map = build_narratives_with_uids(claims, time_window_hours=168.0)
        signals = detect_coordination(uid_map, claims, min_cluster_size=3)
        assert len(signals) >= 1
        assert len(signals[0].source_claim_uids) == 5


# ---------------------------------------------------------------------------
# Fixture 003: conflicting narratives coexist
# ---------------------------------------------------------------------------


class TestNarrative003ConflictingNarratives:
    """defgeo-narrative-003: pro vs anti narratives must both survive."""

    def test_conflicting_narratives_coexist(self) -> None:
        claims = _load_claims("defgeo-narrative-003")
        narratives = build_narratives(
            claims, time_window_hours=168.0, similarity_threshold=0.35
        )
        # 正反叙事不应被合并
        assert len(narratives) >= 2, (
            f"Expected >=2 conflicting narratives, got {len(narratives)}"
        )

    def test_each_narrative_traceable(self) -> None:
        claims = _load_claims("defgeo-narrative-003")
        narratives, uid_map = build_narratives_with_uids(
            claims, time_window_hours=168.0, similarity_threshold=0.35
        )
        assert len(narratives) >= 2
        all_traced_uids: set[str] = set()
        for nar in narratives:
            chain = trace_narrative(nar.uid, narratives, claims, uid_map)
            assert len(chain) >= 1
            for node in chain:
                all_traced_uids.add(node["uid"])
        # 所有 claim 都应出现在某条叙事链中
        expected_uids = {c.uid for c in claims}
        assert all_traced_uids == expected_uids


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestNarrativeEdgeCases:
    def test_empty_claims_returns_empty(self) -> None:
        narratives = build_narratives([])
        assert narratives == []

    def test_single_claim_produces_single_narrative(self) -> None:
        claims = _load_claims("defgeo-narrative-001")[:1]
        narratives = build_narratives(claims)
        assert len(narratives) == 1

    def test_coordination_signal_always_has_false_positive_explanation(self) -> None:
        claims = _load_claims("defgeo-narrative-002")
        _, uid_map = build_narratives_with_uids(claims, time_window_hours=168.0)
        signals = detect_coordination(uid_map, claims, min_cluster_size=3)
        for sig in signals:
            assert isinstance(sig.false_positive_explanation, str)
            assert len(sig.false_positive_explanation) > 0
