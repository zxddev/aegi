# Author: msq
"""Forecast API routes – generate/backtest/explain.

Source: openspec/changes/predictive-causal-scenarios/tasks.md (3.1–3.3)
        openspec/changes/predictive-causal-scenarios/design.md (API Contract)
Evidence:
  - POST /cases/{case_uid}/forecast/generate
  - POST /cases/{case_uid}/forecast/backtest
  - GET  /cases/{case_uid}/forecast/{scenario_id}/explain
  - 高风险自动 HITL 门禁
  - 证据不足降级输出
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/cases/{case_uid}/forecast", tags=["forecast"])


class ForecastGenerateIn(BaseModel):
    hypothesis_uids: list[str]
    assertion_uids: list[str]
    indicator_names: list[str] | None = None
    context: dict | None = None


class ForecastScenarioOut(BaseModel):
    scenario_id: str
    probability: float | None = None
    trigger_conditions: list[str]
    evidence_citations: list[str]
    alternatives: list[str]
    status: str


class ForecastGenerateOut(BaseModel):
    scenarios: list[ForecastScenarioOut]
    action_uid: str
    trace_id: str


class BacktestIn(BaseModel):
    scenario_id: str
    actual_outcomes: list[dict]


class BacktestOut(BaseModel):
    scenario_id: str
    precision: float
    false_alarm: float
    missed_alert: float
    action_uid: str
    trace_id: str


class ExplainOut(BaseModel):
    scenario_id: str
    trigger_conditions: list[str]
    evidence_citations: list[str]
    alternatives: list[str]
    causal_links: list[dict]
    signal_scores: list[dict]


@router.post("/generate", status_code=201)
async def generate_forecast(case_uid: str, body: ForecastGenerateIn) -> ForecastGenerateOut:
    """生成预测情景（桩实现，完整版需注入 service 层）。"""
    return ForecastGenerateOut(
        scenarios=[],
        action_uid="stub",
        trace_id="stub",
    )


@router.post("/backtest", status_code=200)
async def backtest_forecast(case_uid: str, body: BacktestIn) -> BacktestOut:
    """对预测执行回测（桩实现）。"""
    return BacktestOut(
        scenario_id=body.scenario_id,
        precision=0.0,
        false_alarm=0.0,
        missed_alert=0.0,
        action_uid="stub",
        trace_id="stub",
    )


@router.get("/{scenario_id}/explain", status_code=200)
async def explain_forecast(case_uid: str, scenario_id: str) -> ExplainOut:
    """返回预测的可回放解释（桩实现）。"""
    return ExplainOut(
        scenario_id=scenario_id,
        trigger_conditions=[],
        evidence_citations=[],
        alternatives=[],
        causal_links=[],
        signal_scores=[],
    )
