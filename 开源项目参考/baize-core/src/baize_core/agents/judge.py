"""Judge Agent 实现。

Judge 负责冲突检测、置信度调整和仲裁。

支持两种模式：
1. 规则驱动（默认）：基于阈值和启发式规则
2. LLM 驱动：使用结构化输出生成仲裁结果
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.schemas.content import ContentSource
from baize_core.schemas.critique import (
    ConfidenceAdjustment,
    ConflictSeverity,
    Critique,
    EvidenceConflict,
    Judgment,
    QualityGateResult,
)
from baize_core.schemas.evidence import Claim, Evidence
from baize_core.schemas.extraction import JudgeResult
from baize_core.schemas.ooda import Hypothesis

if TYPE_CHECKING:
    from baize_core.llm.runner import LlmRunner
    from baize_core.schemas.policy import StageType


# LLM 仲裁系统提示
JUDGE_SYSTEM_PROMPT = """你是一个冲突仲裁专家。
你的任务是检测证据和声明之间的冲突，并进行仲裁。

仲裁原则：
1. 识别矛盾：找出相互矛盾的声明或证据
2. 评估来源：考虑来源的可信度和权威性
3. 时间因素：较新的证据可能更可靠
4. 一致性：多个独立来源支持的观点更可信

输出要求：
- 明确标识冲突双方
- 说明冲突类型（矛盾/不一致/时间冲突）
- 提供解决建议
- 给出整体一致性评分
"""


class JudgeAgent:
    """Judge Agent。

    职责：
    1. 冲突检测
    2. 置信度调整
    3. 综合仲裁
    """

    def __init__(
        self,
        *,
        conflict_threshold: float = 0.3,
        critical_conflict_threshold: int = 2,
    ) -> None:
        """初始化 Judge。

        Args:
            conflict_threshold: 冲突检测阈值（可信度差异）
            critical_conflict_threshold: 关键冲突数量阈值
        """
        self._conflict_threshold = conflict_threshold
        self._critical_threshold = critical_conflict_threshold

    def judge(
        self,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim] | None = None,
        hypotheses: Sequence[Hypothesis] | None = None,
    ) -> Judgment:
        """执行仲裁分析。

        Args:
            evidence: 证据列表
            claims: 声明列表（可选）
            hypotheses: 假设列表（可选）

        Returns:
            Judgment 仲裁结果
        """
        conflicts: list[EvidenceConflict] = []
        adjustments: list[ConfidenceAdjustment] = []

        # 检测证据间冲突
        evidence_conflicts = self._detect_evidence_conflicts(evidence)
        conflicts.extend(evidence_conflicts)

        # 根据冲突调整置信度
        if claims:
            claim_adjustments = self._adjust_claim_confidence(claims, conflicts)
            adjustments.extend(claim_adjustments)

        if hypotheses:
            hypothesis_adjustments = self._adjust_hypothesis_confidence(
                hypotheses, conflicts
            )
            adjustments.extend(hypothesis_adjustments)

        # 计算整体置信度
        overall_confidence = self._calculate_overall_confidence(
            evidence=evidence,
            conflicts=conflicts,
            adjustments=adjustments,
        )

        # 检查是否有关键冲突
        critical_count = sum(
            1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL
        )
        has_critical = critical_count >= self._critical_threshold

        # 生成建议
        recommendation = self._generate_recommendation(
            conflicts=conflicts,
            has_critical=has_critical,
            overall_confidence=overall_confidence,
        )

        return Judgment(
            conflicts=conflicts,
            adjustments=adjustments,
            overall_confidence=overall_confidence,
            has_critical_conflicts=has_critical,
            recommendation=recommendation,
        )

    def evaluate_quality_gate(
        self,
        critique: Critique,
        judgment: Judgment,
    ) -> QualityGateResult:
        """评估质量闸门。

        综合 Critic 和 Judge 的结果，决定是否通过。

        Args:
            critique: Critic 分析结果
            judgment: Judge 仲裁结果

        Returns:
            QualityGateResult 质量闸门结果
        """
        blocking_issues: list[str] = []
        warnings: list[str] = []

        # 检查 Critic 结果
        if critique.needs_more_evidence:
            if critique.coverage_score < 0.3:
                blocking_issues.append(
                    f"证据覆盖严重不足（{critique.coverage_score:.2f}）"
                )
            else:
                warnings.append(f"证据覆盖不足（{critique.coverage_score:.2f}）")

        high_priority_gaps = [g for g in critique.gaps if g.priority <= 2]
        if high_priority_gaps:
            blocking_issues.append(f"{len(high_priority_gaps)} 处高优先级证据缺口")

        # 检查 Judge 结果
        if judgment.has_critical_conflicts:
            blocking_issues.append("存在关键冲突，需要重新评估")

        major_conflicts = [
            c
            for c in judgment.conflicts
            if c.severity in {ConflictSeverity.MAJOR, ConflictSeverity.CRITICAL}
        ]
        if major_conflicts:
            warnings.append(f"{len(major_conflicts)} 处严重冲突需要关注")

        # 决定行动
        if blocking_issues:
            if any("证据覆盖" in issue for issue in blocking_issues):
                action_required = "supplement"
            elif any("冲突" in issue for issue in blocking_issues):
                action_required = "revise"
            else:
                action_required = "reject"
            passed = False
        elif warnings:
            action_required = "proceed"
            passed = True
        else:
            action_required = "proceed"
            passed = True

        return QualityGateResult(
            passed=passed,
            critique=critique,
            judgment=judgment,
            blocking_issues=blocking_issues,
            warnings=warnings,
            action_required=action_required,
        )

    def _detect_evidence_conflicts(
        self,
        evidence: Sequence[Evidence],
    ) -> list[EvidenceConflict]:
        """检测证据间冲突。

        Args:
            evidence: 证据列表

        Returns:
            冲突列表
        """
        conflicts: list[EvidenceConflict] = []

        # 按来源域名分组
        domain_evidence: dict[str, list[Evidence]] = defaultdict(list)
        for evi in evidence:
            domain = self._extract_domain(evi.uri or evi.source)
            domain_evidence[domain].append(evi)

        # 检测不同可信度来源之间的冲突
        high_cred = [e for e in evidence if e.base_credibility >= 0.7]
        low_cred = [e for e in evidence if e.base_credibility < 0.4]

        for high_evi in high_cred:
            for low_evi in low_cred:
                if high_evi.source != low_evi.source:
                    # 不同来源的高低可信度冲突
                    cred_diff = high_evi.base_credibility - low_evi.base_credibility
                    if cred_diff > self._conflict_threshold:
                        severity = self._determine_severity(cred_diff)
                        conflicts.append(
                            EvidenceConflict(
                                severity=severity,
                                evidence_a_uid=high_evi.evidence_uid,
                                evidence_b_uid=low_evi.evidence_uid,
                                description=(
                                    f"来源可信度差异：{high_evi.source}"
                                    f"（{high_evi.base_credibility:.2f}）vs "
                                    f"{low_evi.source}（{low_evi.base_credibility:.2f}）"
                                ),
                                confidence_impact=-cred_diff * 0.2,
                            )
                        )

        return conflicts

    def _adjust_claim_confidence(
        self,
        claims: Sequence[Claim],
        conflicts: list[EvidenceConflict],
    ) -> list[ConfidenceAdjustment]:
        """调整声明置信度。

        Args:
            claims: 声明列表
            conflicts: 冲突列表

        Returns:
            调整列表
        """
        adjustments: list[ConfidenceAdjustment] = []
        conflict_evidence = set()
        for conflict in conflicts:
            conflict_evidence.add(conflict.evidence_a_uid)
            conflict_evidence.add(conflict.evidence_b_uid)

        for claim in claims:
            # 检查 Claim 关联的证据是否涉及冲突
            involved = [uid for uid in claim.evidence_uids if uid in conflict_evidence]
            if involved:
                # 根据涉及的冲突数量调整
                penalty = min(len(involved) * 0.1, 0.3)
                new_confidence = max(0.0, claim.confidence - penalty)
                adjustments.append(
                    ConfidenceAdjustment(
                        target_id=claim.claim_uid,
                        original_confidence=claim.confidence,
                        adjusted_confidence=new_confidence,
                        reason=f"涉及 {len(involved)} 处证据冲突",
                    )
                )

        return adjustments

    def _adjust_hypothesis_confidence(
        self,
        hypotheses: Sequence[Hypothesis],
        conflicts: list[EvidenceConflict],
    ) -> list[ConfidenceAdjustment]:
        """调整假设置信度。

        Args:
            hypotheses: 假设列表
            conflicts: 冲突列表

        Returns:
            调整列表
        """
        adjustments: list[ConfidenceAdjustment] = []

        for hypothesis in hypotheses:
            # 有矛盾事实的假设降低置信度
            if hypothesis.contradicting_facts:
                penalty = min(len(hypothesis.contradicting_facts) * 0.15, 0.4)
                new_confidence = max(0.0, hypothesis.confidence - penalty)
                adjustments.append(
                    ConfidenceAdjustment(
                        target_id=hypothesis.hypothesis_id,
                        original_confidence=hypothesis.confidence,
                        adjusted_confidence=new_confidence,
                        reason=f"存在 {len(hypothesis.contradicting_facts)} 条矛盾证据",
                    )
                )

        return adjustments

    def _calculate_overall_confidence(
        self,
        evidence: Sequence[Evidence],
        conflicts: list[EvidenceConflict],
        adjustments: list[ConfidenceAdjustment],
    ) -> float:
        """计算整体置信度。

        Args:
            evidence: 证据列表
            conflicts: 冲突列表
            adjustments: 调整列表

        Returns:
            整体置信度（0-1）
        """
        if not evidence:
            return 0.0

        # 基础分数：证据平均可信度
        base_score = sum(e.base_credibility for e in evidence) / len(evidence)

        # 冲突惩罚
        conflict_penalty = len(conflicts) * 0.05
        critical_conflicts = sum(
            1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL
        )
        conflict_penalty += critical_conflicts * 0.1

        # 调整惩罚
        adjustment_penalty = sum(
            adj.original_confidence - adj.adjusted_confidence for adj in adjustments
        ) / max(len(adjustments), 1)

        overall = base_score - conflict_penalty - adjustment_penalty
        return max(0.0, min(1.0, overall))

    def _determine_severity(self, cred_diff: float) -> ConflictSeverity:
        """确定冲突严重程度。

        Args:
            cred_diff: 可信度差异

        Returns:
            冲突严重程度
        """
        if cred_diff > 0.6:
            return ConflictSeverity.CRITICAL
        if cred_diff > 0.4:
            return ConflictSeverity.MAJOR
        if cred_diff > 0.2:
            return ConflictSeverity.MODERATE
        return ConflictSeverity.MINOR

    def _generate_recommendation(
        self,
        conflicts: list[EvidenceConflict],
        has_critical: bool,
        overall_confidence: float,
    ) -> str:
        """生成建议。

        Args:
            conflicts: 冲突列表
            has_critical: 是否有关键冲突
            overall_confidence: 整体置信度

        Returns:
            建议文本
        """
        if has_critical:
            return "存在关键冲突，建议暂停输出并重新核实证据来源"
        if overall_confidence < 0.3:
            return "整体置信度过低，建议补充更多可信来源"
        if conflicts:
            return f"存在 {len(conflicts)} 处冲突，建议在报告中显式呈现不确定性"
        return "证据质量良好，可以继续生成报告"

    def _extract_domain(self, source: str) -> str:
        """提取域名。

        Args:
            source: 来源字符串

        Returns:
            域名
        """
        if source.startswith(("http://", "https://")):
            parsed = urlparse(source)
            return parsed.netloc or source
        return source

    async def judge_with_llm(
        self,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim] | None = None,
        *,
        llm_runner: LlmRunner,
        stage: StageType,
        task_id: str,
    ) -> JudgeResult:
        """使用 LLM 进行冲突仲裁。

        通过结构化输出约束 LLM 生成标准化的仲裁结果。

        Args:
            evidence: 证据列表
            claims: 声明列表（可选）
            llm_runner: LLM 运行器
            stage: 编排阶段
            task_id: 任务 ID

        Returns:
            JudgeResult 结构化仲裁结果
        """
        from baize_core.llm.structured import GenerationMode

        # 构建仲裁提示
        evidence_text = self._format_evidence_for_llm(evidence)
        claims_text = self._format_claims_for_llm(claims) if claims else ""
        user_query = (
            "请对以下证据与声明进行冲突仲裁，并输出结构化结果。\n\n"
            "请分析：\n"
            "1. 是否存在冲突\n"
            "2. 冲突列表（如有）\n"
            "3. 一致性声明列表\n"
            "4. 整体一致性评分（0-1）\n"
            "5. 仲裁摘要\n"
        )
        prompt = (
            PromptBuilder()
            .add_system_instruction(
                JUDGE_SYSTEM_PROMPT,
                source_type=ContentSource.INTERNAL,
                source_ref="judge_system",
            )
            .add_user_query(
                user_query, source_type=ContentSource.INTERNAL, source_ref="judge_query"
            )
            .add_evidence(
                f"## 证据列表\n{evidence_text}",
                source_ref="judge_evidence",
                content_type="evidence_list",
            )
        )
        if claims_text:
            prompt = prompt.add_evidence(
                f"## 相关声明\n{claims_text}",
                source_ref="judge_claims",
                content_type="claims",
            )
        built = prompt.build()
        system_msg = next(
            (m["content"] for m in built.messages if m["role"] == "system"), ""
        )
        user_msg = next(
            (m["content"] for m in built.messages if m["role"] == "user"), ""
        )

        result = await llm_runner.generate_structured(
            system=system_msg,
            user=user_msg,
            schema=JudgeResult,
            stage=stage,
            task_id=task_id,
            max_retries=3,
            mode=GenerationMode.POST_VALIDATE,
        )

        return result.data

    def _format_evidence_for_llm(self, evidence: Sequence[Evidence]) -> str:
        """格式化证据列表用于 LLM 分析。

        Args:
            evidence: 证据列表

        Returns:
            格式化后的文本
        """
        lines: list[str] = []
        for i, evi in enumerate(evidence, 1):
            summary = evi.summary or "(无摘要)"
            source = evi.source or "(未知来源)"
            cred = f"{evi.base_credibility:.2f}"
            lines.append(f"{i}. [{source}] 可信度:{cred} - {summary}")
        return "\n".join(lines) if lines else "(无证据)"

    def _format_claims_for_llm(self, claims: Sequence[Claim]) -> str:
        """格式化声明列表用于 LLM 分析。

        Args:
            claims: 声明列表

        Returns:
            格式化后的文本
        """
        lines: list[str] = []
        for i, claim in enumerate(claims, 1):
            stmt = claim.statement[:100]
            conf = f"{claim.confidence:.2f}"
            lines.append(f"{i}. {stmt}... (置信度:{conf})")
        return "\n".join(lines) if lines else "(无声明)"
