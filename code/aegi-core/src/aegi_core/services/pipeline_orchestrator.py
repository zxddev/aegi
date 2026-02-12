# Author: msq
"""端到端分析 pipeline 编排器。

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md
Evidence:
  - 每阶段可独立跳过/降级（输入缺失时 skip 而非 fail）。
  - 输出 PipelineResult：每阶段产物 + 耗时 + 状态。
  - 支持从任意阶段开始、只执行指定阶段子集。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Any

from pydantic import BaseModel

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
from aegi_core.services import assertion_fuser, hypothesis_engine, narrative_builder
from aegi_core.services.confidence_scorer import QualityInput, score_confidence
from aegi_core.services.scenario_generator import ForecastV1, generate_forecasts


class HypothesisListOutput(BaseModel):
    """LLM 假设生成的结构化输出模型。"""

    hypotheses: list[str]


STAGE_ORDER: list[str] = [
    "assertion_fuse",
    "hypothesis_analyze",
    "adversarial_evaluate",
    "narrative_build",
    "kg_build",
    "forecast_generate",
    "quality_score",
    "report_generate",
]


@dataclass
class StageResult:
    """单阶段执行结果。"""

    stage: str
    status: str  # success | skipped | degraded | error
    duration_ms: int
    output: Any
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


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
            stage=name,
            status="success",
            duration_ms=_now_ms() - start,
            output=output,
        )
    except Exception as exc:
        return StageResult(
            stage=name,
            status="error",
            duration_ms=_now_ms() - start,
            output=None,
            error=str(exc),
        )


async def _run_stage_async(name: str, coro: Any) -> StageResult:
    """执行异步阶段。"""
    start = _now_ms()
    try:
        output = await coro
        return StageResult(
            stage=name,
            status="success",
            duration_ms=_now_ms() - start,
            output=output,
        )
    except Exception as exc:
        return StageResult(
            stage=name,
            status="error",
            duration_ms=_now_ms() - start,
            output=None,
            error=str(exc),
        )


class PipelineOrchestrator:
    """端到端分析 pipeline 编排器。

    可选注入 llm / neo4j_store，注入后启用 LLM 假设生成和 KG 写入。
    """

    def __init__(
        self,
        llm: Any | None = None,
        neo4j_store: Any | None = None,
        analysis_memory: Any | None = None,
    ) -> None:
        self._llm = llm
        self._neo4j = neo4j_store
        self._analysis_memory = analysis_memory

    async def run_playbook(
        self,
        *,
        playbook_name: str = "default",
        case_uid: str,
        source_claims: list[SourceClaimV1],
        on_progress: Any | None = None,
    ) -> PipelineResult:
        """执行命名 Playbook，使用可插拔的阶段注册表。

        替代原来硬编码阶段逻辑的新入口。
        ``run_full_async`` 保留用于向后兼容。

        Args:
            on_progress: 可选异步回调 (stage_name, status, percent, message)。
        """
        from aegi_core.services.stages.base import StageContext, stage_registry
        from aegi_core.services.stages.playbook import get_playbook

        pb = get_playbook(playbook_name)
        ctx = StageContext(
            case_uid=case_uid,
            source_claims=source_claims,
            llm=self._llm,
            neo4j=self._neo4j,
            config={},
            on_progress=on_progress,
        )

        pipeline_start = _now_ms()
        result = PipelineResult(case_uid=case_uid)
        stages = stage_registry.ordered(pb.stages)
        total = len(stages) or 1

        for i, stage in enumerate(stages):
            ctx.config = pb.stage_config.get(stage.name, {})

            if on_progress:
                await on_progress(
                    stage.name, "starting", (i / total) * 100, f"Starting {stage.name}"
                )

            skip_reason = stage.should_skip(ctx)
            if skip_reason:
                result.stages.append(
                    StageResult(
                        stage=stage.name,
                        status="skipped",
                        duration_ms=0,
                        output=None,
                        error=skip_reason,
                    )
                )
                if on_progress:
                    await on_progress(
                        stage.name, "skipped", ((i + 1) / total) * 100, skip_reason
                    )
                continue

            sr = await stage.run(ctx)
            result.stages.append(sr)

            if on_progress:
                await on_progress(stage.name, sr.status, ((i + 1) / total) * 100, "")

        result.total_duration_ms = _now_ms() - pipeline_start

        # ── 发送 pipeline.completed 事件 ──
        from aegi_core.services.event_bus import get_event_bus, AegiEvent

        bus = get_event_bus()
        await bus.emit(
            AegiEvent(
                event_type="pipeline.completed",
                case_uid=case_uid,
                payload={
                    "summary": f"Pipeline '{playbook_name}' completed: "
                    f"{sum(1 for s in result.stages if s.status == 'success')}/{len(result.stages)} stages OK",
                    "playbook": playbook_name,
                    "duration_ms": result.total_duration_ms,
                    "stage_results": {s.stage: s.status for s in result.stages},
                },
                severity="medium",
                source_event_uid=f"pipeline:{case_uid}:{playbook_name}:{result.total_duration_ms}",
            )
        )

        await self._maybe_record_analysis_memory(case_uid)

        return result

    # ── sync 入口（向后兼容，不用 LLM/Neo4j）──────────────────────

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
        """同步执行（规则模式，向后兼容）。"""
        pipeline_start = _now_ms()
        result = PipelineResult(case_uid=case_uid)
        active = self._resolve_stages(stages, start_from)

        assertions, result = self._stage_assertion_fuse(
            active,
            case_uid,
            source_claims,
            assertions,
            result,
        )
        # hypothesis_analyze — sync 模式下 skip（需要 LLM）
        if "hypothesis_analyze" in active:
            if hypotheses is not None:
                result.stages.append(
                    StageResult(
                        stage="hypothesis_analyze",
                        status="skipped",
                        duration_ms=0,
                        output=hypotheses,
                    )
                )
            else:
                result.stages.append(
                    StageResult(
                        stage="hypothesis_analyze",
                        status="skipped",
                        duration_ms=0,
                        output=[],
                    )
                )
                hypotheses = []
        if hypotheses is None:
            hypotheses = []
        # adversarial_evaluate — sync 模式下 skip（需要 LLM）
        if "adversarial_evaluate" in active:
            result.stages.append(
                StageResult(
                    stage="adversarial_evaluate",
                    status="skipped",
                    duration_ms=0,
                    output=None,
                )
            )
        # narrative_build (sync)
        narratives, result = self._stage_narrative(
            active, source_claims, assertions, narratives, result
        )

        # kg_build — 同步模式下跳过（无 Neo4j）
        if "kg_build" in active:
            result.stages.append(
                StageResult(
                    stage="kg_build",
                    status="skipped",
                    duration_ms=0,
                    output=None,
                )
            )

        # forecast_generate (sync)
        forecasts, result = self._stage_forecast(
            active,
            case_uid,
            assertions,
            hypotheses,
            narratives,
            forecasts,
            result,
        )
        result = self._stage_quality(
            active,
            case_uid,
            assertions,
            hypotheses,
            narratives,
            source_claims,
            forecasts,
            result,
        )
        # report_generate — sync 模式下 skip（需要 DB）
        if "report_generate" in active:
            result.stages.append(
                StageResult(
                    stage="report_generate",
                    status="skipped",
                    duration_ms=0,
                    output=None,
                )
            )
        result.total_duration_ms = _now_ms() - pipeline_start
        return result

    # ── async 入口（LLM + Neo4j）──────────────────────────────────

    async def run_full_async(
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
        """异步执行，使用 LLM 生成假设，写入 Neo4j。"""
        pipeline_start = _now_ms()
        result = PipelineResult(case_uid=case_uid)
        active = self._resolve_stages(stages, start_from)

        # assertion_fuse (同步规则 + 异步 LLM 语义冲突检测)
        assertions, result = self._stage_assertion_fuse(
            active,
            case_uid,
            source_claims,
            assertions,
            result,
        )
        # LLM 语义冲突检测（追加到 assertion_fuse 阶段结果）
        if "assertion_fuse" in active and self._llm is not None and source_claims:
            try:
                from aegi_core.services.assertion_fuser import (
                    adetect_semantic_conflicts,
                )

                sem_conflicts = await adetect_semantic_conflicts(
                    source_claims, llm=self._llm
                )
                if sem_conflicts:
                    # 追加到 assertion_fuse 阶段的 output
                    for sr in result.stages:
                        if sr.stage == "assertion_fuse" and sr.status == "success":
                            sr.output = (sr.output, sem_conflicts)
                            break
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "LLM 语义冲突检测在 pipeline 中失败",
                    exc_info=True,
                    extra={"degraded": True, "component": "assertion_fuser"},
                )

        # hypothesis_analyze — 必须有 LLM，不降级
        if "hypothesis_analyze" in active:
            if hypotheses is not None:
                result.stages.append(
                    StageResult(
                        stage="hypothesis_analyze",
                        status="skipped",
                        duration_ms=0,
                        output=hypotheses,
                    )
                )
            elif not assertions:
                result.stages.append(
                    StageResult(
                        stage="hypothesis_analyze",
                        status="skipped",
                        duration_ms=0,
                        output=[],
                    )
                )
                hypotheses = []
            elif self._llm is not None:
                sr = await _run_stage_async(
                    "hypothesis_analyze",
                    self._hypothesis_with_llm(assertions, source_claims, case_uid),
                )
                hypotheses = sr.output if sr.status == "success" and sr.output else []
                result.stages.append(sr)
            else:
                # 无 LLM = hard error，不 fallback 到规则引擎
                result.stages.append(
                    StageResult(
                        stage="hypothesis_analyze",
                        status="error",
                        duration_ms=0,
                        output=None,
                    )
                )
                hypotheses = []
        if hypotheses is None:
            hypotheses = []

        # adversarial_evaluate — LLM 三角对抗评估
        if "adversarial_evaluate" in active:
            if self._llm is not None and hypotheses:
                sr = await _run_stage_async(
                    "adversarial_evaluate",
                    self._adversarial_with_llm(
                        hypotheses, assertions, source_claims, case_uid
                    ),
                )
                result.stages.append(sr)
            else:
                result.stages.append(
                    StageResult(
                        stage="adversarial_evaluate",
                        status="skipped",
                        duration_ms=0,
                        output=None,
                    )
                )

        # narrative_build（async + embedding）
        if "narrative_build" in active:
            if narratives is not None:
                result.stages.append(
                    StageResult(
                        stage="narrative_build",
                        status="skipped",
                        duration_ms=0,
                        output=narratives,
                    )
                )
            elif not source_claims:
                result.stages.append(
                    StageResult(
                        stage="narrative_build",
                        status="skipped",
                        duration_ms=0,
                        output=[],
                    )
                )
                narratives = []
            else:
                embed_fn = self._llm.embed if self._llm is not None else None
                sr = await _run_stage_async(
                    "narrative_build",
                    narrative_builder.abuild_narratives_with_uids(
                        source_claims,
                        embed_fn=embed_fn,
                        assertions=assertions,
                    ),
                )
                narratives = (
                    sr.output[0] if sr.status == "success" and sr.output else []
                )
                result.stages.append(sr)
        if narratives is None:
            narratives = []

        # kg_build — 有 Neo4j 时写入
        if "kg_build" in active and self._neo4j is not None and assertions:
            sr = await _run_stage_async(
                "kg_build",
                self._kg_build_and_write(assertions, case_uid),
            )
            result.stages.append(sr)
        elif "kg_build" in active:
            result.stages.append(
                StageResult(
                    stage="kg_build",
                    status="skipped",
                    duration_ms=0,
                    output=None,
                )
            )

        # forecast_generate（async + LLM）
        if "forecast_generate" in active:
            if forecasts is not None:
                result.stages.append(
                    StageResult(
                        stage="forecast_generate",
                        status="skipped",
                        duration_ms=0,
                        output=forecasts,
                    )
                )
            elif not hypotheses:
                result.stages.append(
                    StageResult(
                        stage="forecast_generate",
                        status="skipped",
                        duration_ms=0,
                        output=[],
                    )
                )
                forecasts = []
            else:
                from aegi_core.services.scenario_generator import agenerate_forecasts

                sr = await _run_stage_async(
                    "forecast_generate",
                    agenerate_forecasts(
                        hypotheses=hypotheses,
                        assertions=assertions,
                        narratives=narratives,
                        case_uid=case_uid,
                        llm=self._llm,
                    ),
                )
                if sr.status == "success" and sr.output:
                    forecasts = sr.output[0]  # tuple[list[ForecastV1], ...]
                else:
                    forecasts = []
                result.stages.append(sr)
        if forecasts is None:
            forecasts = []

        # quality_score (sync)
        result = self._stage_quality(
            active,
            case_uid,
            assertions,
            hypotheses,
            narratives,
            source_claims,
            forecasts,
            result,
        )

        result.total_duration_ms = _now_ms() - pipeline_start
        await self._maybe_record_analysis_memory(case_uid)
        return result

    # ── LLM 对抗评估 ────────────────────────────────

    async def _adversarial_with_llm(
        self,
        hypotheses: list[HypothesisV1],
        assertions: list[AssertionV1],
        source_claims: list[SourceClaimV1],
        case_uid: str,
    ) -> list[dict]:
        """对每个假设执行 LLM 三角对抗评估。"""
        from aegi_core.services.hypothesis_adversarial import aevaluate_adversarial
        from aegi_core.services.hypothesis_engine import ACHResult

        results = []
        for hyp in hypotheses:
            ach = ACHResult(
                hypothesis_text=hyp.label,
                supporting_assertion_uids=hyp.supporting_assertion_uids,
                confidence=hyp.confidence or 0.0,
            )
            adv, _, _ = await aevaluate_adversarial(
                ach,
                assertions,
                source_claims,
                case_uid=case_uid,
                llm=self._llm,
            )
            results.append({"hypothesis_uid": hyp.uid, "adversarial": adv})
        return results

    # ── LLM 假设生成 ─────────────────────────────────

    async def _hypothesis_with_llm(
        self,
        assertions: list[AssertionV1],
        source_claims: list[SourceClaimV1],
        case_uid: str,
    ) -> list[HypothesisV1]:
        """用 LLM 生成假设并执行 LLM ACH 分析。"""
        assert self._llm is not None  # noqa: S101
        # 构建证据摘要
        evidence_lines = [f"- [{a.kind}] {a.value}" for a in assertions[:20]]
        evidence_text = "\n".join(evidence_lines)

        prompt = (
            f"Based on the following intelligence assertions, generate 3-5 competing "
            f"hypotheses that could explain the evidence. For each hypothesis, provide "
            f"a clear statement.\n\nAssertions:\n{evidence_text}\n\n"
            f'Return a JSON object with a single key "hypotheses" containing a list '
            f"of hypothesis strings. Example:\n"
            f'{{"hypotheses": ["Hypothesis one", "Hypothesis two"]}}'
        )

        parsed = await self._llm.invoke_structured(
            prompt,
            HypothesisListOutput,
            max_tokens=2048,
        )

        hypotheses: list[HypothesisV1] = []
        for h_text in parsed.hypotheses:
            h_text = h_text.strip()
            if not h_text or len(h_text) < 10:
                continue

            # 用 LLM 执行 ACH 分析（替代规则引擎）
            ach = await hypothesis_engine.analyze_hypothesis_llm(
                h_text, assertions, llm=self._llm
            )
            hypotheses.append(_ach_to_hypothesis(ach, case_uid))

        if not hypotheses:
            raise RuntimeError("LLM 未能生成有效假设")

        return hypotheses

    # ── KG 构建 + Neo4j 写入 ────────────────────────────────────

    async def _kg_build_and_write(
        self,
        assertions: list[AssertionV1],
        case_uid: str,
    ) -> dict:
        """用 GraphRAG 从 assertions 构建 KG 并写入 Neo4j。"""
        from aegi_core.services.graphrag_pipeline import extract_and_index

        result = await extract_and_index(
            assertions,
            case_uid=case_uid,
            ontology_version="v1",
            llm=self._llm,
            neo4j=self._neo4j,
        )
        if not result.ok:
            return {"error": str(result.error)}

        return {
            "entities": len(result.entities),
            "events": len(result.events),
            "relations": len(result.relations),
        }

    # ── 共用阶段辅助方法 ──────────────────────────────────────

    @staticmethod
    def _run_or_skip(
        active: list[str],
        stage_name: str,
        existing: list | None,
        inputs: list,
        fn: Any,
        result: PipelineResult,
        *,
        unpack_first: bool = False,
    ) -> tuple[list, PipelineResult]:
        """通用三分支阶段执行：已提供→skip / 输入为空→skip+[] / else→_run_stage。"""
        if stage_name in active:
            if existing is not None:
                result.stages.append(
                    StageResult(
                        stage=stage_name,
                        status="skipped",
                        duration_ms=0,
                        output=existing,
                    )
                )
            elif not inputs:
                result.stages.append(
                    StageResult(
                        stage=stage_name, status="skipped", duration_ms=0, output=[]
                    )
                )
                existing = []
            else:
                sr = _run_stage(stage_name, fn)
                if sr.status == "success":
                    existing = sr.output[0] if unpack_first else sr.output
                else:
                    existing = []
                result.stages.append(sr)
        if existing is None:
            existing = []
        return existing, result

    def _stage_assertion_fuse(
        self,
        active: list[str],
        case_uid: str,
        source_claims: list[SourceClaimV1],
        assertions: list[AssertionV1] | None,
        result: PipelineResult,
    ) -> tuple[list[AssertionV1], PipelineResult]:
        return self._run_or_skip(
            active,
            "assertion_fuse",
            assertions,
            source_claims,
            lambda: assertion_fuser.fuse_claims(source_claims, case_uid=case_uid),
            result,
            unpack_first=True,
        )

    def _stage_narrative(
        self,
        active: list[str],
        source_claims: list[SourceClaimV1],
        assertions: list[AssertionV1],
        narratives: list[NarrativeV1] | None,
        result: PipelineResult,
    ) -> tuple[list[NarrativeV1], PipelineResult]:
        return self._run_or_skip(
            active,
            "narrative_build",
            narratives,
            source_claims,
            lambda: narrative_builder.build_narratives(
                source_claims, assertions=assertions
            ),
            result,
        )

    def _stage_forecast(
        self,
        active: list[str],
        case_uid: str,
        assertions: list[AssertionV1],
        hypotheses: list[HypothesisV1],
        narratives: list[NarrativeV1],
        forecasts: list[ForecastV1] | None,
        result: PipelineResult,
    ) -> tuple[list[ForecastV1], PipelineResult]:
        return self._run_or_skip(
            active,
            "forecast_generate",
            forecasts,
            hypotheses,
            lambda: generate_forecasts(
                hypotheses=hypotheses,
                assertions=assertions,
                narratives=narratives,
                case_uid=case_uid,
            ),
            result,
            unpack_first=True,
        )

    def _stage_quality(
        self,
        active: list[str],
        case_uid: str,
        assertions: list[AssertionV1],
        hypotheses: list[HypothesisV1],
        narratives: list[NarrativeV1],
        source_claims: list[SourceClaimV1],
        forecasts: list[ForecastV1],
        result: PipelineResult,
    ) -> PipelineResult:
        if "quality_score" in active:
            sr = _run_stage(
                "quality_score",
                lambda: score_confidence(
                    QualityInput(
                        judgment_uid=f"pipeline-{uuid.uuid4().hex[:8]}",
                        case_uid=case_uid,
                        title="Pipeline quality assessment",
                        assertions=assertions,
                        hypotheses=hypotheses,
                        narratives=narratives,
                        source_claims=source_claims,
                        forecasts=[{"scenario_id": f.scenario_id} for f in forecasts]
                        if forecasts
                        else None,
                    )
                ),
            )
            result.stages.append(sr)
        return result

    def run_stage(self, stage_name: str, inputs: dict) -> StageResult:
        """执行单个阶段（同步）。"""
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
        return (
            r.stages[0]
            if r.stages
            else StageResult(
                stage=stage_name,
                status="skipped",
                duration_ms=0,
                output=None,
            )
        )

    @staticmethod
    def _resolve_stages(
        stages: list[str] | None,
        start_from: str | None,
    ) -> list[str]:
        if stages is not None:
            return [s for s in STAGE_ORDER if s in stages]
        if start_from is not None and start_from in STAGE_ORDER:
            return STAGE_ORDER[STAGE_ORDER.index(start_from) :]
        return list(STAGE_ORDER)

    async def _maybe_record_analysis_memory(self, case_uid: str) -> None:
        from aegi_core.settings import settings

        if not settings.analysis_memory_enabled:
            return
        try:
            if self._analysis_memory is not None:
                await self._analysis_memory.record(case_uid)
                return
            if self._llm is None:
                return
            from aegi_core.api.deps import get_analysis_memory_qdrant_store
            from aegi_core.db.session import ENGINE
            from aegi_core.services.analysis_memory import AnalysisMemory
            from sqlalchemy.ext.asyncio import AsyncSession

            qdrant = get_analysis_memory_qdrant_store()
            await qdrant.connect()
            async with AsyncSession(ENGINE, expire_on_commit=False) as session:
                memory = AnalysisMemory(
                    db_session=session,
                    qdrant=qdrant,
                    llm=self._llm,
                )
                await memory.record(case_uid)
        except Exception:
            logging.getLogger(__name__).warning(
                "Analysis memory record failed: case=%s",
                case_uid,
                exc_info=True,
            )


def _ach_to_hypothesis(ach: hypothesis_engine.ACHResult, case_uid: str) -> HypothesisV1:
    return HypothesisV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        label=ach.hypothesis_text[:120],
        supporting_assertion_uids=ach.supporting_assertion_uids,
        confidence=ach.confidence,
        created_at=datetime.now(timezone.utc),
    )
