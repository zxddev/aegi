# Author: msq
"""Tests for Dempster-Shafer fusion engine."""

from __future__ import annotations

from datetime import datetime, timezone

from aegi_core.contracts.schemas import Modality, SourceClaimV1
from aegi_core.services.ds_fusion import claim_to_mass, combine_masses, fuse_claims_ds


def _make_claim(uid: str, quote: str) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid="case_ds",
        artifact_version_uid="av_ds",
        chunk_uid="chunk_ds",
        evidence_uid="ev_ds",
        quote=quote,
        selectors=[{"type": "TextQuoteSelector", "exact": quote}],
        attributed_to="Exampleland",
        modality=Modality.TEXT,
        created_at=datetime.now(timezone.utc),
    )


def test_claim_to_mass_high_credibility() -> None:
    """高可信来源：m_uncertain 小。"""
    m_true, _, m_uncertain = claim_to_mass(0.8, 0.9)
    assert abs(m_true - 0.72) < 0.01
    assert abs(m_uncertain - 0.10) < 0.01


def test_claim_to_mass_low_credibility() -> None:
    """低可信来源：m_uncertain 大。"""
    _, _, m_uncertain = claim_to_mass(0.8, 0.3)
    assert m_uncertain > 0.6


def test_combine_two_agreeing_sources() -> None:
    """两个一致的高可信来源 -> confidence 很高。"""
    m1 = claim_to_mass(0.8, 0.9)
    m2 = claim_to_mass(0.85, 0.85)
    result = combine_masses([m1, m2])
    assert result.confidence > 0.9


def test_combine_two_conflicting_sources() -> None:
    """两个矛盾来源 -> conflict_degree 高。"""
    m1 = claim_to_mass(0.9, 0.8)
    m2 = claim_to_mass(0.1, 0.8)
    result = combine_masses([m1, m2])
    assert result.conflict_degree > 0.3


def test_combine_high_vs_low_credibility() -> None:
    """高可信来源应压过低可信来源。"""
    m_reuters = claim_to_mass(0.8, 0.9)
    m_blog = claim_to_mass(0.2, 0.3)
    result = combine_masses([m_reuters, m_blog])
    assert result.confidence > 0.6


def test_combine_single_source() -> None:
    """单一来源直接映射为概率。"""
    m = claim_to_mass(0.8, 0.9)
    result = combine_masses([m])
    assert abs(result.confidence - 0.8) < 0.1


def test_combine_many_weak_sources() -> None:
    """多个弱来源聚合可以增强信念。"""
    masses = [claim_to_mass(0.7, 0.4) for _ in range(5)]
    result = combine_masses(masses)
    assert result.confidence > 0.7


def test_fuse_claims_ds_with_confidence_override() -> None:
    """高层接口支持按 claim 传入 confidence 覆盖值。"""
    claims = [
        _make_claim("sc_ds_1", "Exampleland confirmed deployment."),
        _make_claim("sc_ds_2", "Exampleland confirmed reinforcement."),
    ]
    result = fuse_claims_ds(
        claims,
        credibility_scores={"sc_ds_1": 0.9, "sc_ds_2": 0.8},
        claim_confidences={"sc_ds_1": 0.9, "sc_ds_2": 0.88},
    )
    assert result.source_count == 2
    assert result.confidence > 0.85
