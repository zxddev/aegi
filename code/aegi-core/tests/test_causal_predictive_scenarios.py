# Author: msq
"""Causal predictive scenarios tests.

Source: openspec/changes/predictive-causal-scenarios/tasks.md (4.1–4.3)
Evidence:
  - defgeo-forecast-001: 可解释预警（正常路径）
  - defgeo-forecast-002: 冲突信号（多假设冲突）
  - defgeo-forecast-003: 证据不足（应降级，不输出强结论）
  - 无证据预测禁止输出 probability → grounding_gate(False) 降级
  - 预测必须附替代解释，不允许单因果链闭环
  - 高风险阈值命中时自动进入 HITL 审批（pending_review）
  - backtest 必须输出 precision/false_alarm/missed_alert
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, NarrativeV1
from aegi_core.services.causal_reasoner import analyze_causal_links
from aegi_core.services.predictive_signals import (
    IndicatorSeriesV1,
    aggregate_signals,
    score_indicator,
)
from aegi_core.services.scenario_generator import (
    BacktestSummary,
    ForecastV1,
    backtest_forecast,
    generate_forecasts,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "defense-geopolitics"


def _load_scenario(name: str) -> dict:
    return json.loads((FIXTURES / name / "scenario.json").read_text(encoding="utf-8"))


def _build_assertions(raw: list[dict]) -> list[AssertionV1]:
    return [
        AssertionV1(
            uid=a["assertion_uid"],
            case_uid="case_test",
            kind=a.get("kind", "event"),
            value=a.get("value", {}),
            source_claim_uids=a.get("source_claim_uids", []),
            confidence=a.get("confidence"),
            created_at=a.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
        for a in raw
    ]


def _build_hypotheses(raw: list[dict]) -> list[HypothesisV1]:
    return [
        HypothesisV1(
            uid=h["hypothesis_uid"],
            case_uid="case_test",
            label=h["label"],
            supporting_assertion_uids=h.get("supporting_assertion_uids", []),
            confidence=h.get("confidence"),
            created_at=datetime.now(timezone.utc),
        )
        for h in raw
    ]


def _build_narratives(raw: list[dict]) -> list[NarrativeV1]:
    return [
        NarrativeV1(
            uid=n["narrative_uid"],
            case_uid="case_test",
            title=n["title"],
            assertion_uids=n.get("assertion_uids", []),
            hypothesis_uids=n.get("hypothesis_uids", []),
            created_at=datetime.now(timezone.utc),
        )
        for n in raw
    ]


def _build_indicators(raw: list[dict]) -> list[IndicatorSeriesV1]:
    return [IndicatorSeriesV1(**ind) for ind in raw]


# ---------------------------------------------------------------------------
# defgeo-forecast-001: 可解释预警（正常路径）
# ---------------------------------------------------------------------------

class TestForecast001ExplainableWarning:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-forecast-001")

    @pytest.fixture()
    def forecasts(self, scenario: dict) -> list[ForecastV1]:
        results, _, _ = generate_forecasts(
            hypotheses=_build_hypotheses(scenario["hypotheses"]),
            assertions=_build_assertions(scenario["assertions"]),
            narratives=_build_narratives(scenario.get("narratives", [])),
            indicators=_build_indicators(scenario.get("indicators", [])),
            case_uid="case_test",
            trace_id="trace_fc_001",
        )
        return results

    def test_scenario_count(self, forecasts: list[ForecastV1], scenario: dict) -> None:
        assert len(forecasts) >= scenario["expected"]["scenario_count_gte"]

    def test_has_evidence_citations(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert len(f.evidence_citations) > 0

    def test_has_trigger_conditions(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert len(f.trigger_conditions) > 0

    def test_has_alternatives(self, forecasts: list[ForecastV1]) -> None:
        """预测必须附替代解释，不允许单因果链闭环。"""
        for f in forecasts:
            assert len(f.alternatives) > 0

    def test_grounding_level_fact(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert f.grounding_level == GroundingLevel.FACT

    def test_probability_present(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert f.probability is not None
            assert 0.0 <= f.probability <= 1.0

    def test_audit_trace(self, scenario: dict) -> None:
        _, action, trace = generate_forecasts(
            hypotheses=_build_hypotheses(scenario["hypotheses"]),
            assertions=_build_assertions(scenario["assertions"]),
            case_uid="case_test",
            trace_id="trace_fc_001",
        )
        assert action.trace_id == "trace_fc_001"
        assert trace.trace_id == "trace_fc_001"

    def test_causal_analysis_present(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert f.causal_analysis is not None
            assert f.causal_analysis.consistency_score > 0


# ---------------------------------------------------------------------------
# defgeo-forecast-002: 冲突信号（多假设冲突）
# ---------------------------------------------------------------------------

class TestForecast002ConflictingSignals:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-forecast-002")

    @pytest.fixture()
    def forecasts(self, scenario: dict) -> list[ForecastV1]:
        results, _, _ = generate_forecasts(
            hypotheses=_build_hypotheses(scenario["hypotheses"]),
            assertions=_build_assertions(scenario["assertions"]),
            narratives=_build_narratives(scenario.get("narratives", [])),
            indicators=_build_indicators(scenario.get("indicators", [])),
            case_uid="case_test",
            trace_id="trace_fc_002",
        )
        return results

    def test_multiple_scenarios(self, forecasts: list[ForecastV1], scenario: dict) -> None:
        assert len(forecasts) >= scenario["expected"]["scenario_count_gte"]

    def test_has_alternatives(self, forecasts: list[ForecastV1]) -> None:
        """冲突假设时每个预测必须列出替代解释。"""
        for f in forecasts:
            assert len(f.alternatives) > 0

    def test_high_risk_pending_review(self, forecasts: list[ForecastV1]) -> None:
        """高风险阈值命中时自动进入 HITL 审批。"""
        statuses = {f.status for f in forecasts}
        # 冲突场景中至少有一个 pending_review 或 degraded
        assert statuses & {"pending_review", "degraded"}

    def test_signal_scores_present(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert len(f.signal_scores) > 0


# ---------------------------------------------------------------------------
# defgeo-forecast-003: 证据不足（应降级，不输出强结论）
# ---------------------------------------------------------------------------

class TestForecast003InsufficientEvidence:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-forecast-003")

    @pytest.fixture()
    def forecasts(self, scenario: dict) -> list[ForecastV1]:
        results, _, _ = generate_forecasts(
            hypotheses=_build_hypotheses(scenario["hypotheses"]),
            assertions=_build_assertions(scenario["assertions"]),
            narratives=_build_narratives(scenario.get("narratives", [])),
            indicators=_build_indicators(scenario.get("indicators", [])),
            case_uid="case_test",
            trace_id="trace_fc_003",
        )
        return results

    def test_grounding_degraded(self, forecasts: list[ForecastV1]) -> None:
        """无证据支持 → grounding_gate(False) → HYPOTHESIS。"""
        for f in forecasts:
            assert f.grounding_level == GroundingLevel.HYPOTHESIS

    def test_probability_none(self, forecasts: list[ForecastV1]) -> None:
        """缺少 evidence citations 的预测不返回高置信 probability。"""
        for f in forecasts:
            assert f.probability is None

    def test_status_degraded(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert f.status == "degraded"

    def test_has_alternatives(self, forecasts: list[ForecastV1]) -> None:
        for f in forecasts:
            assert len(f.alternatives) > 0


# ---------------------------------------------------------------------------
# Backtest 验证
# ---------------------------------------------------------------------------

class TestBacktest:
    def test_backtest_success(self) -> None:
        forecast = ForecastV1(
            scenario_id="test-bt",
            probability=0.8,
            evidence_citations=["sc1"],
            alternatives=["alt"],
        )
        summary = backtest_forecast(forecast, [
            {"occurred": True},
            {"occurred": True},
            {"occurred": False},
        ])
        assert isinstance(summary, BacktestSummary)
        assert summary.precision > 0
        assert summary.false_alarm >= 0
        assert summary.missed_alert >= 0

    def test_backtest_no_outcomes(self) -> None:
        forecast = ForecastV1(scenario_id="test-bt-empty", alternatives=["alt"])
        summary = backtest_forecast(forecast, [])
        assert summary.precision == 0.0
        assert summary.false_alarm == 0.0
        assert summary.missed_alert == 0.0

    def test_backtest_missed_alert(self) -> None:
        """预测为低概率但实际发生 → missed_alert > 0。"""
        forecast = ForecastV1(
            scenario_id="test-bt-miss",
            probability=0.2,
            alternatives=["alt"],
        )
        summary = backtest_forecast(forecast, [{"occurred": True}])
        assert summary.missed_alert > 0

    def test_backtest_false_alarm(self) -> None:
        """预测为高概率但未发生 → false_alarm > 0。"""
        forecast = ForecastV1(
            scenario_id="test-bt-false",
            probability=0.9,
            evidence_citations=["sc1"],
            alternatives=["alt"],
        )
        summary = backtest_forecast(forecast, [{"occurred": False}])
        assert summary.false_alarm > 0


# ---------------------------------------------------------------------------
# Causal reasoner 单元测试
# ---------------------------------------------------------------------------

class TestCausalReasoner:
    def test_temporal_consistency(self) -> None:
        now = datetime.now(timezone.utc)
        assertions = [
            AssertionV1(
                uid="a1", case_uid="c", kind="event", value={},
                source_claim_uids=["sc1"], confidence=0.8,
                created_at="2026-01-01T00:00:00+00:00",
            ),
            AssertionV1(
                uid="a2", case_uid="c", kind="event", value={},
                source_claim_uids=["sc2"], confidence=0.9,
                created_at="2026-01-02T00:00:00+00:00",
            ),
        ]
        hyp = HypothesisV1(
            uid="h1", case_uid="c", label="test",
            supporting_assertion_uids=["a1", "a2"],
            confidence=0.8, created_at=now,
        )
        result = analyze_causal_links(hyp, assertions)
        assert result.consistency_score == 1.0
        assert len(result.causal_links) == 1
        assert result.causal_links[0].temporal_consistent is True

    def test_no_supporting_assertions(self) -> None:
        hyp = HypothesisV1(
            uid="h1", case_uid="c", label="test",
            supporting_assertion_uids=[],
            created_at=datetime.now(timezone.utc),
        )
        result = analyze_causal_links(hyp, [])
        assert result.grounding_level == GroundingLevel.HYPOTHESIS
        assert result.consistency_score == 0.0

    def test_narrative_degradation(self) -> None:
        """Narrative 缺失时 narrative_available 为 False。"""
        hyp = HypothesisV1(
            uid="h1", case_uid="c", label="test",
            supporting_assertion_uids=[],
            created_at=datetime.now(timezone.utc),
        )
        result = analyze_causal_links(hyp, [], narratives=None)
        assert result.narrative_available is False

        result_with = analyze_causal_links(hyp, [], narratives=[
            NarrativeV1(
                uid="n1", case_uid="c", title="t",
                created_at=datetime.now(timezone.utc),
            )
        ])
        assert result_with.narrative_available is True


# ---------------------------------------------------------------------------
# Predictive signals 单元测试
# ---------------------------------------------------------------------------

class TestPredictiveSignals:
    def test_rising_trend(self) -> None:
        series = IndicatorSeriesV1(
            name="test", timestamps=["t1", "t2", "t3"], values=[0.1, 0.5, 0.9],
        )
        score = score_indicator(series)
        assert score.trend == "rising"
        assert score.momentum > 0

    def test_stable_trend(self) -> None:
        series = IndicatorSeriesV1(
            name="test", timestamps=["t1", "t2"], values=[0.5, 0.5],
        )
        score = score_indicator(series)
        assert score.trend == "stable"

    def test_single_value(self) -> None:
        series = IndicatorSeriesV1(name="test", timestamps=["t1"], values=[0.5])
        score = score_indicator(series)
        assert score.trend == "stable"
        assert score.momentum == 0.0

    def test_aggregate(self) -> None:
        series_list = [
            IndicatorSeriesV1(name="a", timestamps=["t1", "t2"], values=[0.1, 0.9]),
            IndicatorSeriesV1(name="b", timestamps=["t1", "t2"], values=[0.8, 0.2]),
        ]
        scores = aggregate_signals(series_list)
        assert len(scores) == 2
        assert scores[0].indicator_name == "a"
        assert scores[1].indicator_name == "b"


# ---------------------------------------------------------------------------
# Grounding gate 合同验证（forecast 上下文）
# ---------------------------------------------------------------------------

class TestForecastGroundingGate:
    def test_no_evidence_never_fact(self) -> None:
        assert grounding_gate(False) != GroundingLevel.FACT

    def test_with_evidence_returns_fact(self) -> None:
        assert grounding_gate(True) == GroundingLevel.FACT


# ---------------------------------------------------------------------------
# API route 桩测试
# ---------------------------------------------------------------------------

class TestForecastAPIStubs:
    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from aegi_core.api.routes.forecast import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_generate_stub(self, client) -> None:
        resp = client.post(
            "/cases/c1/forecast/generate",
            json={"hypothesis_uids": [], "assertion_uids": []},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "scenarios" in data
        assert data["action_uid"] == "stub"

    def test_backtest_stub(self, client) -> None:
        resp = client.post(
            "/cases/c1/forecast/backtest",
            json={"scenario_id": "s1", "actual_outcomes": []},
        )
        assert resp.status_code == 200
        assert resp.json()["precision"] == 0.0

    def test_explain_stub(self, client) -> None:
        resp = client.get("/cases/c1/forecast/s1/explain")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == "s1"
        assert "alternatives" in data
