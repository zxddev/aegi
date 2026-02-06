# Author: msq
"""Tests for end-to-end pipeline orchestration.

Source: openspec/changes/end-to-end-pipeline-orchestration/tasks.md (4.1–4.5)
Evidence:
  - 全链路测试用 defgeo-claim-001 fixture 驱动。
  - 增量 pipeline 测试用 defgeo-ach-001 从 hypothesis 阶段开始。
  - 降级路径测试用 defgeo-forecast-003 验证 skip 而非 crash。
  - API 桩测试验证路由注册与响应结构。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    Modality,
    SourceClaimV1,
)
from aegi_core.services.pipeline_orchestrator import (
    STAGE_ORDER,
    PipelineOrchestrator,
    PipelineResult,
    StageResult,
)

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"
CASE_UID = "case_pipeline_test"


# -- helpers -------------------------------------------------------------------


def _make_claim(
    uid: str,
    quote: str,
    *,
    attributed_to: str | None = None,
    case_uid: str = CASE_UID,
) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid=case_uid,
        artifact_version_uid="av_test",
        chunk_uid="chunk_test",
        evidence_uid="ev_test",
        quote=quote,
        selectors=[{"type": "TextQuoteSelector", "exact": quote}],
        attributed_to=attributed_to,
        modality=Modality.TEXT,
        created_at=datetime.now(timezone.utc),
    )


def _make_assertion(
    uid: str,
    source_claim_uids: list[str],
    *,
    kind: str = "fused_claim",
    confidence: float = 0.9,
    case_uid: str = CASE_UID,
) -> AssertionV1:
    return AssertionV1(
        uid=uid,
        case_uid=case_uid,
        kind=kind,
        value={"attributed_to": "TestEntity", "rationale": "test confirmed"},
        source_claim_uids=source_claim_uids,
        confidence=confidence,
        created_at=datetime.now(timezone.utc),
    )


def _make_hypothesis(
    uid: str,
    label: str,
    supporting: list[str],
    *,
    confidence: float = 0.8,
    case_uid: str = CASE_UID,
) -> HypothesisV1:
    return HypothesisV1(
        uid=uid,
        case_uid=case_uid,
        label=label,
        supporting_assertion_uids=supporting,
        confidence=confidence,
        created_at=datetime.now(timezone.utc),
    )


def _load_claims_from_fixture(fixture_name: str) -> list[SourceClaimV1]:
    """从 fixture 加载 source claims。"""
    sc_data = json.loads((FIXTURES / fixture_name / "source_claims.json").read_text())
    return [
        _make_claim(
            uid=sc["source_claim_uid"],
            quote=sc["quote"],
            attributed_to=sc.get("attributed_to"),
        )
        for sc in sc_data["source_claims"]
    ]


# -- Task 4.2: 全链路测试 (defgeo-claim-001) -----------------------------------


class TestFullPipeline:
    """全链路 pipeline 测试。"""

    def test_full_pipeline_from_claims(self) -> None:
        """defgeo-claim-001: source_claims → 全阶段执行，无 crash。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        result = orch.run_full(case_uid=CASE_UID, source_claims=claims)

        assert isinstance(result, PipelineResult)
        assert result.case_uid == CASE_UID
        assert len(result.stages) == len(STAGE_ORDER)
        assert result.total_duration_ms >= 0

        for sr in result.stages:
            assert sr.status in {"success", "skipped", "degraded", "error"}
            assert sr.duration_ms >= 0

    def test_full_pipeline_stage_names(self) -> None:
        """全链路执行的阶段名称与顺序一致。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        result = orch.run_full(case_uid=CASE_UID, source_claims=claims)

        stage_names = [s.stage for s in result.stages]
        assert stage_names == STAGE_ORDER

    def test_assertion_fuse_produces_output(self) -> None:
        """assertion_fuse 阶段应产出 assertions。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        result = orch.run_full(case_uid=CASE_UID, source_claims=claims)

        fuse_stage = result.stages[0]
        assert fuse_stage.stage == "assertion_fuse"
        assert fuse_stage.status == "success"
        # output 是 (assertions, conflict_set, action, trace) 或 assertions list
        assert fuse_stage.output is not None


# -- Task 4.2: 增量 pipeline (defgeo-ach-001) ----------------------------------


class TestIncrementalPipeline:
    """增量 pipeline 测试：从任意阶段开始。"""

    def test_start_from_hypothesis(self) -> None:
        """defgeo-ach-001: 已有 assertions，从 hypothesis_analyze 开始。"""
        scenario = json.loads(
            (FIXTURES / "defgeo-ach-001" / "scenario.json").read_text()
        )
        claims = [
            _make_claim(uid=sc["source_claim_uid"], quote=sc["quote"])
            for sc in scenario["source_claims"]
        ]
        assertions = [
            _make_assertion(
                uid=a["assertion_uid"],
                source_claim_uids=a["source_claim_uids"],
                kind=a["kind"],
                confidence=a["confidence"],
            )
            for a in scenario["assertions"]
        ]

        orch = PipelineOrchestrator()
        result = orch.run_full(
            case_uid=CASE_UID,
            source_claims=claims,
            assertions=assertions,
            start_from="hypothesis_analyze",
        )

        stage_names = [s.stage for s in result.stages]
        assert "assertion_fuse" not in stage_names
        assert "hypothesis_analyze" in stage_names
        assert result.stages[0].stage == "hypothesis_analyze"

    def test_run_specific_stages(self) -> None:
        """只执行指定阶段子集。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        result = orch.run_full(
            case_uid=CASE_UID,
            source_claims=claims,
            stages=["assertion_fuse", "quality_score"],
        )

        stage_names = [s.stage for s in result.stages]
        assert stage_names == ["assertion_fuse", "quality_score"]

    def test_run_single_stage(self) -> None:
        """run_stage 执行单阶段。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        sr = orch.run_stage("assertion_fuse", {
            "case_uid": CASE_UID,
            "source_claims": claims,
        })

        assert isinstance(sr, StageResult)
        assert sr.stage == "assertion_fuse"
        assert sr.status in {"success", "skipped"}


# -- Task 4.3: 降级路径 (defgeo-forecast-003) ----------------------------------


class TestDegradationPaths:
    """降级路径测试：缺失输入 → skip 而非 crash。"""

    def test_empty_claims_skips_all(self) -> None:
        """空 source_claims → 所有阶段 skip，不 crash。"""
        orch = PipelineOrchestrator()
        result = orch.run_full(case_uid=CASE_UID, source_claims=[])

        assert isinstance(result, PipelineResult)
        for sr in result.stages:
            assert sr.status in {"success", "skipped"}, (
                f"Stage {sr.stage} should skip/succeed, got {sr.status}: {sr.error}"
            )

    def test_degraded_forecast_scenario(self) -> None:
        """defgeo-forecast-003: 弱证据 → forecast 降级，不 crash。"""
        scenario = json.loads(
            (FIXTURES / "defgeo-forecast-003" / "scenario.json").read_text()
        )
        claims = [
            _make_claim(uid=sc["source_claim_uid"], quote=sc["quote"])
            for sc in scenario["source_claims"]
        ]
        assertions = [
            _make_assertion(
                uid=a["assertion_uid"],
                source_claim_uids=a["source_claim_uids"],
                kind=a["kind"],
                confidence=a.get("confidence", 0.2),
            )
            for a in scenario["assertions"]
        ]
        hypotheses = [
            _make_hypothesis(
                uid=h["hypothesis_uid"],
                label=h["label"],
                supporting=h["supporting_assertion_uids"],
                confidence=h.get("confidence", 0.15),
            )
            for h in scenario["hypotheses"]
        ]

        orch = PipelineOrchestrator()
        result = orch.run_full(
            case_uid=CASE_UID,
            source_claims=claims,
            assertions=assertions,
            hypotheses=hypotheses,
        )

        for sr in result.stages:
            assert sr.status != "error", (
                f"Stage {sr.stage} errored: {sr.error}"
            )

    def test_missing_hypotheses_skips_forecast(self) -> None:
        """无 hypotheses → forecast_generate 阶段 skip。"""
        claims = _load_claims_from_fixture("defgeo-claim-001")
        orch = PipelineOrchestrator()
        # 提供 assertions 但无 hypotheses，且 hypothesis_analyze 可能产出空
        result = orch.run_full(
            case_uid=CASE_UID,
            source_claims=claims,
            hypotheses=[],
            stages=["forecast_generate"],
        )

        assert result.stages[0].stage == "forecast_generate"
        assert result.stages[0].status == "skipped"


# -- Task 3.1–3.2: API 桩测试 -------------------------------------------------


class TestOrchestrationAPI:
    """API 路由桩测试。"""

    @pytest.mark.asyncio
    async def test_full_analysis_stub(self) -> None:
        """POST /cases/{case_uid}/pipelines/full_analysis 返回正确结构。"""
        from aegi_core.api.routes.orchestration import router

        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/cases/case_001/pipelines/full_analysis",
                json={"source_claim_uids": []},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_uid"] == "case_001"
        assert "stages" in data

    @pytest.mark.asyncio
    async def test_run_stage_stub(self) -> None:
        """POST /cases/{case_uid}/pipelines/run_stage 返回正确结构。"""
        from aegi_core.api.routes.orchestration import router

        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/cases/case_001/pipelines/run_stage",
                json={"stage_name": "assertion_fuse", "inputs": {}},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["stage"] == "assertion_fuse"
        assert data["status"] == "skipped"
