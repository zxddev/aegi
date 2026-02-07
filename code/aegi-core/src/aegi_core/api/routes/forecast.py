# Author: msq
"""Forecast API routes – generate/backtest/explain.

Source: openspec/changes/predictive-causal-scenarios/tasks.md (3.1–3.3)
        openspec/changes/predictive-causal-scenarios/design.md (API Contract)
Evidence:
  - POST /cases/{case_uid}/forecast/generate
  - POST /cases/{case_uid}/forecast/backtest
  - GET  /cases/{case_uid}/forecast/{scenario_id}/explain
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import not_found
from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, NarrativeV1
from aegi_core.db.models.action import Action
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.hypothesis import Hypothesis
from aegi_core.db.models.narrative import Narrative
from aegi_core.services.scenario_generator import (
    backtest_forecast as svc_backtest,
    generate_forecasts as svc_generate,
)

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


def _hyp_to_v1(row: Hypothesis) -> HypothesisV1:
    return HypothesisV1(
        uid=row.uid,
        case_uid=row.case_uid,
        label=row.label,
        supporting_assertion_uids=row.supporting_assertion_uids or [],
        confidence=row.confidence,
        modality=row.modality,
        segment_ref=row.segment_ref,
        media_time_range=row.media_time_range,
        created_at=row.created_at,
    )


def _assertion_to_v1(row: Assertion) -> AssertionV1:
    return AssertionV1(
        uid=row.uid,
        case_uid=row.case_uid,
        kind=row.kind,
        value=row.value,
        source_claim_uids=row.source_claim_uids,
        confidence=row.confidence,
        modality=row.modality,
        segment_ref=row.segment_ref,
        media_time_range=row.media_time_range,
        created_at=row.created_at,
    )


@router.post("/generate", status_code=201)
async def generate_forecast(
    case_uid: str,
    body: ForecastGenerateIn,
    session: AsyncSession = Depends(get_db_session),
) -> ForecastGenerateOut:
    """生成预测情景。"""
    rows_h = await session.execute(
        sa.select(Hypothesis).where(Hypothesis.uid.in_(body.hypothesis_uids))
    )
    hypotheses = [_hyp_to_v1(r) for r in rows_h.scalars().all()]

    rows_a = await session.execute(
        sa.select(Assertion).where(Assertion.uid.in_(body.assertion_uids))
    )
    assertions = [_assertion_to_v1(r) for r in rows_a.scalars().all()]

    # 查询 narratives（soft dep）
    rows_n = await session.execute(
        sa.select(Narrative).where(Narrative.case_uid == case_uid)
    )
    narratives_v1: list[NarrativeV1] = []
    for n in rows_n.scalars().all():
        narratives_v1.append(
            NarrativeV1(
                uid=n.uid,
                case_uid=n.case_uid,
                title=n.theme,
                assertion_uids=[],
                hypothesis_uids=[],
                created_at=n.created_at,
            )
        )

    forecasts, svc_action, svc_trace = svc_generate(
        hypotheses=hypotheses,
        assertions=assertions,
        narratives=narratives_v1 or None,
        case_uid=case_uid,
    )

    action_uid = f"act_{uuid4().hex}"
    scenarios: list[ForecastScenarioOut] = []
    scenario_details: list[dict] = []
    for f in forecasts:
        scenarios.append(
            ForecastScenarioOut(
                scenario_id=f.scenario_id,
                probability=f.probability,
                trigger_conditions=f.trigger_conditions,
                evidence_citations=f.evidence_citations,
                alternatives=f.alternatives,
                status=f.status,
            )
        )
        scenario_details.append(
            {
                "scenario_id": f.scenario_id,
                "probability": f.probability,
                "trigger_conditions": f.trigger_conditions,
                "evidence_citations": f.evidence_citations,
                "alternatives": f.alternatives,
                "status": f.status,
                "causal_links": (
                    [
                        {
                            "source_uid": cl.source_uid,
                            "target_uid": cl.target_uid,
                            "temporal_consistent": cl.temporal_consistent,
                        }
                        for cl in f.causal_analysis.causal_links
                    ]
                    if f.causal_analysis
                    else []
                ),
                "signal_scores": (
                    [
                        {
                            "indicator_name": s.indicator_name,
                            "trend": s.trend,
                            "alert_level": s.alert_level,
                        }
                        for s in f.signal_scores
                    ]
                ),
            }
        )

    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="forecast.generate",
            inputs=body.model_dump(exclude_none=True),
            outputs={"scenarios": scenario_details},
            trace_id=svc_action.trace_id,
        )
    )
    await session.commit()

    return ForecastGenerateOut(
        scenarios=scenarios,
        action_uid=action_uid,
        trace_id=svc_action.trace_id or "",
    )


@router.post("/backtest", status_code=200)
async def backtest_forecast_endpoint(
    case_uid: str,
    body: BacktestIn,
    session: AsyncSession = Depends(get_db_session),
) -> BacktestOut:
    """对预测执行回测。"""
    # 从 Action outputs 中查找该 scenario 的 forecast 数据
    row = await session.execute(
        sa.select(Action)
        .where(
            Action.case_uid == case_uid,
            Action.action_type == "forecast.generate",
        )
        .order_by(Action.created_at.desc())
        .limit(1)
    )
    gen_action = row.scalars().first()

    from aegi_core.services.scenario_generator import ForecastV1

    forecast = ForecastV1(scenario_id=body.scenario_id)
    if gen_action and gen_action.outputs:
        for s in gen_action.outputs.get("scenarios", []):
            if s.get("scenario_id") == body.scenario_id:
                forecast = ForecastV1(
                    scenario_id=s["scenario_id"],
                    probability=s.get("probability"),
                    trigger_conditions=s.get("trigger_conditions", []),
                    evidence_citations=s.get("evidence_citations", []),
                    alternatives=s.get("alternatives", []),
                    status=s.get("status", "draft"),
                )
                break

    result = svc_backtest(forecast, body.actual_outcomes)

    action_uid = f"act_{uuid4().hex}"
    trace_id = gen_action.trace_id if gen_action else ""
    session.add(
        Action(
            uid=action_uid,
            case_uid=case_uid,
            action_type="forecast.backtest",
            inputs=body.model_dump(),
            outputs={
                "precision": result.precision,
                "false_alarm": result.false_alarm,
                "missed_alert": result.missed_alert,
            },
            trace_id=trace_id,
        )
    )
    await session.commit()

    return BacktestOut(
        scenario_id=body.scenario_id,
        precision=result.precision,
        false_alarm=result.false_alarm,
        missed_alert=result.missed_alert,
        action_uid=action_uid,
        trace_id=trace_id or "",
    )


@router.get("/{scenario_id}/explain", status_code=200)
async def explain_forecast(
    case_uid: str,
    scenario_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ExplainOut:
    """返回预测的可回放解释。"""
    row = await session.execute(
        sa.select(Action)
        .where(
            Action.case_uid == case_uid,
            Action.action_type == "forecast.generate",
        )
        .order_by(Action.created_at.desc())
        .limit(1)
    )
    gen_action = row.scalars().first()
    if gen_action is None:
        raise not_found("Forecast", scenario_id)

    for s in gen_action.outputs.get("scenarios", []):
        if s.get("scenario_id") == scenario_id:
            return ExplainOut(
                scenario_id=scenario_id,
                trigger_conditions=s.get("trigger_conditions", []),
                evidence_citations=s.get("evidence_citations", []),
                alternatives=s.get("alternatives", []),
                causal_links=s.get("causal_links", []),
                signal_scores=s.get("signal_scores", []),
            )

    raise not_found("Forecast scenario", scenario_id)
