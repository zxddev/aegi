# Author: msq
"""Dempster-Shafer 证据融合引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aegi_core.contracts.schemas import SourceClaimV1

_EPS = 1e-9
DEFAULT_CREDIBILITY = 0.5
DEFAULT_CLAIM_CONFIDENCE = 0.75


@dataclass(slots=True)
class DSFusionResult:
    """DS 融合结果。"""

    confidence: float
    belief: float
    plausibility: float
    uncertainty: float
    conflict_degree: float
    mass_true: float
    mass_false: float
    source_count: int


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_mass(m_true: float, m_false: float, m_uncertain: float) -> tuple[float, float, float]:
    """归一化并保证 mass 三元组有效。"""
    mt = max(0.0, float(m_true))
    mf = max(0.0, float(m_false))
    mu = max(0.0, float(m_uncertain))
    total = mt + mf + mu
    if total <= _EPS:
        return 0.0, 0.0, 1.0
    return mt / total, mf / total, mu / total


def claim_to_mass(
    claim_confidence: float,
    source_credibility: float,
) -> tuple[float, float, float]:
    """将单条 SourceClaim 转换为 mass function。"""
    confidence = _clamp01(claim_confidence)
    credibility = _clamp01(source_credibility)
    m_true = confidence * credibility
    m_false = (1.0 - confidence) * credibility
    m_uncertain = 1.0 - credibility
    return _normalize_mass(m_true, m_false, m_uncertain)


def _combine_two(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[tuple[float, float, float], float]:
    """组合两个 mass function，返回 (组合后的 mass, 冲突度 K)。"""
    lt, lf, lu = left
    rt, rf, ru = right

    conflict = _clamp01(lt * rf + lf * rt)
    normalizer = 1.0 - conflict
    if normalizer <= _EPS:
        return (0.0, 0.0, 1.0), 1.0

    m_true = (lt * rt + lt * ru + lu * rt) / normalizer
    m_false = (lf * rf + lf * ru + lu * rf) / normalizer
    m_uncertain = (lu * ru) / normalizer
    return _normalize_mass(m_true, m_false, m_uncertain), conflict


def _pignistic_true(m_true: float, m_uncertain: float) -> float:
    """Pignistic 概率 BetP(true)。"""
    return _clamp01(m_true + 0.5 * m_uncertain)


def combine_masses(
    masses: list[tuple[float, float, float]],
) -> DSFusionResult:
    """用 Dempster 组合规则融合多个 mass function。"""
    if not masses:
        return DSFusionResult(
            confidence=0.5,
            belief=0.0,
            plausibility=1.0,
            uncertainty=1.0,
            conflict_degree=0.0,
            mass_true=0.0,
            mass_false=0.0,
            source_count=0,
        )

    normalized = [_normalize_mass(*m) for m in masses]
    current = normalized[0]
    conflict_degree = 0.0
    for mass in normalized[1:]:
        current, conflict = _combine_two(current, mass)
        # 逐步冲突聚合：1 - Π(1 - Ki)
        conflict_degree = 1.0 - ((1.0 - conflict_degree) * (1.0 - conflict))

    mass_true, mass_false, mass_uncertain = current
    belief = _clamp01(mass_true)
    plausibility = _clamp01(mass_true + mass_uncertain)
    confidence = _pignistic_true(mass_true, mass_uncertain)

    return DSFusionResult(
        confidence=confidence,
        belief=belief,
        plausibility=plausibility,
        uncertainty=_clamp01(mass_uncertain),
        conflict_degree=_clamp01(conflict_degree),
        mass_true=_clamp01(mass_true),
        mass_false=_clamp01(mass_false),
        source_count=len(masses),
    )


def _resolve_claim_confidence(
    claim: "SourceClaimV1",
    claim_confidences: dict[str, float] | None,
) -> float:
    """解析单条 claim 置信度，优先使用外部传入值。"""
    if claim_confidences and claim.uid in claim_confidences:
        return _clamp01(claim_confidences[claim.uid])

    raw_confidence = getattr(claim, "confidence", None)
    if isinstance(raw_confidence, int | float):
        return _clamp01(float(raw_confidence))

    return DEFAULT_CLAIM_CONFIDENCE


def fuse_claims_ds(
    claims: list["SourceClaimV1"],
    credibility_scores: dict[str, float],
    *,
    claim_confidences: dict[str, float] | None = None,
) -> DSFusionResult:
    """高层接口：融合一组 SourceClaims。"""
    masses: list[tuple[float, float, float]] = []
    for claim in claims:
        claim_confidence = _resolve_claim_confidence(claim, claim_confidences)
        source_credibility = _clamp01(
            credibility_scores.get(claim.uid, DEFAULT_CREDIBILITY)
        )
        masses.append(claim_to_mass(claim_confidence, source_credibility))
    return combine_masses(masses)
