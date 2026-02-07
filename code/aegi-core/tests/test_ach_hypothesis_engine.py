# Author: msq
"""ACH hypothesis engine tests.

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (4.1–4.3)
Evidence:
  - 验证支持/反证/缺口输出完整 (tasks.md 4.3)
  - defgeo-ach-001: 支持证据占优 (design.md: Fixtures)
  - defgeo-ach-002: 反证占优 (design.md: Fixtures)
  - defgeo-ach-003: 证据不足，必须输出 gap (design.md: Fixtures)
  - 无证据支持的结论必须调用 grounding_gate(False) 强制降级
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.services.hypothesis_adversarial import evaluate_adversarial
from aegi_core.services.hypothesis_engine import ACHResult, analyze_hypothesis

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "defense-geopolitics"


def _load_scenario(name: str) -> dict:
    return json.loads((FIXTURES / name / "scenario.json").read_text(encoding="utf-8"))


def _build_claims(raw: list[dict]) -> list[SourceClaimV1]:
    now = datetime.now(timezone.utc)
    return [
        SourceClaimV1(
            uid=sc["source_claim_uid"],
            case_uid="case_test",
            artifact_version_uid="av_test",
            chunk_uid="chunk_test",
            evidence_uid="ev_test",
            quote=sc["quote"],
            selectors=sc["selectors"],
            created_at=now,
        )
        for sc in raw
    ]


def _build_assertions(raw: list[dict]) -> list[AssertionV1]:
    now = datetime.now(timezone.utc)
    return [
        AssertionV1(
            uid=a["assertion_uid"],
            case_uid="case_test",
            kind=a.get("kind", "event"),
            value=a.get("value", {}),
            source_claim_uids=a.get("source_claim_uids", []),
            confidence=a.get("confidence"),
            created_at=now,
        )
        for a in raw
    ]


# ---------------------------------------------------------------------------
# defgeo-ach-001: 支持证据占优
# ---------------------------------------------------------------------------


class TestACH001SupportDominant:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-001")

    @pytest.fixture()
    def result(self, scenario: dict) -> ACHResult:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        return analyze_hypothesis(scenario["hypothesis"], assertions, claims)

    def test_supporting_count(self, result: ACHResult, scenario: dict) -> None:
        expected = scenario["expected"]
        assert len(result.supporting_assertion_uids) >= expected["supporting_count_gte"]

    def test_no_contradicting(self, result: ACHResult, scenario: dict) -> None:
        assert (
            len(result.contradicting_assertion_uids)
            == scenario["expected"]["contradicting_count"]
        )

    def test_no_gaps(self, result: ACHResult) -> None:
        assert len(result.gap_list) == 0

    def test_coverage(self, result: ACHResult, scenario: dict) -> None:
        assert result.coverage_score >= scenario["expected"]["coverage_score_gte"]

    def test_confidence(self, result: ACHResult, scenario: dict) -> None:
        assert result.confidence >= scenario["expected"]["confidence_gte"]

    def test_output_completeness(self, result: ACHResult) -> None:
        """每个假设 MUST 包含支持/反证/缺口三类输出。"""
        assert result.supporting_assertion_uids is not None
        assert result.contradicting_assertion_uids is not None
        assert result.gap_list is not None
        assert result.coverage_score is not None
        assert result.confidence is not None

    def test_adversarial_preserves_disagreement(
        self, result: ACHResult, scenario: dict
    ) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, action, trace = evaluate_adversarial(
            result, assertions, claims, case_uid="case_test"
        )
        assert adv.defense.role == "defense"
        assert adv.prosecution.role == "prosecution"
        assert adv.judge.role == "judge"
        assert action.trace_id is not None
        assert trace.trace_id is not None


# ---------------------------------------------------------------------------
# defgeo-ach-002: 反证占优
# ---------------------------------------------------------------------------


class TestACH002ContradictionDominant:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-002")

    @pytest.fixture()
    def result(self, scenario: dict) -> ACHResult:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        return analyze_hypothesis(scenario["hypothesis"], assertions, claims)

    def test_has_contradicting(self, result: ACHResult, scenario: dict) -> None:
        assert (
            len(result.contradicting_assertion_uids)
            >= scenario["expected"]["contradicting_count_gte"]
        )

    def test_coverage(self, result: ACHResult, scenario: dict) -> None:
        assert result.coverage_score >= scenario["expected"]["coverage_score_gte"]

    def test_low_confidence(self, result: ACHResult, scenario: dict) -> None:
        assert result.confidence <= scenario["expected"]["confidence_lte"]

    def test_output_completeness(self, result: ACHResult) -> None:
        assert result.supporting_assertion_uids is not None
        assert result.contradicting_assertion_uids is not None
        assert result.gap_list is not None

    def test_adversarial_conflict_preserved(
        self, result: ACHResult, scenario: dict
    ) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, _, _ = evaluate_adversarial(
            result, assertions, claims, case_uid="case_test"
        )
        # 反证占优时 prosecution 必须有内容
        assert len(adv.prosecution.assertion_uids) > 0
        # judge 必须包含裁决依据
        assert adv.judge.rationale != ""


# ---------------------------------------------------------------------------
# defgeo-ach-003: 证据不足（必须输出 gap）
# ---------------------------------------------------------------------------


class TestACH003InsufficientEvidence:
    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-003")

    @pytest.fixture()
    def result(self, scenario: dict) -> ACHResult:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        return analyze_hypothesis(scenario["hypothesis"], assertions, claims)

    def test_has_gaps(self, result: ACHResult, scenario: dict) -> None:
        assert len(result.gap_list) >= scenario["expected"]["gap_count_gte"]

    def test_low_coverage(self, result: ACHResult, scenario: dict) -> None:
        assert result.coverage_score <= scenario["expected"]["coverage_score_lte"]

    def test_grounding_forced_degraded(self, result: ACHResult, scenario: dict) -> None:
        """无证据支持的结论 MUST 调用 grounding_gate(False) 强制降级。"""
        expected_level = GroundingLevel(scenario["expected"]["grounding_level"])
        assert result.grounding_level == expected_level

    def test_output_completeness(self, result: ACHResult) -> None:
        assert result.supporting_assertion_uids is not None
        assert result.contradicting_assertion_uids is not None
        assert result.gap_list is not None

    def test_adversarial_gaps_explicit(self, result: ACHResult, scenario: dict) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, _, _ = evaluate_adversarial(
            result, assertions, claims, case_uid="case_test"
        )
        # judge 必须显式列出证据缺口
        assert len(adv.judge.gaps) > 0


# ---------------------------------------------------------------------------
# grounding_gate 合同验证
# ---------------------------------------------------------------------------


class TestGroundingGateContract:
    def test_with_evidence_returns_fact(self) -> None:
        assert grounding_gate(True) == GroundingLevel.FACT

    def test_without_evidence_returns_hypothesis(self) -> None:
        assert grounding_gate(False) == GroundingLevel.HYPOTHESIS

    def test_no_evidence_never_fact(self) -> None:
        """无证据支持的结论不得输出 FACT。"""
        level = grounding_gate(False)
        assert level != GroundingLevel.FACT


# ---------------------------------------------------------------------------
# 审计追踪验证
# ---------------------------------------------------------------------------


class TestAuditTraceability:
    def test_adversarial_records_trace_id(self) -> None:
        scenario = _load_scenario("defgeo-ach-001")
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        ach = analyze_hypothesis(scenario["hypothesis"], assertions, claims)
        _, action, trace = evaluate_adversarial(
            ach, assertions, claims, case_uid="case_test", trace_id="trace_abc"
        )
        assert action.trace_id == "trace_abc"
        assert trace.trace_id == "trace_abc"

    def test_adversarial_records_prompt_version(self) -> None:
        scenario = _load_scenario("defgeo-ach-001")
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        ach = analyze_hypothesis(scenario["hypothesis"], assertions, claims)
        _, _, trace = evaluate_adversarial(
            ach, assertions, claims, case_uid="case_test"
        )
        assert "prompt_version" in trace.policy
