# Author: msq
"""Confidence scoring and quality report for meta-cognition.

Source: openspec/changes/meta-cognition-quality-scoring/design.md
Evidence:
  - confidence_breakdown: evidence_strength / coverage / consistency / freshness.
  - Upstream missing → pending_inputs, no pseudo-complete score.
  - QualityReportV1 output with trace_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
from aegi_core.services.bias_detector import BiasFlag, detect_biases
from aegi_core.services.blindspot_detector import BlindspotItem, detect_blindspots


# -- Models --------------------------------------------------------------------


class DimensionStatus(str, Enum):
    COMPLETE = "complete"
    PENDING = "pending"


class ConfidenceDimension(BaseModel):
    name: str
    score: float
    status: DimensionStatus = DimensionStatus.COMPLETE
    detail: str = ""


class ReportStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PENDING_INPUTS = "pending_inputs"


class QualityReportV1(BaseModel):
    judgment_uid: str
    case_uid: str
    status: ReportStatus
    confidence_score: float
    confidence_breakdown: list[ConfidenceDimension]
    bias_flags: list[BiasFlag] = Field(default_factory=list)
    blindspot_items: list[BlindspotItem] = Field(default_factory=list)
    evidence_diversity: int = 0
    trace_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -- Input container -----------------------------------------------------------


class QualityInput(BaseModel):
    judgment_uid: str
    case_uid: str
    title: str
    assertion_uids: list[str] = Field(default_factory=list)
    assertions: list[AssertionV1] = Field(default_factory=list)
    hypotheses: list[HypothesisV1] = Field(default_factory=list)
    narratives: list[NarrativeV1] = Field(default_factory=list)
    source_claims: list[SourceClaimV1] = Field(default_factory=list)
    forecasts: list[dict] | None = None


# -- Scoring functions ---------------------------------------------------------


def _evidence_strength(
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
) -> ConfidenceDimension:
    """独立来源数 × 平均置信度。"""
    if not assertions:
        return ConfidenceDimension(
            name="evidence_strength", score=0.0, detail="no assertions"
        )
    unique_sources = {sc.attributed_to for sc in source_claims if sc.attributed_to}
    avg_conf = sum(a.confidence or 0.0 for a in assertions) / len(assertions)
    source_factor = min(len(unique_sources) / 3.0, 1.0)
    score = round((avg_conf * 0.6 + source_factor * 0.4), 4)
    return ConfidenceDimension(
        name="evidence_strength",
        score=score,
        detail=f"sources={len(unique_sources)}, avg_confidence={avg_conf:.2f}",
    )


def _coverage(
    assertions: list[AssertionV1],
    hypotheses: list[HypothesisV1],
) -> ConfidenceDimension:
    """关键维度是否缺证据。"""
    if not hypotheses:
        return ConfidenceDimension(name="coverage", score=0.0, detail="no hypotheses")
    assertion_uid_set = {a.uid for a in assertions}
    covered = sum(
        1
        for h in hypotheses
        if any(uid in assertion_uid_set for uid in h.supporting_assertion_uids)
    )
    score = round(covered / len(hypotheses), 4)
    return ConfidenceDimension(
        name="coverage",
        score=score,
        detail=f"covered_hypotheses={covered}/{len(hypotheses)}",
    )


def _consistency(
    hypotheses: list[HypothesisV1],
    narratives: list[NarrativeV1],
    forecasts: list[dict] | None,
) -> ConfidenceDimension:
    """上游模块输出冲突程度；forecast 缺失时标记 pending。"""
    if forecasts is None:
        return ConfidenceDimension(
            name="consistency",
            score=0.0,
            status=DimensionStatus.PENDING,
            detail="forecast unavailable",
        )
    if not hypotheses:
        return ConfidenceDimension(
            name="consistency", score=0.0, detail="no hypotheses"
        )
    confs = [h.confidence for h in hypotheses if h.confidence is not None]
    if not confs:
        return ConfidenceDimension(
            name="consistency", score=0.5, detail="no confidence values"
        )
    spread = max(confs) - min(confs)
    score = round(1.0 - min(spread, 1.0), 4)
    return ConfidenceDimension(
        name="consistency",
        score=score,
        detail=f"confidence_spread={spread:.2f}",
    )


def _freshness(source_claims: list[SourceClaimV1]) -> ConfidenceDimension:
    """时效性：最新 source_claim 距今天数。"""
    if not source_claims:
        return ConfidenceDimension(
            name="freshness", score=0.0, detail="no source claims"
        )
    now = datetime.now(timezone.utc)
    newest = max(sc.created_at for sc in source_claims)
    days_old = (now - newest).total_seconds() / 86400.0
    score = round(max(1.0 - days_old / 30.0, 0.0), 4)
    return ConfidenceDimension(
        name="freshness",
        score=score,
        detail=f"newest_days_ago={days_old:.1f}",
    )


def score_confidence(inp: QualityInput) -> QualityReportV1:
    """计算元认知质量评分。

    Args:
        inp: 包含 judgment、上游产物、可选 forecast 的输入。

    Returns:
        QualityReportV1，status 为 complete/partial/pending_inputs。
    """
    trace_id = f"trace-quality-{uuid.uuid4().hex[:12]}"

    dims = [
        _evidence_strength(inp.assertions, inp.source_claims),
        _coverage(inp.assertions, inp.hypotheses),
        _consistency(inp.hypotheses, inp.narratives, inp.forecasts),
        _freshness(inp.source_claims),
    ]

    bias_flags = detect_biases(inp.assertions, inp.source_claims, inp.hypotheses)
    blindspots = detect_blindspots(
        inp.assertions,
        inp.hypotheses,
        inp.source_claims,
        inp.forecasts,
    )

    unique_sources = {sc.attributed_to for sc in inp.source_claims if sc.attributed_to}

    has_pending = any(d.status == DimensionStatus.PENDING for d in dims)
    complete_dims = [d for d in dims if d.status == DimensionStatus.COMPLETE]
    avg_score = (
        round(sum(d.score for d in complete_dims) / len(complete_dims), 4)
        if complete_dims
        else 0.0
    )

    if not inp.assertions and not inp.source_claims:
        status = ReportStatus.PENDING_INPUTS
    elif has_pending:
        status = ReportStatus.PARTIAL
    else:
        status = ReportStatus.COMPLETE

    return QualityReportV1(
        judgment_uid=inp.judgment_uid,
        case_uid=inp.case_uid,
        status=status,
        confidence_score=avg_score,
        confidence_breakdown=dims,
        bias_flags=bias_flags,
        blindspot_items=blindspots,
        evidence_diversity=len(unique_sources),
        trace_id=trace_id,
    )
