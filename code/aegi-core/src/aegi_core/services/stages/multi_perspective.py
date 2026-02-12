"""多视角假设生成阶段（STORM 启发）。

用多角色分析替代单一视角的假设生成。
作为可插拔 stage 与内置 hypothesis_analyze 并列注册。
"""

from __future__ import annotations

from aegi_core.services.pipeline_orchestrator import StageResult
from aegi_core.services.stages.base import AnalysisStage, StageContext
from aegi_core.services.stages.builtin import _ms, _skip


class MultiPerspectiveHypothesisStage(AnalysisStage):
    """从多个分析师角色生成假设。"""

    name = "hypothesis_multi_perspective"

    def should_skip(self, ctx: StageContext) -> str | None:
        if not ctx.assertions:
            return "no assertions"
        if ctx.llm is None:
            return "no LLM"
        return None

    async def run(self, ctx: StageContext) -> StageResult:
        from aegi_core.services.persona_generator import (
            generate_hypotheses_multi_perspective,
        )
        from aegi_core.services import hypothesis_engine

        t = _ms()
        try:
            persona_count = ctx.config.get("persona_count", 3)
            raw = await generate_hypotheses_multi_perspective(
                ctx.assertions,
                ctx.source_claims,
                case_uid=ctx.case_uid,
                llm=ctx.llm,
                persona_count=persona_count,
            )

            # 对每个假设执行 ACH 分析
            from aegi_core.services.pipeline_orchestrator import _ach_to_hypothesis

            hypotheses = []
            for item in raw:
                ach = await hypothesis_engine.analyze_hypothesis_llm(
                    item["hypothesis_text"],
                    ctx.assertions,
                    llm=ctx.llm,
                )
                h = _ach_to_hypothesis(ach, ctx.case_uid)
                # 附加角色元数据
                h.metadata = h.metadata or {}
                h.metadata["persona"] = item["persona"]
                h.metadata["perspective"] = item["perspective"]
                hypotheses.append(h)

            ctx.hypotheses = hypotheses
            return StageResult(
                stage=self.name,
                status="success",
                duration_ms=_ms() - t,
                output=hypotheses,
            )
        except Exception as exc:
            return StageResult(
                stage=self.name,
                status="error",
                duration_ms=_ms() - t,
                output=None,
                error=str(exc),
            )
