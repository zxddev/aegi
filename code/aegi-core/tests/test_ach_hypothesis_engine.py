# Author: msq
"""ACH hypothesis engine tests — adversarial + grounding_gate + audit.

旧规则引擎 analyze_hypothesis 已删除，ACH 分析改用 LLM（analyze_hypothesis_llm）。
本文件保留不依赖 LLM 的 adversarial 评估、grounding_gate 合同、审计追踪测试。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.services.hypothesis_adversarial import evaluate_adversarial
from aegi_core.services.hypothesis_engine import ACHResult

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
# Adversarial 评估（支持占优场景）
# ---------------------------------------------------------------------------


class TestAdversarialSupportDominant:
    """defgeo-ach-001 fixture + 手工构造 ACHResult → adversarial 评估。"""

    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-001")

    @pytest.fixture()
    def ach(self, scenario: dict) -> ACHResult:
        uids = [a["assertion_uid"] for a in scenario["assertions"]]
        return ACHResult(
            hypothesis_text=scenario["hypothesis"],
            supporting_assertion_uids=uids,
            contradicting_assertion_uids=[],
            coverage_score=1.0,
            confidence=1.0,
            gap_list=[],
            grounding_level=GroundingLevel.FACT,
        )

    def test_adversarial_roles(self, ach: ACHResult, scenario: dict) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, action, trace = evaluate_adversarial(
            ach, assertions, claims, case_uid="case_test"
        )
        assert adv.defense.role == "defense"
        assert adv.prosecution.role == "prosecution"
        assert adv.judge.role == "judge"
        assert action.trace_id is not None
        assert trace.trace_id is not None


# ---------------------------------------------------------------------------
# Adversarial 评估（反证占优场景）
# ---------------------------------------------------------------------------


class TestAdversarialContradictionDominant:
    """defgeo-ach-002 fixture + 手工构造 ACHResult → adversarial 评估。"""

    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-002")

    @pytest.fixture()
    def ach(self, scenario: dict) -> ACHResult:
        uids = [a["assertion_uid"] for a in scenario["assertions"]]
        return ACHResult(
            hypothesis_text=scenario["hypothesis"],
            supporting_assertion_uids=[],
            contradicting_assertion_uids=uids,
            coverage_score=1.0,
            confidence=0.0,
            gap_list=[],
            grounding_level=GroundingLevel.HYPOTHESIS,
        )

    def test_prosecution_has_content(self, ach: ACHResult, scenario: dict) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, _, _ = evaluate_adversarial(ach, assertions, claims, case_uid="case_test")
        assert len(adv.prosecution.assertion_uids) > 0
        assert adv.judge.rationale != ""


# ---------------------------------------------------------------------------
# Adversarial 评估（证据不足场景）
# ---------------------------------------------------------------------------


class TestAdversarialInsufficientEvidence:
    """defgeo-ach-003 fixture + 手工构造 ACHResult → adversarial 评估。"""

    @pytest.fixture()
    def scenario(self) -> dict:
        return _load_scenario("defgeo-ach-003")

    @pytest.fixture()
    def ach(self, scenario: dict) -> ACHResult:
        return ACHResult(
            hypothesis_text=scenario["hypothesis"],
            supporting_assertion_uids=[],
            contradicting_assertion_uids=[],
            coverage_score=0.0,
            confidence=0.0,
            gap_list=["assertion as_ach_003_0001 not evaluated"],
            grounding_level=GroundingLevel.HYPOTHESIS,
        )

    def test_judge_lists_gaps(self, ach: ACHResult, scenario: dict) -> None:
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        adv, _, _ = evaluate_adversarial(ach, assertions, claims, case_uid="case_test")
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
        uids = [a["assertion_uid"] for a in scenario["assertions"]]
        ach = ACHResult(
            hypothesis_text=scenario["hypothesis"],
            supporting_assertion_uids=uids,
            coverage_score=1.0,
            confidence=1.0,
            grounding_level=GroundingLevel.FACT,
        )
        _, action, trace = evaluate_adversarial(
            ach, assertions, claims, case_uid="case_test", trace_id="trace_abc"
        )
        assert action.trace_id == "trace_abc"
        assert trace.trace_id == "trace_abc"

    def test_adversarial_records_prompt_version(self) -> None:
        scenario = _load_scenario("defgeo-ach-001")
        claims = _build_claims(scenario["source_claims"])
        assertions = _build_assertions(scenario["assertions"])
        uids = [a["assertion_uid"] for a in scenario["assertions"]]
        ach = ACHResult(
            hypothesis_text=scenario["hypothesis"],
            supporting_assertion_uids=uids,
            coverage_score=1.0,
            confidence=1.0,
            grounding_level=GroundingLevel.FACT,
        )
        _, _, trace = evaluate_adversarial(
            ach, assertions, claims, case_uid="case_test"
        )
        assert "prompt_version" in trace.policy
