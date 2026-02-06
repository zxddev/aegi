# Author: msq
"""Blindspot detection for meta-cognition quality scoring.

Source: openspec/changes/meta-cognition-quality-scoring/design.md
Evidence:
  - 关键维度缺证据、时间窗缺失、地理盲点。
  - 每个 blindspot MUST 指向具体缺失维度。
  - 上游缺失 → pending_inputs。
"""

from __future__ import annotations


from pydantic import BaseModel

from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, SourceClaimV1


class BlindspotItem(BaseModel):
    dimension: str
    description: str
    severity: str = "medium"


def _coverage_blindspots(
    assertions: list[AssertionV1],
    hypotheses: list[HypothesisV1],
) -> list[BlindspotItem]:
    """假设缺少支撑 assertion → 覆盖度盲区。"""
    assertion_uid_set = {a.uid for a in assertions}
    items: list[BlindspotItem] = []
    for h in hypotheses:
        unsupported = [uid for uid in h.supporting_assertion_uids if uid not in assertion_uid_set]
        if unsupported:
            items.append(
                BlindspotItem(
                    dimension="coverage",
                    description=(
                        f"Hypothesis {h.uid} references {len(unsupported)} "
                        f"missing assertion(s): {unsupported}"
                    ),
                    severity="high",
                )
            )
    if not assertions:
        items.append(
            BlindspotItem(
                dimension="coverage",
                description="No assertions available for judgment",
                severity="high",
            )
        )
    return items


def _temporal_blindspots(source_claims: list[SourceClaimV1]) -> list[BlindspotItem]:
    """时间窗口过窄或过旧 → 时间盲区。"""
    if len(source_claims) <= 1:
        return [
            BlindspotItem(
                dimension="temporal",
                description="Insufficient temporal spread (<=1 source claim)",
                severity="medium",
            )
        ]
    timestamps = sorted(sc.created_at for sc in source_claims)
    span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
    if span_hours < 1.0:
        return [
            BlindspotItem(
                dimension="temporal",
                description=f"All sources within {span_hours:.1f}h window",
                severity="medium",
            )
        ]
    return []


def _upstream_blindspots(forecasts: list[dict] | None) -> list[BlindspotItem]:
    """上游 forecast 缺失 → 上游盲区。"""
    if forecasts is None:
        return [
            BlindspotItem(
                dimension="upstream_dependency",
                description="Forecast output unavailable (AI-8 pending)",
                severity="high",
            )
        ]
    return []


def detect_blindspots(
    assertions: list[AssertionV1],
    hypotheses: list[HypothesisV1],
    source_claims: list[SourceClaimV1],
    forecasts: list[dict] | None = None,
) -> list[BlindspotItem]:
    """运行所有盲区检测器。

    Args:
        assertions: 当前 judgment 的 assertions。
        hypotheses: 关联的 hypotheses。
        source_claims: 关联的 source claims。
        forecasts: 上游 forecast 输出（None 表示不可用）。

    Returns:
        检测到的 BlindspotItem 列表。
    """
    items: list[BlindspotItem] = []
    items.extend(_coverage_blindspots(assertions, hypotheses))
    items.extend(_temporal_blindspots(source_claims))
    items.extend(_upstream_blindspots(forecasts))
    return items
