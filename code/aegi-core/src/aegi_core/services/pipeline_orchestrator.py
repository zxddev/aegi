# Author: msq
"""End-to-end analysis pipeline orchestrator.

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md
Evidence:
  - 每阶段可独立跳过/降级（输入缺失时 skip 而非 fail）。
  - 输出 PipelineResult：每阶段产物 + 耗时 + 状态。
  - 支持从任意阶段开始、只执行指定阶段子集。
  - 纯函数式，不依赖 DB session。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
from aegi_core.services import assertion_fuser, hypothesis_engine, narrative_builder
from aegi_core.services.confidence_scorer import QualityInput, score_confidence
from aegi_core.services.scenario_generator import ForecastV1, generate_forecasts


STAGE_ORDER: list[str] = [
    "assertion_fuse",
    "hypothesis_analyze",
    "narrative_build",
    "forecast_generate",
    "quality_score",
]


@dataclass
class StageResult:
    """单阶段执行结果。"""

    stage: str
    status: str  # success | skipped | degraded | error
    duration_ms: int
    output: Any
    error: str | None = None


@dataclass
class PipelineResult:
    """完整 pipeline 执行结果。"""

    case_uid: str
    stages: list[StageResult] = field(default_factory=list)
    total_duration_ms: int = 0


def _now_ms() -> int:
    return monotonic_ns() // 1_000_000


def _run_stage(name: str, fn: Any) -> StageResult:
    """执行单阶段，捕获异常返回 error 状态。"""
    start = _now_ms()
    try:
        output = fn()
        return StageResult(
            stage=name, status="success", duration_ms=_now_ms() - start, output=output,
        )
    except Exception as exc:
        return StageResult(
            stage=name, status="error", duration_ms=_now_ms() - start,
            output=None, error=str(exc),
        )


class PipelineOrchestrator:
    """端到端分析 pipeline 编排器。"""

    def run_full(
        self,
        *,
        case_uid: str,
        source_claims: list[SourceClaimV1],
        assertions: list[AssertionV1] | None = None,
        hypotheses: list[HypothesisV1] | None = None,
        narratives: list[NarrativeV1] | None = None,
        forecasts: list[ForecastV1] | None = None,
        stages: list[str] | None = None,
        start_from: str | None = None,
    ) -> PipelineResult:
        """执行完整或部分 pipeline。

        Args:
            case_uid: 所属 case。
            source_claims: 输入 source claims。
            assertions: 预置 assertions（跳过 assertion_fuse）。
            hypotheses: 预置 hypotheses（跳过 hypothesis_analyze）。
            narratives: 预置 narratives（跳过 narrative_build）。
            forecasts: 预置 forecasts（跳过 forecast_generate）。
            stages: 只执行指定阶段子集。
            start_from: 从指定阶段开始。

        Returns:
            PipelineResult 包含每阶段产物、耗时、状态。
        """
        pipeline_start = _now_ms()
        result = PipelineResult(case_uid=case_uid)

        active_stages = self._resolve_stages(stages, start_from)

        # -- assertion_fuse --
        if "assertion_fuse" in active_stages:
            if assertions is not None:
                result.stages.append(StageResult(
                    stage="assertion_fuse", status="skipped",
                    duration_ms=0, output=assertions,
                ))
            elif not source_claims:
                result.stages.append(StageResult(
                    stage="assertion_fuse", status="skipped",
                    duration_ms=0, output=[],
                ))
                assertions = []
            else:
                sr = _run_stage("assertion_fuse", lambda: assertion_fuser.fuse_claims(
                    source_claims, case_uid=case_uid,
                ))
                if sr.status == "success":
                    assertions = sr.output[0]  # (assertions, conflict_set, action, trace)
                else:
                    assertions = []
                result.stages.append(sr)
        if assertions is None:
            assertions = []

        # -- hypothesis_analyze --
        if "hypothesis_analyze" in active_stages:
            if hypotheses is not None:
                result.stages.append(StageResult(
                    stage="hypothesis_analyze", status="skipped",
                    duration_ms=0, output=hypotheses,
                ))
            elif not assertions:
                result.stages.append(StageResult(
                    stage="hypothesis_analyze", status="skipped",
                    duration_ms=0, output=[],
                ))
                hypotheses = []
            else:
                sr = _run_stage("hypothesis_analyze", lambda: [
                    _ach_to_hypothesis(r, case_uid)
                    for r in [
                        hypothesis_engine.analyze_hypothesis(
                            "Auto-generated hypothesis from assertions",
                            assertions, source_claims,
                        )
                    ]
                ])
                if sr.status == "success":
                    hypotheses = sr.output
                else:
                    hypotheses = []
                result.stages.append(sr)
        if hypotheses is None:
            hypotheses = []

        # -- narrative_build --
        if "narrative_build" in active_stages:
            if narratives is not None:
                result.stages.append(StageResult(
                    stage="narrative_build", status="skipped",
                    duration_ms=0, output=narratives,
                ))
            elif not source_claims:
                result.stages.append(StageResult(
                    stage="narrative_build", status="skipped",
                    duration_ms=0, output=[],
                ))
                narratives = []
            else:
                sr = _run_stage("narrative_build", lambda: narrative_builder.build_narratives(
                    source_claims,
                ))
                if sr.status == "success":
                    narratives = sr.output
                else:
                    narratives = []
                result.stages.append(sr)
        if narratives is None:
            narratives = []

        # -- forecast_generate --
        if "forecast_generate" in active_stages:
            if forecasts is not None:
                result.stages.append(StageResult(
                    stage="forecast_generate", status="skipped",
                    duration_ms=0, output=forecasts,
                ))
            elif not hypotheses:
                result.stages.append(StageResult(
                    stage="forecast_generate", status="skipped",
                    duration_ms=0, output=[],
                ))
                forecasts = []
            else:
                sr = _run_stage("forecast_generate", lambda: generate_forecasts(
                    hypotheses=hypotheses,
                    assertions=assertions,
                    narratives=narratives,
                    case_uid=case_uid,
                ))
                if sr.status == "success":
                    forecasts = sr.output[0]  # (forecasts, action, trace)
                else:
                    forecasts = []
                result.stages.append(sr)
        if forecasts is None:
            forecasts = []

        # -- quality_score --
        if "quality_score" in active_stages:
            sr = _run_stage("quality_score", lambda: score_confidence(QualityInput(
                judgment_uid=f"pipeline-{uuid.uuid4().hex[:8]}",
                case_uid=case_uid,
                title="Pipeline quality assessment",
                assertions=assertions,
                hypotheses=hypotheses,
                narratives=narratives,
                source_claims=source_claims,
                forecasts=[{"scenario_id": f.scenario_id} for f in forecasts] if forecasts else None,
            )))
            result.stages.append(sr)

        result.total_duration_ms = _now_ms() - pipeline_start
        return result

    def run_stage(self, stage_name: str, inputs: dict) -> StageResult:
        """执行单个阶段。

        Args:
            stage_name: 阶段名称。
            inputs: 阶段输入参数。

        Returns:
            StageResult。
        """
        case_uid = inputs.get("case_uid", "unknown")
        source_claims = inputs.get("source_claims", [])
        assertions = inputs.get("assertions", [])
        hypotheses = inputs.get("hypotheses", [])
        narratives = inputs.get("narratives", [])

        r = self.run_full(
            case_uid=case_uid,
            source_claims=source_claims,
            assertions=assertions if stage_name != "assertion_fuse" else None,
            hypotheses=hypotheses if stage_name != "hypothesis_analyze" else None,
            narratives=narratives if stage_name != "narrative_build" else None,
            stages=[stage_name],
        )
        if r.stages:
            return r.stages[0]
        return StageResult(stage=stage_name, status="skipped", duration_ms=0, output=None)

    @staticmethod
    def _resolve_stages(
        stages: list[str] | None,
        start_from: str | None,
    ) -> list[str]:
        """解析要执行的阶段列表。"""
        if stages is not None:
            return [s for s in STAGE_ORDER if s in stages]
        if start_from is not None and start_from in STAGE_ORDER:
            idx = STAGE_ORDER.index(start_from)
            return STAGE_ORDER[idx:]
        return list(STAGE_ORDER)


def _ach_to_hypothesis(
    ach: hypothesis_engine.ACHResult,
    case_uid: str,
) -> HypothesisV1:
    """将 ACHResult 转换为 HypothesisV1。"""
    from datetime import datetime, timezone

    return HypothesisV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        label=ach.hypothesis_text[:120],
        supporting_assertion_uids=ach.supporting_assertion_uids,
        confidence=ach.confidence,
        created_at=datetime.now(timezone.utc),
    )
