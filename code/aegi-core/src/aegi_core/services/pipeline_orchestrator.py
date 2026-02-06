# Author: msq
"""End-to-end analysis pipeline orchestrator.

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md
Evidence:
  - 每阶段可独立跳过/降级（输入缺失时 skip 而非 fail）。
  - 输出 PipelineResult：每阶段产物 + 耗时 + 状态。
  - 支持从任意阶段开始、只执行指定阶段子集。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
    "kg_build",
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
    ) -> None:
        self._llm = llm
        self._neo4j = neo4j_store

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
        hypotheses, result = self._stage_hypothesis_sync(
            active,
            case_uid,
            assertions,
            source_claims,
            hypotheses,
            result,
        )
        # narrative_build (sync)
        narratives, result = self._stage_narrative(active, source_claims, narratives, result)

        # kg_build — skipped in sync mode (no Neo4j)
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

        # assertion_fuse (sync, rule-based)
        assertions, result = self._stage_assertion_fuse(
            active,
            case_uid,
            source_claims,
            assertions,
            result,
        )

        # hypothesis_analyze — use LLM if available
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
                hypotheses, result = self._stage_hypothesis_sync(
                    active,
                    case_uid,
                    assertions,
                    source_claims,
                    hypotheses,
                    result,
                )
        if hypotheses is None:
            hypotheses = []

        # narrative_build (sync)
        narratives, result = self._stage_narrative(active, source_claims, narratives, result)

        # kg_build — write to Neo4j if available
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
        return result

    # ── LLM hypothesis generation ─────────────────────────────────

    async def _hypothesis_with_llm(
        self,
        assertions: list[AssertionV1],
        source_claims: list[SourceClaimV1],
        case_uid: str,
    ) -> list[HypothesisV1]:
        """Use LLM to generate hypotheses, then run ACH analysis."""
        # Build a concise evidence summary for the LLM
        evidence_lines = []
        for a in assertions[:20]:
            evidence_lines.append(f"- [{a.kind}] {a.value}")
        evidence_text = "\n".join(evidence_lines)

        prompt = (
            f"Based on the following intelligence assertions, generate 3-5 competing "
            f"hypotheses that could explain the evidence. For each hypothesis, provide "
            f"a clear statement.\n\nAssertions:\n{evidence_text}\n\n"
            f"Return each hypothesis on a separate line, prefixed with 'H:'"
        )

        result = await self._llm.invoke(prompt, model="default")
        text = result.get("text", "")

        # Parse hypotheses from LLM output
        hypotheses: list[HypothesisV1] = []

        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("H:"):
                h_text = line[2:].strip()
            elif line and len(line) > 10:
                h_text = line.lstrip("0123456789.-) ").strip()
            else:
                continue
            if not h_text:
                continue

            # Run ACH analysis on each hypothesis
            ach = hypothesis_engine.analyze_hypothesis(h_text, assertions, source_claims)
            hypotheses.append(_ach_to_hypothesis(ach, case_uid))

        # Fallback: if LLM didn't produce usable hypotheses, use rule-based
        if not hypotheses:
            ach = hypothesis_engine.analyze_hypothesis(
                "Auto-generated hypothesis from assertions",
                assertions,
                source_claims,
            )
            hypotheses.append(_ach_to_hypothesis(ach, case_uid))

        return hypotheses

    # ── KG build + Neo4j write ────────────────────────────────────

    async def _kg_build_and_write(
        self,
        assertions: list[AssertionV1],
        case_uid: str,
    ) -> dict:
        """Build KG from assertions and write to Neo4j."""
        from aegi_core.services import kg_mapper

        result = kg_mapper.build_graph(
            assertions,
            case_uid=case_uid,
            ontology_version="v1",
        )
        # build_graph returns 5-tuple on success, 6-tuple on error
        if len(result) == 6:
            return {"error": str(result[5])}

        entities, events, relations, action, trace = result

        # Write to Neo4j
        neo = self._neo4j
        await neo.upsert_nodes(
            "Entity",
            [
                {"uid": e.uid, "name": e.label, "type": e.entity_type, "case_uid": e.case_uid}
                for e in entities
            ],
        )
        await neo.upsert_nodes(
            "Event",
            [
                {
                    "uid": e.uid,
                    "label": e.label,
                    "type": e.event_type,
                    "case_uid": e.case_uid,
                    "timestamp_ref": e.timestamp_ref,
                }
                for e in events
            ],
        )
        for r in relations:
            await neo.upsert_edges(
                "Entity" if any(e.uid == r.source_entity_uid for e in entities) else "Event",
                "Entity" if any(e.uid == r.target_entity_uid for e in entities) else "Event",
                r.relation_type.upper(),
                [
                    {
                        "source_uid": r.source_entity_uid,
                        "target_uid": r.target_entity_uid,
                        "properties": r.properties,
                    }
                ],
            )

        return {
            "entities": len(entities),
            "events": len(events),
            "relations": len(relations),
        }

    # ── shared stage helpers ──────────────────────────────────────

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
                    StageResult(stage=stage_name, status="skipped",
                                duration_ms=0, output=existing)
                )
            elif not inputs:
                result.stages.append(
                    StageResult(stage=stage_name, status="skipped",
                                duration_ms=0, output=[])
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
            active, "assertion_fuse", assertions, source_claims,
            lambda: assertion_fuser.fuse_claims(source_claims, case_uid=case_uid),
            result, unpack_first=True,
        )

    def _stage_hypothesis_sync(
        self,
        active: list[str],
        case_uid: str,
        assertions: list[AssertionV1],
        source_claims: list[SourceClaimV1],
        hypotheses: list[HypothesisV1] | None,
        result: PipelineResult,
    ) -> tuple[list[HypothesisV1], PipelineResult]:
        return self._run_or_skip(
            active, "hypothesis_analyze", hypotheses, assertions,
            lambda: [
                _ach_to_hypothesis(r, case_uid)
                for r in [
                    hypothesis_engine.analyze_hypothesis(
                        "Auto-generated hypothesis from assertions",
                        assertions, source_claims,
                    )
                ]
            ],
            result,
        )

    def _stage_narrative(
        self,
        active: list[str],
        source_claims: list[SourceClaimV1],
        narratives: list[NarrativeV1] | None,
        result: PipelineResult,
    ) -> tuple[list[NarrativeV1], PipelineResult]:
        return self._run_or_skip(
            active, "narrative_build", narratives, source_claims,
            lambda: narrative_builder.build_narratives(source_claims),
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
            active, "forecast_generate", forecasts, hypotheses,
            lambda: generate_forecasts(
                hypotheses=hypotheses, assertions=assertions,
                narratives=narratives, case_uid=case_uid,
            ),
            result, unpack_first=True,
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


def _ach_to_hypothesis(ach: hypothesis_engine.ACHResult, case_uid: str) -> HypothesisV1:
    return HypothesisV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        label=ach.hypothesis_text[:120],
        supporting_assertion_uids=ach.supporting_assertion_uids,
        confidence=ach.confidence,
        created_at=datetime.now(timezone.utc),
    )
