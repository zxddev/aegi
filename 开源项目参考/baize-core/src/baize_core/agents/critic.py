"""Critic Agent 实现。

Critic 负责识别证据缺口，产出缺失证据清单。
不做业务结论输出，只做质量评估。

支持两种模式：
1. 规则驱动（默认）：基于阈值和启发式规则
2. LLM 驱动：使用结构化输出生成评估结果
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from baize_core.llm.prompt_builder import PromptBuilder
from baize_core.schemas.content import ContentSource
from baize_core.schemas.critique import (
    Critique,
    EvidenceGap,
    GapType,
)
from baize_core.schemas.evidence import Claim, Evidence
from baize_core.schemas.extraction import CritiqueResult
from baize_core.schemas.ooda import Hypothesis

if TYPE_CHECKING:
    from baize_core.llm.runner import LlmRunner
    from baize_core.schemas.policy import StageType


# 质量阈值
MIN_SOURCES_THRESHOLD = 3  # 最少来源数量
MIN_EVIDENCE_PER_CLAIM = 2  # 每个 Claim 最少证据数
MIN_COVERAGE_SCORE = 0.6  # 最低覆盖分数

# LLM 分析系统提示
CRITIC_SYSTEM_PROMPT = """你是一个证据质量分析专家。
你的任务是评估给定证据的质量，识别证据缺口，并提供改进建议。

评估标准：
1. 来源多样性：是否有多个独立来源
2. 证据覆盖度：关键声明是否有充分证据支持
3. 时效性：证据是否及时
4. 可信度：来源的权威性和可靠性

输出要求：
- 客观、中立地评估
- 明确指出缺口和问题
- 提供可操作的改进建议
"""


class CriticAgent:
    """Critic Agent。

    职责：
    1. 识别证据缺口
    2. 评估证据覆盖率
    3. 产出补洞建议
    """

    def __init__(
        self,
        *,
        min_sources: int = MIN_SOURCES_THRESHOLD,
        min_evidence_per_claim: int = MIN_EVIDENCE_PER_CLAIM,
        min_coverage_score: float = MIN_COVERAGE_SCORE,
    ) -> None:
        """初始化 Critic。

        Args:
            min_sources: 最少来源数量阈值
            min_evidence_per_claim: 每个 Claim 最少证据数
            min_coverage_score: 最低覆盖分数
        """
        self._min_sources = min_sources
        self._min_evidence_per_claim = min_evidence_per_claim
        self._min_coverage_score = min_coverage_score

    def analyze(
        self,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim] | None = None,
        hypotheses: Sequence[Hypothesis] | None = None,
    ) -> Critique:
        """分析证据并识别缺口。

        Args:
            evidence: 证据列表
            claims: 声明列表（可选）
            hypotheses: 假设列表（可选）

        Returns:
            Critique 分析结果
        """
        gaps: list[EvidenceGap] = []

        # 统计来源
        sources = {e.source for e in evidence if e.source}
        unique_source_count = len(sources)

        # 检查来源数量
        if unique_source_count < self._min_sources:
            gaps.append(
                EvidenceGap(
                    gap_type=GapType.MISSING_SOURCE,
                    description=f"来源数量不足：当前 {unique_source_count}，"
                    f"需要至少 {self._min_sources} 个独立来源",
                    priority=1,
                    suggested_query="扩展搜索范围，增加更多来源",
                )
            )

        # 检查 Claim 证据覆盖
        if claims:
            claim_gaps = self._check_claim_coverage(claims, evidence)
            gaps.extend(claim_gaps)

        # 检查假设支撑
        if hypotheses:
            hypothesis_gaps = self._check_hypothesis_support(hypotheses)
            gaps.extend(hypothesis_gaps)

        # 计算覆盖分数
        coverage_score = self._calculate_coverage_score(
            evidence=evidence,
            claims=claims or [],
            gaps=gaps,
        )

        # 判断是否需要更多证据
        needs_more = coverage_score < self._min_coverage_score or len(gaps) > 0

        # 生成摘要
        summary = self._generate_summary(
            evidence_count=len(evidence),
            source_count=unique_source_count,
            gap_count=len(gaps),
            coverage_score=coverage_score,
        )

        return Critique(
            gaps=gaps,
            total_evidence_count=len(evidence),
            unique_source_count=unique_source_count,
            coverage_score=coverage_score,
            needs_more_evidence=needs_more,
            summary=summary,
        )

    def _check_claim_coverage(
        self,
        claims: Sequence[Claim],
        evidence: Sequence[Evidence],
    ) -> list[EvidenceGap]:
        """检查声明的证据覆盖。

        Args:
            claims: 声明列表
            evidence: 证据列表

        Returns:
            缺口列表
        """
        gaps: list[EvidenceGap] = []
        evidence_set = {e.evidence_uid for e in evidence}

        for claim in claims:
            # 检查 Claim 绑定的证据是否存在
            valid_evidence = [uid for uid in claim.evidence_uids if uid in evidence_set]

            if len(valid_evidence) < self._min_evidence_per_claim:
                gaps.append(
                    EvidenceGap(
                        gap_type=GapType.UNVERIFIED_CLAIM,
                        description=f"声明 '{claim.statement[:50]}...' 证据不足："
                        f"当前 {len(valid_evidence)} 条，"
                        f"需要 {self._min_evidence_per_claim} 条",
                        related_claim_ids=[claim.claim_uid],
                        priority=2,
                        suggested_query=f"搜索更多关于 '{claim.statement[:30]}' 的证据",
                    )
                )

        return gaps

    def _check_hypothesis_support(
        self,
        hypotheses: Sequence[Hypothesis],
    ) -> list[EvidenceGap]:
        """检查假设的支撑情况。

        Args:
            hypotheses: 假设列表

        Returns:
            缺口列表
        """
        gaps: list[EvidenceGap] = []

        for hypothesis in hypotheses:
            # 低置信度假设需要更多支撑
            if hypothesis.confidence < 0.5:
                gaps.append(
                    EvidenceGap(
                        gap_type=GapType.INSUFFICIENT_DEPTH,
                        description=f"假设 '{hypothesis.statement[:50]}...' "
                        f"置信度过低（{hypothesis.confidence:.2f}），需要更多支撑证据",
                        priority=3,
                        suggested_query=f"深入研究 '{hypothesis.statement[:30]}'",
                    )
                )

            # 存在矛盾事实
            if hypothesis.contradicting_facts:
                gaps.append(
                    EvidenceGap(
                        gap_type=GapType.UNVERIFIED_CLAIM,
                        description=f"假设 '{hypothesis.statement[:50]}...' "
                        f"存在 {len(hypothesis.contradicting_facts)} 条矛盾证据",
                        priority=2,
                        suggested_query="验证矛盾证据的真实性",
                    )
                )

        return gaps

    def _calculate_coverage_score(
        self,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim],
        gaps: list[EvidenceGap],
    ) -> float:
        """计算覆盖分数。

        Args:
            evidence: 证据列表
            claims: 声明列表
            gaps: 缺口列表

        Returns:
            覆盖分数（0-1）
        """
        if not evidence:
            return 0.0

        # 基础分数：证据数量
        evidence_score = min(len(evidence) / 10, 1.0)

        # 来源分数
        sources = {e.source for e in evidence if e.source}
        source_score = min(len(sources) / self._min_sources, 1.0)

        # 缺口惩罚
        gap_penalty = len(gaps) * 0.1
        gap_penalty = min(gap_penalty, 0.5)  # 最多扣 0.5

        # 综合分数
        score = (evidence_score * 0.4 + source_score * 0.6) - gap_penalty
        return max(0.0, min(1.0, score))

    def _generate_summary(
        self,
        evidence_count: int,
        source_count: int,
        gap_count: int,
        coverage_score: float,
    ) -> str:
        """生成分析摘要。

        Args:
            evidence_count: 证据数量
            source_count: 来源数量
            gap_count: 缺口数量
            coverage_score: 覆盖分数

        Returns:
            摘要文本
        """
        status = "充足" if coverage_score >= self._min_coverage_score else "不足"
        return (
            f"证据分析：{evidence_count} 条证据，"
            f"{source_count} 个独立来源，"
            f"覆盖分数 {coverage_score:.2f}（{status}），"
            f"{gap_count} 处需要补充"
        )

    async def analyze_with_llm(
        self,
        evidence: Sequence[Evidence],
        claims: Sequence[Claim] | None = None,
        *,
        llm_runner: LlmRunner,
        stage: StageType,
        task_id: str,
    ) -> CritiqueResult:
        """使用 LLM 进行证据质量分析。

        通过结构化输出约束 LLM 生成标准化的评估结果。

        Args:
            evidence: 证据列表
            claims: 声明列表（可选）
            llm_runner: LLM 运行器
            stage: 编排阶段
            task_id: 任务 ID

        Returns:
            CritiqueResult 结构化评估结果
        """
        from baize_core.llm.structured import GenerationMode

        # 构建分析提示
        evidence_text = self._format_evidence_for_llm(evidence)
        claims_text = self._format_claims_for_llm(claims) if claims else ""
        user_query = (
            "请分析以下证据的质量，并输出结构化评估。\n\n"
            "请评估：\n"
            "1. 整体质量评分（0-1）\n"
            "2. 证据缺口列表\n"
            "3. 质量问题\n"
            "4. 是否需要更多证据\n"
            "5. 评估摘要\n"
        )
        prompt = (
            PromptBuilder()
            .add_system_instruction(
                CRITIC_SYSTEM_PROMPT,
                source_type=ContentSource.INTERNAL,
                source_ref="critic_system",
            )
            .add_user_query(
                user_query,
                source_type=ContentSource.INTERNAL,
                source_ref="critic_query",
            )
            .add_evidence(
                f"## 证据列表\n{evidence_text}",
                source_ref="critic_evidence",
                content_type="evidence_list",
            )
        )
        if claims_text:
            prompt = prompt.add_evidence(
                f"## 相关声明\n{claims_text}",
                source_ref="critic_claims",
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
            schema=CritiqueResult,
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
            evi_count = len(claim.evidence_uids)
            lines.append(f"{i}. {stmt}... (置信度:{conf}, 证据:{evi_count}条)")
        return "\n".join(lines) if lines else "(无声明)"
