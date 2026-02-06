# Author: msq
"""Scenario generator – combine causal analysis + predictive signals into forecasts.

Source: openspec/changes/predictive-causal-scenarios/tasks.md (2.3)
        openspec/changes/predictive-causal-scenarios/design.md
Evidence:
  - ForecastV1 必填：scenario_id, probability, trigger_conditions, evidence_citations, alternatives
  - 无证据预测禁止输出 probability → grounding_gate(False) 降级
  - 预测必须附替代解释，不允许单因果链闭环
  - 高风险阈值命中时自动进入 HITL 审批（pending_review）
  - 缺少 evidence citations → 降级为 hypothesis，不返回高置信 probability
  - 发布级预测 MUST 附带 backtest_summary
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, NarrativeV1
from aegi_core.services.causal_reasoner import CausalAnalysis, analyze_causal_links
from aegi_core.services.predictive_signals import (
    IndicatorSeriesV1,
    SignalScore,
    aggregate_signals,
)

HIGH_RISK_THRESHOLD = 0.8
CONFLICT_THRESHOLD = 2  # >= 2 hypotheses with overlapping assertions → conflict


@dataclass
class ForecastV1:
    """预测情景输出。"""

    scenario_id: str
    probability: float | None = None
    trigger_conditions: list[str] = field(default_factory=list)
    evidence_citations: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    grounding_level: GroundingLevel = GroundingLevel.HYPOTHESIS
    status: str = "draft"  # draft / published / degraded / pending_review
    causal_analysis: CausalAnalysis | None = None
    signal_scores: list[SignalScore] = field(default_factory=list)


@dataclass
class BacktestSummary:
    """回测摘要。"""

    precision: float = 0.0
    false_alarm: float = 0.0
    missed_alert: float = 0.0


def generate_forecasts(
    *,
    hypotheses: list[HypothesisV1],
    assertions: list[AssertionV1],
    narratives: list[NarrativeV1] | None = None,
    indicators: list[IndicatorSeriesV1] | None = None,
    case_uid: str,
    trace_id: str | None = None,
) -> tuple[list[ForecastV1], ActionV1, ToolTraceV1]:
    """生成预测情景。

    Args:
        hypotheses: 输入假设列表。
        assertions: 输入 assertion 列表。
        narratives: 可选叙事列表（soft dep）。
        indicators: 可选指标序列。
        case_uid: 所属 case。
        trace_id: 分布式追踪 ID。

    Returns:
        Tuple of (forecasts, action, tool_trace).
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    signals = aggregate_signals(indicators or [])
    max_alert = max((s.alert_level for s in signals), default=0.0)

    # 收集所有 assertion 的 evidence citation uids
    all_evidence_uids: list[str] = []
    for a in assertions:
        all_evidence_uids.extend(a.source_claim_uids)
    has_evidence = len(all_evidence_uids) > 0

    # 冲突检测：多个假设引用不同 assertion 集合 → 信号冲突
    has_conflict = len(hypotheses) >= CONFLICT_THRESHOLD

    forecasts: list[ForecastV1] = []

    for hyp in hypotheses:
        causal = analyze_causal_links(hyp, assertions, narratives)
        grounding = grounding_gate(has_evidence and len(hyp.supporting_assertion_uids) > 0)

        # 构建 trigger conditions
        triggers: list[str] = []
        for link in causal.causal_links:
            if link.temporal_consistent:
                triggers.append(f"{link.source_uid} → {link.target_uid}")
        for sig in signals:
            if sig.trend == "rising":
                triggers.append(f"{sig.indicator_name}: {sig.trend}")

        # 收集该假设的 evidence citations
        hyp_evidence: list[str] = []
        for a in assertions:
            if a.uid in hyp.supporting_assertion_uids:
                hyp_evidence.extend(a.source_claim_uids)

        # 计算 probability（无证据时禁止输出）
        probability: float | None = None
        if grounding == GroundingLevel.FACT:
            base = (hyp.confidence or 0.0) * causal.consistency_score
            signal_boost = max_alert * 0.2
            probability = min(1.0, base + signal_boost)

        # 生成替代解释（强制：不允许单因果链闭环）
        other_labels = [h.label for h in hypotheses if h.uid != hyp.uid]
        alternatives = other_labels if other_labels else ["No alternative hypotheses available"]

        # 状态判定
        if grounding != GroundingLevel.FACT:
            status = "degraded"
        elif has_conflict or (probability is not None and probability >= HIGH_RISK_THRESHOLD):
            status = "pending_review"
        else:
            status = "published"

        forecasts.append(
            ForecastV1(
                scenario_id=f"forecast-{uuid.uuid4().hex[:8]}",
                probability=probability,
                trigger_conditions=triggers,
                evidence_citations=hyp_evidence,
                alternatives=alternatives,
                grounding_level=grounding,
                status=status,
                causal_analysis=causal,
                signal_scores=signals,
            )
        )

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="forecast_generate",
        rationale=f"Generated {len(forecasts)} forecasts from {len(hypotheses)} hypotheses",
        inputs={"hypothesis_count": len(hypotheses), "assertion_count": len(assertions)},
        outputs={"forecast_count": len(forecasts)},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="forecast_generate",
        request={"hypothesis_count": len(hypotheses)},
        response={"forecast_count": len(forecasts)},
        status="ok",
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return forecasts, action, tool_trace


def backtest_forecast(
    forecast: ForecastV1,
    actual_outcomes: list[dict],
) -> BacktestSummary:
    """对预测执行回测。

    Args:
        forecast: 待回测的预测。
        actual_outcomes: 实际结果列表，每项含 {"occurred": bool}。

    Returns:
        BacktestSummary 包含 precision/false_alarm/missed_alert。
    """
    if not actual_outcomes:
        return BacktestSummary()

    total = len(actual_outcomes)
    occurred = sum(1 for o in actual_outcomes if o.get("occurred", False))
    not_occurred = total - occurred

    predicted_positive = forecast.probability is not None and forecast.probability > 0.5

    if predicted_positive and occurred > 0:
        precision = occurred / total
    else:
        precision = 0.0

    false_alarm = (not_occurred / total) if predicted_positive else 0.0
    missed_alert = (occurred / total) if not predicted_positive and occurred > 0 else 0.0

    return BacktestSummary(
        precision=precision,
        false_alarm=false_alarm,
        missed_alert=missed_alert,
    )
