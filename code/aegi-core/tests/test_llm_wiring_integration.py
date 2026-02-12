# Author: msq
"""Phase 1+2 LLM 接通集成测试。

验证所有 async LLM 方法在真实 OSS 120B 下的端到端行为。
需要 LiteLLM Proxy + vLLM + embedding 服务在线。
"""

from __future__ import annotations

from datetime import datetime, timezone


from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    Modality,
    SourceClaimV1,
)
from aegi_core.infra.llm_client import LLMClient
from aegi_core.settings import settings
from conftest import requires_llm

# ── 测试数据 ──────────────────────────────────────────────────────


def _llm() -> LLMClient:
    import json

    extra: dict[str, str] | None = None
    if settings.litellm_extra_headers:
        extra = json.loads(settings.litellm_extra_headers)
    return LLMClient(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        default_model=settings.litellm_default_model,
        extra_headers=extra,
    )


def _claims() -> list[SourceClaimV1]:
    base = datetime(2026, 1, 15, tzinfo=timezone.utc)
    return [
        SourceClaimV1(
            uid="sc1",
            case_uid="test",
            artifact_version_uid="av1",
            chunk_uid="c1",
            evidence_uid="e1",
            quote="Russia deployed 100000 troops near Ukraine border",
            selectors=[],
            attributed_to="satellite_imagery",
            modality=Modality.TEXT,
            created_at=base,
        ),
        SourceClaimV1(
            uid="sc2",
            case_uid="test",
            artifact_version_uid="av1",
            chunk_uid="c2",
            evidence_uid="e1",
            quote="Moscow sent additional military forces to Ukrainian border",
            selectors=[],
            attributed_to="military_analyst",
            modality=Modality.TEXT,
            created_at=base,
        ),
        SourceClaimV1(
            uid="sc3",
            case_uid="test",
            artifact_version_uid="av1",
            chunk_uid="c3",
            evidence_uid="e2",
            quote="NATO deployed forces to Eastern European member states",
            selectors=[],
            attributed_to="nato_spokesperson",
            modality=Modality.TEXT,
            created_at=base,
        ),
        SourceClaimV1(
            uid="sc4",
            case_uid="test",
            artifact_version_uid="av1",
            chunk_uid="c4",
            evidence_uid="e3",
            quote="EU sanctions reduced Russian oil revenues by 30 percent",
            selectors=[],
            attributed_to="eu_commission",
            modality=Modality.TEXT,
            created_at=base,
        ),
    ]


def _assertions() -> list[AssertionV1]:
    from aegi_core.services.assertion_fuser import fuse_claims

    return fuse_claims(_claims(), case_uid="test")[0]


def _hypothesis(assertions: list[AssertionV1]) -> HypothesisV1:
    return HypothesisV1(
        uid="h1",
        case_uid="test",
        label="Russia is preparing a military offensive against Ukraine",
        supporting_assertion_uids=[a.uid for a in assertions[:2]],
        confidence=0.7,
        created_at=datetime.now(timezone.utc),
    )


# ── 测试 ──────────────────────────────────────────────────────────


@requires_llm
class TestLLMQueryPlanner:
    """aplan_query LLM 路径。"""

    async def test_aplan_query_returns_plan(self) -> None:
        from aegi_core.services.query_planner import aplan_query

        plan = await aplan_query("俄乌冲突中北约的角色？", "test", llm=_llm())
        assert len(plan.retrieval_steps) >= 1
        assert plan.case_uid == "test"

    async def test_aplan_query_fallback_without_llm(self) -> None:
        """无 LLM 时 fallback 到规则版本。"""
        from aegi_core.services.query_planner import aplan_query

        plan = await aplan_query("test question", "test", llm=None)
        assert len(plan.retrieval_steps) == 2  # 规则版本固定 2 步


@requires_llm
class TestLLMNarrativeEmbedding:
    """abuild_narratives_with_uids embedding 路径。"""

    async def test_embedding_clusters_semantic_similar(self) -> None:
        """语义相近的 claims 应被聚到同一 narrative。"""
        from aegi_core.services.narrative_builder import abuild_narratives_with_uids

        narratives, uid_map = await abuild_narratives_with_uids(
            _claims(),
            embed_fn=_llm().embed,
        )
        # 4 条 claims 中 sc1/sc2 语义相同应聚类，sc3/sc4 各自独立
        assert 1 <= len(narratives) <= 3
        total_mapped = sum(len(v) for v in uid_map.values())
        assert total_mapped == 4


@requires_llm
class TestLLMForecast:
    """agenerate_forecasts LLM 路径。"""

    async def test_llm_generates_multiple_scenarios(self) -> None:
        assertions = _assertions()
        hyp = _hypothesis(assertions)

        from aegi_core.services.scenario_generator import agenerate_forecasts

        forecasts, action, trace = await agenerate_forecasts(
            hypotheses=[hyp],
            assertions=assertions,
            case_uid="test",
            llm=_llm(),
        )
        # LLM 应生成多个情景（规则版只生成 1 个）
        assert len(forecasts) >= 2
        for f in forecasts:
            assert f.scenario_id
            assert f.status in {"draft", "active", "expired"}


@requires_llm
class TestLLMAdversarial:
    """aevaluate_adversarial LLM 路径。"""

    async def test_adversarial_produces_three_roles(self) -> None:
        assertions = _assertions()
        claims = _claims()

        from aegi_core.services.hypothesis_adversarial import aevaluate_adversarial
        from aegi_core.services.hypothesis_engine import ACHResult

        ach = ACHResult(
            hypothesis_text="Russia is preparing a military offensive",
            supporting_assertion_uids=[a.uid for a in assertions[:2]],
            confidence=0.7,
        )
        adv, action, trace = await aevaluate_adversarial(
            ach,
            assertions,
            claims,
            case_uid="test",
            llm=_llm(),
        )
        # 三个角色都应有输出
        assert adv.defense.role == "defense"
        assert adv.prosecution.role == "prosecution"
        assert adv.judge.role == "judge"
        # LLM 路径应产生非空 rationale
        assert adv.defense.rationale or adv.defense.assertion_uids
        assert adv.judge.rationale or adv.judge.assertion_uids


@requires_llm
class TestOrchestratorAsync:
    """PipelineOrchestrator.run_full_async LLM 路径。"""

    async def test_async_pipeline_has_adversarial_stage(self) -> None:
        from aegi_core.services.pipeline_orchestrator import PipelineOrchestrator

        orch = PipelineOrchestrator(llm=_llm())
        result = await orch.run_full_async(
            case_uid="test",
            source_claims=_claims(),
        )
        stage_names = [s.stage for s in result.stages]
        assert "adversarial_evaluate" in stage_names

    async def test_async_pipeline_all_stages_no_crash(self) -> None:
        from aegi_core.services.pipeline_orchestrator import (
            STAGE_ORDER,
            PipelineOrchestrator,
        )

        orch = PipelineOrchestrator(llm=_llm())
        result = await orch.run_full_async(
            case_uid="test",
            source_claims=_claims(),
        )
        assert len(result.stages) == len(STAGE_ORDER)
        for sr in result.stages:
            assert sr.status != "error", f"{sr.stage} errored: {sr.error}"
