"""Critic/Judge 测试。"""

from __future__ import annotations

from datetime import datetime

from baize_core.agents.critic import CriticAgent
from baize_core.agents.judge import JudgeAgent
from baize_core.schemas.critique import ConflictSeverity, GapType
from baize_core.schemas.evidence import Claim, Evidence
from baize_core.schemas.ooda import Hypothesis


def make_evidence(
    uid: str,
    source: str,
    credibility: float,
    summary: str = "",
) -> Evidence:
    """创建测试证据。"""
    return Evidence(
        evidence_uid=uid,
        chunk_uid=f"chk_{uid}",
        source=source,
        collected_at=datetime.now(),
        base_credibility=credibility,
        summary=summary,
    )


class TestCriticAgent:
    """CriticAgent 测试。"""

    def test_来源不足识别缺口(self) -> None:
        """来源数量不足时识别缺口。"""
        critic = CriticAgent(min_sources=3)
        evidence = [
            make_evidence("e1", "source_a", 0.8),
            make_evidence("e2", "source_a", 0.7),  # 同一来源
        ]

        result = critic.analyze(evidence)

        assert result.needs_more_evidence is True
        assert result.unique_source_count == 1
        assert len(result.gaps) > 0
        assert any(g.gap_type == GapType.MISSING_SOURCE for g in result.gaps)

    def test_来源充足无缺口(self) -> None:
        """来源数量充足时无缺口。"""
        critic = CriticAgent(min_sources=2)
        evidence = [
            make_evidence("e1", "source_a", 0.8),
            make_evidence("e2", "source_b", 0.7),
            make_evidence("e3", "source_c", 0.6),
        ]

        result = critic.analyze(evidence)

        assert result.unique_source_count == 3
        assert not any(g.gap_type == GapType.MISSING_SOURCE for g in result.gaps)

    def test_声明证据不足识别缺口(self) -> None:
        """声明证据不足时识别缺口。"""
        critic = CriticAgent(min_evidence_per_claim=2)
        evidence = [make_evidence("e1", "source_a", 0.8)]
        claims = [
            Claim(
                claim_uid="c1",
                statement="测试声明",
                confidence=0.7,
                evidence_uids=["e1"],  # 只有1条证据
            )
        ]

        result = critic.analyze(evidence, claims=claims)

        assert any(g.gap_type == GapType.UNVERIFIED_CLAIM for g in result.gaps)

    def test_低置信假设识别缺口(self) -> None:
        """低置信度假设识别缺口。"""
        critic = CriticAgent()
        evidence = [make_evidence("e1", "source_a", 0.8)]
        hypotheses = [
            Hypothesis(
                statement="低置信假设",
                supporting_facts=["f1"],
                confidence=0.3,
            )
        ]

        result = critic.analyze(evidence, hypotheses=hypotheses)

        assert any(g.gap_type == GapType.INSUFFICIENT_DEPTH for g in result.gaps)

    def test_覆盖分数计算(self) -> None:
        """覆盖分数计算正确。"""
        critic = CriticAgent(min_sources=3)
        evidence = [
            make_evidence("e1", "source_a", 0.8),
            make_evidence("e2", "source_b", 0.7),
            make_evidence("e3", "source_c", 0.6),
        ]

        result = critic.analyze(evidence)

        assert 0.0 <= result.coverage_score <= 1.0


class TestJudgeAgent:
    """JudgeAgent 测试。"""

    def test_可信度差异检测冲突(self) -> None:
        """可信度差异大时检测冲突。"""
        judge = JudgeAgent(conflict_threshold=0.3)
        evidence = [
            make_evidence("e1", "source_a", 0.9),  # 高可信
            make_evidence("e2", "source_b", 0.2),  # 低可信
        ]

        result = judge.judge(evidence)

        assert len(result.conflicts) > 0

    def test_无冲突情况(self) -> None:
        """可信度相近无冲突。"""
        judge = JudgeAgent(conflict_threshold=0.3)
        evidence = [
            make_evidence("e1", "source_a", 0.7),
            make_evidence("e2", "source_b", 0.6),
        ]

        result = judge.judge(evidence)

        assert len(result.conflicts) == 0

    def test_关键冲突标记(self) -> None:
        """关键冲突数量达标时标记。"""
        judge = JudgeAgent(
            conflict_threshold=0.2,
            critical_conflict_threshold=1,
        )
        evidence = [
            make_evidence("e1", "source_a", 0.95),
            make_evidence("e2", "source_b", 0.1),
        ]

        result = judge.judge(evidence)

        # 0.95 - 0.1 = 0.85 > 0.6, 应该是 CRITICAL
        critical = [
            c for c in result.conflicts if c.severity == ConflictSeverity.CRITICAL
        ]
        assert len(critical) >= 1
        assert result.has_critical_conflicts is True

    def test_置信度调整(self) -> None:
        """涉及冲突的声明置信度被调整。"""
        judge = JudgeAgent(conflict_threshold=0.3)
        evidence = [
            make_evidence("e1", "source_a", 0.9),
            make_evidence("e2", "source_b", 0.2),
        ]
        claims = [
            Claim(
                claim_uid="c1",
                statement="涉及冲突证据的声明",
                confidence=0.8,
                evidence_uids=["e1", "e2"],
            )
        ]

        result = judge.judge(evidence, claims=claims)

        # 应该有置信度调整
        assert len(result.adjustments) > 0
        adj = result.adjustments[0]
        assert adj.adjusted_confidence < adj.original_confidence


class TestQualityGate:
    """质量闸门综合测试。"""

    def test_质量闸门通过(self) -> None:
        """满足条件时通过质量闸门。"""
        critic = CriticAgent(min_sources=2)
        judge = JudgeAgent()

        evidence = [
            make_evidence("e1", "source_a", 0.8),
            make_evidence("e2", "source_b", 0.7),
            make_evidence("e3", "source_c", 0.75),
        ]

        critique = critic.analyze(evidence)
        judgment = judge.judge(evidence)
        result = judge.evaluate_quality_gate(critique, judgment)

        assert result.passed is True
        assert result.action_required == "proceed"

    def test_质量闸门不通过_证据不足(self) -> None:
        """证据不足时不通过。"""
        critic = CriticAgent(min_sources=5)
        judge = JudgeAgent()

        evidence = [make_evidence("e1", "source_a", 0.8)]

        critique = critic.analyze(evidence)
        judgment = judge.judge(evidence)
        result = judge.evaluate_quality_gate(critique, judgment)

        assert result.passed is False
        assert "supplement" in result.action_required or len(result.blocking_issues) > 0

    def test_质量闸门不通过_关键冲突(self) -> None:
        """存在关键冲突时不通过。"""
        critic = CriticAgent(min_sources=1)
        judge = JudgeAgent(critical_conflict_threshold=1)

        evidence = [
            make_evidence("e1", "source_a", 0.95),
            make_evidence("e2", "source_b", 0.1),
        ]

        critique = critic.analyze(evidence)
        judgment = judge.judge(evidence)
        result = judge.evaluate_quality_gate(critique, judgment)

        assert result.passed is False
        assert any("冲突" in issue for issue in result.blocking_issues)
