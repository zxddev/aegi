"""内置分析阶段，封装已有的流水线逻辑。

每个类通过 ``_StageRegistry`` 的 ``AnalysisStage.__subclasses__()`` 自动发现。
"""

from __future__ import annotations

import uuid
from time import monotonic_ns
from typing import Any

from aegi_core.services.pipeline_orchestrator import StageResult
from aegi_core.services.stages.base import AnalysisStage, StageContext


def _ms() -> int:
    return monotonic_ns() // 1_000_000


async def _safe(name: str, coro: Any) -> StageResult:
    t = _ms()
    try:
        out = await coro
        return StageResult(
            stage=name, status="success", duration_ms=_ms() - t, output=out
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Stage %s failed: %s",
            name,
            exc,
            exc_info=True,
        )
        return StageResult(
            stage=name,
            status="error",
            duration_ms=_ms() - t,
            output=None,
            error=str(exc),
        )


def _sync(name: str, fn: Any) -> StageResult:
    t = _ms()
    try:
        out = fn()
        return StageResult(
            stage=name, status="success", duration_ms=_ms() - t, output=out
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Stage %s failed: %s",
            name,
            exc,
            exc_info=True,
        )
        return StageResult(
            stage=name,
            status="error",
            duration_ms=_ms() - t,
            output=None,
            error=str(exc),
        )


def _skip(name: str, output: Any = None) -> StageResult:
    return StageResult(stage=name, status="skipped", duration_ms=0, output=output)


# ---------------------------------------------------------------------------
# 1. Assertion Fuse
# ---------------------------------------------------------------------------
class AssertionFuseStage(AnalysisStage):
    name = "assertion_fuse"

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services import assertion_fuser

        if not ctx.source_claims:
            return _skip(self.name, [])
        sr = _sync(
            self.name,
            lambda: assertion_fuser.fuse_claims(
                ctx.source_claims,
                case_uid=ctx.case_uid,
            ),
        )
        if sr.status == "success" and sr.output:
            ctx.assertions = sr.output[0] if isinstance(sr.output, tuple) else sr.output
        # LLM 语义冲突检测
        if ctx.llm and ctx.source_claims and sr.status == "success":
            try:
                from aegi_core.services.assertion_fuser import (
                    adetect_semantic_conflicts,
                )

                conflicts = await adetect_semantic_conflicts(
                    ctx.source_claims, llm=ctx.llm
                )
                if conflicts:
                    sr.output = (sr.output, conflicts)
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "LLM semantic conflict detection failed",
                    exc_info=True,
                    extra={"degraded": True, "component": "assertion_fuser"},
                )
        return sr


# ---------------------------------------------------------------------------
# 2. Hypothesis Analyze
# ---------------------------------------------------------------------------
class HypothesisAnalyzeStage(AnalysisStage):
    name = "hypothesis_analyze"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.assertions:
            return "no assertions"
        if ctx.llm is None:
            return "no LLM"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.contracts.llm_governance import BudgetContext
        from aegi_core.services import hypothesis_engine

        budget = BudgetContext(max_tokens=4096, max_cost_usd=1.0)
        sr = await _safe(
            self.name,
            hypothesis_engine.generate_hypotheses(
                assertions=ctx.assertions,
                source_claims=ctx.source_claims,
                case_uid=ctx.case_uid,
                llm=ctx.llm,
                budget=budget,
            ),
        )
        if sr.status == "success" and sr.output:
            # generate_hypotheses 返回元组 (results, action, trace, llm_result)
            ctx.hypotheses = sr.output[0] if isinstance(sr.output, tuple) else sr.output
        return sr


# ---------------------------------------------------------------------------
# 3. Adversarial Evaluate
# ---------------------------------------------------------------------------
class AdversarialEvaluateStage(AnalysisStage):
    name = "adversarial_evaluate"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.hypotheses:
            return "no hypotheses"
        if ctx.llm is None:
            return "no LLM"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services.hypothesis_adversarial import aevaluate_adversarial
        from aegi_core.services.hypothesis_engine import ACHResult

        async def _run_all():
            results = []
            for hyp in ctx.hypotheses:
                ach = ACHResult(
                    hypothesis_text=hyp.label,
                    supporting_assertion_uids=hyp.supporting_assertion_uids,
                    confidence=hyp.confidence or 0.0,
                )
                adv, action, trace = await aevaluate_adversarial(
                    ach,
                    ctx.assertions,
                    ctx.source_claims,
                    case_uid=ctx.case_uid,
                    llm=ctx.llm,
                )
                results.append(
                    {
                        "hypothesis_uid": hyp.uid,
                        "adversarial": adv,
                        "action": action,
                        "trace": trace,
                    }
                )
            return results

        return await _safe(self.name, _run_all())


# ---------------------------------------------------------------------------
# 4. Narrative Build
# ---------------------------------------------------------------------------
class NarrativeBuildStage(AnalysisStage):
    name = "narrative_build"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.source_claims:
            return "no source claims"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services import narrative_builder

        embed_fn = ctx.llm.embed if ctx.llm else None
        sr = await _safe(
            self.name,
            narrative_builder.abuild_narratives_with_uids(
                ctx.source_claims,
                embed_fn=embed_fn,
                assertions=ctx.assertions,
            ),
        )
        if sr.status == "success" and sr.output:
            ctx.narratives = sr.output[0] if isinstance(sr.output, tuple) else sr.output
        return sr


# ---------------------------------------------------------------------------
# 5. KG Build
# ---------------------------------------------------------------------------
class KgBuildStage(AnalysisStage):
    name = "kg_build"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.assertions:
            return "no assertions"
        if ctx.neo4j is None:
            return "no Neo4j"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services.kg_mapper import build_kg_triples

        async def _write():
            triples = build_kg_triples(ctx.assertions, case_uid=ctx.case_uid)
            await ctx.neo4j.write_triples(triples, case_uid=ctx.case_uid)
            return triples

        return await _safe(self.name, _write())


# ---------------------------------------------------------------------------
# 6. Forecast Generate
# ---------------------------------------------------------------------------
class ForecastGenerateStage(AnalysisStage):
    name = "forecast_generate"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.hypotheses:
            return "no hypotheses"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services.scenario_generator import agenerate_forecasts

        sr = await _safe(
            self.name,
            agenerate_forecasts(
                hypotheses=ctx.hypotheses,
                assertions=ctx.assertions,
                narratives=ctx.narratives,
                case_uid=ctx.case_uid,
                llm=ctx.llm,
            ),
        )
        if sr.status == "success" and sr.output:
            ctx.forecasts = sr.output[0] if isinstance(sr.output, tuple) else sr.output
        return sr


# ---------------------------------------------------------------------------
# 7. Quality Score
# ---------------------------------------------------------------------------
class QualityScoreStage(AnalysisStage):
    name = "quality_score"

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services.confidence_scorer import QualityInput, score_confidence
        from aegi_core.services.scenario_generator import ForecastV1

        return _sync(
            self.name,
            lambda: score_confidence(
                QualityInput(
                    judgment_uid=f"pipeline-{uuid.uuid4().hex[:8]}",
                    case_uid=ctx.case_uid,
                    title="Pipeline quality assessment",
                    assertions=ctx.assertions,
                    hypotheses=ctx.hypotheses,
                    narratives=ctx.narratives,
                    source_claims=ctx.source_claims,
                    forecasts=[{"scenario_id": f.scenario_id} for f in ctx.forecasts]
                    if ctx.forecasts
                    else None,
                )
            ),
        )


# ---------------------------------------------------------------------------
# 8. Report Generate
# ---------------------------------------------------------------------------
class ReportGenerateStage(AnalysisStage):
    name = "report_generate"

    def should_skip(self, ctx: StageContext) -> str | None:
        if ctx.config.get("generate_report") is False:
            return "report explicitly disabled"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        report_type = ctx.config.get("report_type", "briefing")

        # ReportGenerator 需要 DB session — 没有 DB 时
        # 生成一个轻量级的内存报告，不做持久化
        async def _generate():
            from aegi_core.services.report_generator import (
                _load_context,
                _REPORT_SECTIONS,
                _REPORT_TITLES,
                _render_markdown,
            )

            # 用流水线状态构建上下文，而不是从 DB 读取
            class _PipelineCtx:
                def __init__(self):
                    self.case_uid = ctx.case_uid
                    self.assertions = ctx.assertions or []
                    self.hypotheses = ctx.hypotheses or []
                    self.source_claims = ctx.source_claims or []
                    self.narratives = ctx.narratives or []
                    self.judgments = []

            pipe_ctx = _PipelineCtx()
            section_fns = _REPORT_SECTIONS.get(report_type, [])
            sections = []
            for fn in section_fns:
                try:
                    sec = await fn(pipe_ctx, ctx.llm)
                    sections.append(sec)
                except Exception:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Report section %s failed",
                        fn.__name__,
                        exc_info=True,
                    )

            title = _REPORT_TITLES.get(report_type, "Report")
            rendered = _render_markdown(title, sections)
            return {
                "title": title,
                "sections_count": len(sections),
                "markdown_length": len(rendered),
            }

        return await _safe(self.name, _generate())
