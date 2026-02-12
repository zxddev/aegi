# Author: msq
"""Tests for assertion fusion pipeline.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (4.4)
Evidence:
  - Assertions MUST be derived from SourceClaims (spec.md).
  - Assertion without source claims is rejected (spec.md scenario).
  - Contradicting claims MUST produce conflict_set (spec.md scenario).
  - Conflict set MUST be explicit and replayable (spec.md).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


from aegi_core.contracts.schemas import AssertionV1, Modality, SourceClaimV1
from aegi_core.services.assertion_fuser import fuse_claims

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"


def _make_claim(
    uid: str,
    quote: str,
    *,
    attributed_to: str | None = None,
    case_uid: str = "case_test",
) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid=case_uid,
        artifact_version_uid="av_test",
        chunk_uid="chunk_test",
        evidence_uid="ev_test",
        quote=quote,
        selectors=[{"type": "TextQuoteSelector", "exact": quote}],
        attributed_to=attributed_to,
        modality=Modality.TEXT,
        created_at=datetime.now(timezone.utc),
    )


def test_fuse_normal_scenario() -> None:
    """defgeo-claim-001: normal fusion produces assertions linked to claims."""
    fixture_dir = FIXTURES / "defgeo-claim-001"
    sc_data = json.loads((fixture_dir / "source_claims.json").read_text())

    claims = [
        _make_claim(
            uid=sc["source_claim_uid"],
            quote=sc["quote"],
            attributed_to=sc.get("attributed_to"),
        )
        for sc in sc_data["source_claims"]
    ]

    assertions, conflict_set, action, tool_trace = fuse_claims(
        claims, case_uid="case_test"
    )

    assert len(assertions) > 0
    for a in assertions:
        assert isinstance(a, AssertionV1)
        assert len(a.source_claim_uids) > 0, "Assertion MUST have source_claim_uids"
        assert a.kind == "fused_claim"

    # 正常场景无冲突
    assert conflict_set == []
    assert action.action_type == "assertion_fuse"
    assert tool_trace.status == "ok"


def test_fuse_empty_claims_rejected() -> None:
    """Assertion without source claims MUST be rejected (spec.md scenario)."""
    assertions, conflict_set, action, tool_trace = fuse_claims([], case_uid="case_test")

    assert assertions == []
    assert conflict_set == []
    assert tool_trace.status == "rejected"
    assert "empty" in action.rationale.lower()


def test_fuse_conflict_scenario() -> None:
    """defgeo-claim-002: contradicting claims MUST produce conflict_set."""
    fixture_dir = FIXTURES / "defgeo-claim-002"
    sc_data = json.loads((fixture_dir / "source_claims.json").read_text())

    claims = [
        _make_claim(
            uid=sc["source_claim_uid"],
            quote=sc["quote"],
            attributed_to=sc.get("attributed_to"),
        )
        for sc in sc_data["source_claims"]
    ]

    assertions, conflict_set, action, tool_trace = fuse_claims(
        claims, case_uid="case_test"
    )

    assert len(assertions) > 0
    assert len(conflict_set) > 0, "Contradicting claims MUST produce conflict_set"

    conflict_types = {c["conflict_type"] for c in conflict_set}
    assert "value_conflict" in conflict_types or "modality_conflict" in conflict_types

    for conflict in conflict_set:
        assert "claim_uid_a" in conflict
        assert "claim_uid_b" in conflict
        assert "rationale" in conflict

    assert action.trace_id is not None
    assert tool_trace.status == "ok"


def test_fuse_conflict_stability() -> None:
    """Conflict set output MUST be stable across repeated runs (Acceptance #2)."""
    claim_a = _make_claim(
        "sc_a",
        "Exampleland confirmed deployment of warships.",
        attributed_to="Exampleland",
    )
    claim_b = _make_claim(
        "sc_b",
        "Exampleland denied any military deployment.",
        attributed_to="Exampleland",
    )

    results = []
    for _ in range(3):
        _, conflict_set, _, _ = fuse_claims([claim_a, claim_b], case_uid="case_stable")
        results.append(conflict_set)

    # 冲突类型和涉及的 claim uid 必须稳定
    for r in results[1:]:
        assert len(r) == len(results[0])
        for c1, c2 in zip(results[0], r):
            assert c1["conflict_type"] == c2["conflict_type"]
            assert c1["claim_uid_a"] == c2["claim_uid_a"]
            assert c1["claim_uid_b"] == c2["claim_uid_b"]


def test_fuse_preserves_conflicts_no_overwrite() -> None:
    """Conflicts MUST be preserved, not overwritten (task 2.3)."""
    claim_a = _make_claim(
        "sc_preserve_a",
        "Exampleland confirmed the operation.",
        attributed_to="Exampleland",
    )
    claim_b = _make_claim(
        "sc_preserve_b",
        "Exampleland denied the operation.",
        attributed_to="Exampleland",
    )

    assertions, conflict_set, _, _ = fuse_claims(
        [claim_a, claim_b], case_uid="case_preserve"
    )

    # 两条冲突 claim 都必须出现在 assertion 的 source_claim_uids 中
    all_source_uids = set()
    for a in assertions:
        all_source_uids.update(a.source_claim_uids)

    assert "sc_preserve_a" in all_source_uids
    assert "sc_preserve_b" in all_source_uids

    # assertion 的 value 必须标记 has_conflict
    for a in assertions:
        if "sc_preserve_a" in a.source_claim_uids:
            assert a.value.get("has_conflict") is True


def test_fuse_outputs_ds_metadata_and_continuous_confidence() -> None:
    """融合输出应包含 DS 元数据，confidence 应为连续值。"""
    claim_a = _make_claim(
        "sc_ds_meta_a",
        "Exampleland confirmed deployment of warships.",
        attributed_to="Exampleland",
    )
    claim_b = _make_claim(
        "sc_ds_meta_b",
        "Neighborstan expressed concern over naval movement.",
        attributed_to="Neighborstan",
    )

    assertions, _, _, _ = fuse_claims([claim_a, claim_b], case_uid="case_ds_meta")

    assert len(assertions) == 2
    assert any(a.confidence not in {0.5, 0.9} for a in assertions)
    for assertion in assertions:
        assert assertion.confidence is not None
        assert 0.0 <= assertion.confidence <= 1.0
        assert "ds_belief" in assertion.value
        assert "ds_plausibility" in assertion.value
        assert "ds_uncertainty" in assertion.value
        assert "ds_conflict_degree" in assertion.value
        assert "source_count" in assertion.value


def test_fuse_conflict_scenario_has_ds_conflict_degree() -> None:
    """冲突场景下应输出 DS 冲突度。"""
    claim_a = _make_claim(
        "sc_ds_conflict_a",
        "Exampleland confirmed the operation.",
        attributed_to="Exampleland",
    )
    claim_b = _make_claim(
        "sc_ds_conflict_b",
        "Exampleland denied the operation.",
        attributed_to="Exampleland",
    )

    assertions, _, _, _ = fuse_claims([claim_a, claim_b], case_uid="case_ds_conflict")

    assert len(assertions) == 1
    assertion = assertions[0]
    assert assertion.value.get("has_conflict") is True
    assert assertion.value.get("ds_conflict_degree", 0.0) > 0.0
