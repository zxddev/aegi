# Author: msq
"""盲区检测，用于元认知质量评分。

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
        unsupported = [
            uid for uid in h.supporting_assertion_uids if uid not in assertion_uid_set
        ]
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


def _periodic_gap_detection(source_claims: list[SourceClaimV1]) -> list[BlindspotItem]:
    """检测周期性信息空白，区分真正盲区和规律性模式（如周末无报道）。"""
    if len(source_claims) < 7:
        return []
    timestamps = sorted(sc.created_at for sc in source_claims)
    # 计算相邻 claim 的时间间隔（小时）
    gaps = [
        (timestamps[i + 1] - timestamps[i]).total_seconds() / 3600.0
        for i in range(len(timestamps) - 1)
    ]
    if not gaps:
        return []
    avg_gap = sum(gaps) / len(gaps)
    # 检测是否有规律性大间隔（标准差低 = 规律性）
    large_gaps = [g for g in gaps if g > avg_gap * 2]
    if len(large_gaps) < 2:
        return []
    # 计算大间隔之间的间距是否规律
    large_gap_indices = [i for i, g in enumerate(gaps) if g > avg_gap * 2]
    if len(large_gap_indices) >= 2:
        intervals = [
            large_gap_indices[i + 1] - large_gap_indices[i]
            for i in range(len(large_gap_indices) - 1)
        ]
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
            # 低方差 = 周期性模式
            if variance < avg_interval * 0.5:
                return [
                    BlindspotItem(
                        dimension="periodic_pattern",
                        description=(
                            f"Periodic information gaps detected: "
                            f"{len(large_gaps)} gaps with regular interval "
                            f"(~{avg_interval:.1f} claims apart)"
                        ),
                        severity="low",
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
    items.extend(_periodic_gap_detection(source_claims))
    items.extend(_upstream_blindspots(forecasts))
    return items
