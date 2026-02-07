# Author: msq
"""Predictive signals – indicator series scoring and trend detection.

Source: openspec/changes/predictive-causal-scenarios/tasks.md (2.2)
        openspec/changes/predictive-causal-scenarios/design.md
Evidence:
  - IndicatorSeriesV1 本地定义
  - 基于 Assertion 时序字段做预警评分
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class IndicatorSeriesV1(BaseModel):
    """时序指标序列（本地定义，非共享合同）。"""

    name: str
    timestamps: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)


@dataclass
class SignalScore:
    """单个指标的预测信号评分。"""

    indicator_name: str
    trend: str = "stable"  # rising / falling / stable
    momentum: float = 0.0  # -1.0 ~ 1.0
    alert_level: float = 0.0  # 0.0 ~ 1.0


def score_indicator(series: IndicatorSeriesV1) -> SignalScore:
    """对单个指标序列计算趋势与动量。

    Args:
        series: 时序指标数据。

    Returns:
        SignalScore 包含趋势方向、动量和预警级别。
    """
    if len(series.values) < 2:
        return SignalScore(indicator_name=series.name)

    # 简单差分趋势
    deltas = [
        series.values[i] - series.values[i - 1] for i in range(1, len(series.values))
    ]
    avg_delta = sum(deltas) / len(deltas)

    if avg_delta > 0.05:
        trend = "rising"
    elif avg_delta < -0.05:
        trend = "falling"
    else:
        trend = "stable"

    momentum = max(-1.0, min(1.0, avg_delta * 2))
    alert_level = min(1.0, max(0.0, series.values[-1]))

    return SignalScore(
        indicator_name=series.name,
        trend=trend,
        momentum=momentum,
        alert_level=alert_level,
    )


def aggregate_signals(series_list: list[IndicatorSeriesV1]) -> list[SignalScore]:
    """批量评分所有指标序列。

    Args:
        series_list: 指标序列列表。

    Returns:
        各指标的 SignalScore 列表。
    """
    return [score_indicator(s) for s in series_list]
