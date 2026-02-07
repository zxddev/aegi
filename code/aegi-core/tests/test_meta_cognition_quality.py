# Author: msq
"""Tests for meta-cognition quality scoring.

Source: openspec/changes/meta-cognition-quality-scoring/tasks.md (4.1–4.3)
Evidence:
  - confidence_breakdown 包含来源/覆盖/一致性/时效四维分解。
  - bias flag 引用具体 source_claim_uids。
  - 上游依赖缺失 → pending_inputs / partial，不产出伪完整评分。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aegi_core.contracts.schemas import (
    AssertionV1,
    HypothesisV1,
    NarrativeV1,
    SourceClaimV1,
)
from aegi_core.services.bias_detector import detect_biases
from aegi_core.services.blindspot_detector import detect_blindspots
from aegi_core.services.confidence_scorer import (
    QualityInput,
    QualityReportV1,
    score_confidence,
)

FIXTURES = Path(__file__).parent / "fixtures" / "defense-geopolitics"


def _load_scenario(fixture_dir: str) -> dict:
    path = FIXTURES / fixture_dir / "scenario.json"
    return json.loads(path.read_text())


def _build_input(scenario: dict) -> QualityInput:
    """从 fixture scenario 构建 QualityInput。"""
    j = scenario["judgment"]

    source_claims = [
        SourceClaimV1(
            uid=sc["uid"],
            case_uid=sc["case_uid"],
            artifact_version_uid=sc.get("artifact_version_uid", "av-000"),
            chunk_uid=sc.get("chunk_uid", "ch-000"),
            evidence_uid=sc.get("evidence_uid", "ev-000"),
            quote=sc["quote"],
            attributed_to=sc.get("attributed_to"),
            language=sc.get("language", "en"),
            created_at=datetime.fromisoformat(sc["created_at"]),
        )
        for sc in scenario.get("source_claims", [])
    ]
    assertions = [
        AssertionV1(
            uid=a["uid"],
            case_uid=a["case_uid"],
            kind=a["kind"],
            value=a.get("value", {}),
            source_claim_uids=a.get("source_claim_uids", []),
            confidence=a.get("confidence"),
            created_at=datetime.fromisoformat(a["created_at"]),
        )
        for a in scenario.get("assertions", [])
    ]
    hypotheses = [
        HypothesisV1(
            uid=h["uid"],
            case_uid=h["case_uid"],
            label=h["label"],
            supporting_assertion_uids=h.get("supporting_assertion_uids", []),
            confidence=h.get("confidence"),
            created_at=datetime.fromisoformat(h["created_at"]),
        )
        for h in scenario.get("hypotheses", [])
    ]
    narratives = [
        NarrativeV1(
            uid=n["uid"],
            case_uid=n["case_uid"],
            title=n["title"],
            assertion_uids=n.get("assertion_uids", []),
            hypothesis_uids=n.get("hypothesis_uids", []),
            created_at=datetime.fromisoformat(n["created_at"]),
        )
        for n in scenario.get("narratives", [])
    ]
    forecasts = scenario.get("forecasts")

    return QualityInput(
        judgment_uid=j["uid"],
        case_uid=j["case_uid"],
        title=j["title"],
        assertion_uids=j.get("assertion_uids", []),
        assertions=assertions,
        hypotheses=hypotheses,
        narratives=narratives,
        source_claims=source_claims,
        forecasts=forecasts,
    )


# ---------------------------------------------------------------------------
# Fixture 001: complete input, normal scoring
# ---------------------------------------------------------------------------


class TestQuality001NormalScoring:
    """defgeo-quality-001: 多独立来源，完整评分。"""

    def test_status_complete(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        assert report.status == "complete"

    def test_confidence_score_above_threshold(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        expected = scenario["expected"]
        assert report.confidence_score >= expected["confidence_score_gte"]

    def test_four_dimension_breakdown(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        dim_names = {d.name for d in report.confidence_breakdown}
        assert dim_names == {
            "evidence_strength",
            "coverage",
            "consistency",
            "freshness",
        }

    def test_bias_flags_count_matches(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        assert len(report.bias_flags) == scenario["expected"]["bias_flag_count"]

    def test_no_blindspots(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        assert len(report.blindspot_items) == scenario["expected"]["blindspot_count"]

    def test_evidence_diversity(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        assert (
            report.evidence_diversity >= scenario["expected"]["evidence_diversity_gte"]
        )

    def test_trace_id_present(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        assert report.trace_id.startswith("trace-quality-")


# ---------------------------------------------------------------------------
# Fixture 002: bias examples
# ---------------------------------------------------------------------------


class TestQuality002BiasDetection:
    """defgeo-quality-002: 单源依赖 + 确认偏误。"""

    def test_status_complete(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        report = score_confidence(_build_input(scenario))
        assert report.status == "complete"

    def test_bias_flags_detected(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        report = score_confidence(_build_input(scenario))
        expected = scenario["expected"]
        assert len(report.bias_flags) >= expected["bias_flag_count_gte"]

    def test_single_source_bias_present(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        report = score_confidence(_build_input(scenario))
        kinds = {f.kind for f in report.bias_flags}
        assert "single_source_dependency" in kinds

    def test_bias_flags_have_source_claim_uids(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        report = score_confidence(_build_input(scenario))
        for flag in report.bias_flags:
            assert len(flag.source_claim_uids) >= 1, (
                f"Bias flag {flag.kind} missing source_claim_uids"
            )

    def test_single_stance_bias_detected(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        report = score_confidence(_build_input(scenario))
        kinds = {f.kind for f in report.bias_flags}
        assert "single_stance_bias" in kinds

    def test_bias_detector_standalone(self) -> None:
        scenario = _load_scenario("defgeo-quality-002")
        inp = _build_input(scenario)
        flags = detect_biases(inp.assertions, inp.source_claims, inp.hypotheses)
        assert len(flags) >= 1
        for f in flags:
            assert f.source_claim_uids


# ---------------------------------------------------------------------------
# Fixture 003: blindspot + upstream missing → partial
# ---------------------------------------------------------------------------


class TestQuality003PendingInputs:
    """defgeo-quality-003: forecast 缺失 → partial，盲区检测。"""

    def test_status_partial(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        assert report.status == "partial"

    def test_consistency_dimension_pending(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        consistency = next(
            d for d in report.confidence_breakdown if d.name == "consistency"
        )
        assert consistency.status == "pending"

    def test_blindspots_detected(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        expected = scenario["expected"]
        assert len(report.blindspot_items) >= expected["blindspot_count_gte"]

    def test_upstream_blindspot_present(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        dims = {b.dimension for b in report.blindspot_items}
        assert "upstream_dependency" in dims

    def test_blindspot_detector_standalone(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        inp = _build_input(scenario)
        items = detect_blindspots(
            inp.assertions,
            inp.hypotheses,
            inp.source_claims,
            inp.forecasts,
        )
        assert any(i.dimension == "upstream_dependency" for i in items)

    def test_no_pseudo_complete_score(self) -> None:
        """pending 维度不参与最终 confidence_score 计算。"""
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        assert report.status != "complete"
        complete_dims = [
            d for d in report.confidence_breakdown if d.status == "complete"
        ]
        if complete_dims:
            expected_avg = sum(d.score for d in complete_dims) / len(complete_dims)
            assert abs(report.confidence_score - round(expected_avg, 4)) < 0.001


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestQualityEdgeCases:
    def test_empty_input_returns_pending_inputs(self) -> None:
        inp = QualityInput(
            judgment_uid="jdg-empty",
            case_uid="case-empty",
            title="Empty",
        )
        report = score_confidence(inp)
        assert report.status == "pending_inputs"

    def test_report_is_pydantic_serializable(self) -> None:
        scenario = _load_scenario("defgeo-quality-001")
        report = score_confidence(_build_input(scenario))
        data = report.model_dump()
        assert "confidence_breakdown" in data
        assert "bias_flags" in data
        roundtrip = QualityReportV1.model_validate(data)
        assert roundtrip.judgment_uid == report.judgment_uid

    def test_all_dimensions_present_even_when_partial(self) -> None:
        scenario = _load_scenario("defgeo-quality-003")
        report = score_confidence(_build_input(scenario))
        dim_names = {d.name for d in report.confidence_breakdown}
        assert dim_names == {
            "evidence_strength",
            "coverage",
            "consistency",
            "freshness",
        }
