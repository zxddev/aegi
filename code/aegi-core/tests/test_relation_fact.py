# Author: msq
"""RelationFact service unit tests."""

from __future__ import annotations

from aegi_core.services.relation_fact_service import RelationFactService


def test_calculate_evidence_strength_uses_quantity_and_confidence() -> None:
    low = RelationFactService.calculate_evidence_strength([], 0.2)
    high = RelationFactService.calculate_evidence_strength(
        ["sc_1", "sc_2", "sc_3", "sc_4", "sc_5"],
        0.9,
    )

    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_conflict_detection_rule_for_relation_types() -> None:
    assert RelationFactService.is_conflicting_relation("ALLIED_WITH", "HOSTILE_TO")
    assert RelationFactService.is_conflicting_relation("HOSTILE_TO", "ALLIED_WITH")
    assert not RelationFactService.is_conflicting_relation("ALLIED_WITH", "ALLIED_WITH")
    assert not RelationFactService.is_conflicting_relation(
        "COOPERATES_WITH", "ALLIED_WITH"
    )
