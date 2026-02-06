"""Prompt 预算管理器（PromptBudgeter）。

管理上下文预算分配，保证永不溢出。
支持字符/近似 token 估算，与策略引擎对齐。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from baize_core.llm.context_engine.schemas import (
    EvidenceSnippet,
    PromptBudget,
)

logger = logging.getLogger(__name__)


class BudgetAction(str, Enum):
    """预算动作。"""

    ACCEPT = "accept"  # 接受
    TRUNCATE = "truncate"  # 截断
    REDUCE_COUNT = "reduce_count"  # 减少条数
    SUMMARIZE = "summarize"  # 切换到摘要模式
    REJECT = "reject"  # 拒绝


@dataclass
class BudgetDecision:
    """预算决策。"""

    action: BudgetAction
    allowed_chars: int
    allowed_count: int
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgeterConfig:
    """预算器配置。"""

    # Token/字符估算
    chars_per_token: float = 4.0  # 中英文混合平均
    chinese_chars_per_token: float = 1.5  # 中文字符
    english_chars_per_token: float = 4.0  # 英文字符
    
    # 默认预算
    default_max_tokens: int = 8000
    default_max_chars: int = 32000
    reserved_for_system: int = 800  # 系统指令预留
    reserved_for_query: int = 500  # 用户查询预留
    reserved_for_output: int = 2000  # 输出预留
    
    # 证据限制
    max_evidence_count: int = 20
    min_chars_per_evidence: int = 100
    max_chars_per_evidence: int = 1000
    
    # 降级阈值
    truncation_threshold: float = 0.9  # 90% 预算时开始截断
    reduce_count_threshold: float = 0.95  # 95% 时减少条数


@dataclass
class PromptBudgeter:
    """Prompt 预算管理器。

    负责：
    1. 估算 prompt 大小
    2. 分配证据预算
    3. 决定截断/减少策略
    4. 追踪使用情况
    """

    config: BudgeterConfig = field(default_factory=BudgeterConfig)
    
    # 使用追踪
    _allocated_chars: int = field(default=0, init=False)
    _evidence_count: int = field(default=0, init=False)

    def create_budget(
        self,
        max_tokens: int | None = None,
        evidence_count_hint: int = 10,
    ) -> PromptBudget:
        """创建预算配置。

        Args:
            max_tokens: 最大 token 数（覆盖配置）
            evidence_count_hint: 预期证据数量

        Returns:
            PromptBudget 实例
        """
        max_tokens = max_tokens or self.config.default_max_tokens
        max_chars = int(max_tokens * self.config.chars_per_token)
        
        # 计算可用于证据的字符数
        available = (
            max_chars
            - self.config.reserved_for_system
            - self.config.reserved_for_query
            - self.config.reserved_for_output
        )
        
        # 计算每条证据的预算
        max_per_evidence = min(
            available // max(evidence_count_hint, 1),
            self.config.max_chars_per_evidence,
        )
        max_per_evidence = max(max_per_evidence, self.config.min_chars_per_evidence)
        
        return PromptBudget(
            max_tokens=max_tokens,
            max_chars=max_chars,
            reserved_for_system=self.config.reserved_for_system,
            reserved_for_output=self.config.reserved_for_output,
            max_evidence_count=min(evidence_count_hint, self.config.max_evidence_count),
            max_chars_per_evidence=max_per_evidence,
        )

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数。

        Args:
            text: 文本内容

        Returns:
            估计的 token 数
        """
        if not text:
            return 0
        
        # 区分中英文
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        
        chinese_tokens = chinese_chars / self.config.chinese_chars_per_token
        other_tokens = other_chars / self.config.english_chars_per_token
        
        return int(chinese_tokens + other_tokens) + 1  # +1 作为安全边际

    def estimate_chars(self, tokens: int) -> int:
        """从 token 数估算字符数。"""
        return int(tokens * self.config.chars_per_token)

    def check_budget(
        self,
        budget: PromptBudget,
        snippets: list[EvidenceSnippet],
        additional_chars: int = 0,
    ) -> BudgetDecision:
        """检查预算并返回决策。

        Args:
            budget: 预算配置
            snippets: 证据片段列表
            additional_chars: 额外字符（如查询、指令）

        Returns:
            预算决策
        """
        total_chars = sum(s.char_count for s in snippets) + additional_chars
        evidence_count = len(snippets)
        
        # 计算使用率
        usage_ratio = total_chars / budget.max_chars if budget.max_chars > 0 else 1.0
        
        # 正常情况
        if usage_ratio < self.config.truncation_threshold:
            return BudgetDecision(
                action=BudgetAction.ACCEPT,
                allowed_chars=budget.max_chars - additional_chars,
                allowed_count=evidence_count,
                reason="预算充足",
                metadata={"usage_ratio": usage_ratio},
            )
        
        # 需要截断
        if usage_ratio < self.config.reduce_count_threshold:
            allowed_chars = int(budget.max_chars * self.config.truncation_threshold)
            return BudgetDecision(
                action=BudgetAction.TRUNCATE,
                allowed_chars=allowed_chars - additional_chars,
                allowed_count=evidence_count,
                reason=f"预算紧张（使用率 {usage_ratio:.1%}），需要截断",
                metadata={"usage_ratio": usage_ratio, "original_chars": total_chars},
            )
        
        # 需要减少条数
        target_chars = int(budget.max_chars * self.config.truncation_threshold)
        avg_chars = total_chars / evidence_count if evidence_count > 0 else 1
        target_count = max(1, int(target_chars / avg_chars))
        
        return BudgetDecision(
            action=BudgetAction.REDUCE_COUNT,
            allowed_chars=target_chars - additional_chars,
            allowed_count=target_count,
            reason=f"预算严重不足（使用率 {usage_ratio:.1%}），减少证据数量到 {target_count}",
            metadata={
                "usage_ratio": usage_ratio,
                "original_count": evidence_count,
                "target_count": target_count,
            },
        )

    def allocate_budget(
        self,
        budget: PromptBudget,
        evidence_count: int,
    ) -> list[int]:
        """为每条证据分配字符预算。

        Args:
            budget: 预算配置
            evidence_count: 证据数量

        Returns:
            每条证据的字符预算列表
        """
        if evidence_count <= 0:
            return []
        
        available = budget.available_chars
        
        # 均匀分配，但不超过单条限制
        per_evidence = min(
            available // evidence_count,
            budget.max_chars_per_evidence,
        )
        per_evidence = max(per_evidence, self.config.min_chars_per_evidence)
        
        # 前几条可以稍多一些（重要性更高）
        allocations: list[int] = []
        remaining = available
        
        for i in range(evidence_count):
            if i < 3:
                # 前 3 条多分配 20%
                alloc = int(per_evidence * 1.2)
            elif i < evidence_count // 2:
                # 前半部分正常分配
                alloc = per_evidence
            else:
                # 后半部分少分配 20%
                alloc = int(per_evidence * 0.8)
            
            alloc = min(alloc, remaining, budget.max_chars_per_evidence)
            alloc = max(alloc, self.config.min_chars_per_evidence)
            
            allocations.append(alloc)
            remaining -= alloc
        
        return allocations

    def apply_budget_decision(
        self,
        decision: BudgetDecision,
        snippets: list[EvidenceSnippet],
    ) -> list[EvidenceSnippet]:
        """应用预算决策到证据片段。

        Args:
            decision: 预算决策
            snippets: 原始证据片段

        Returns:
            调整后的证据片段列表
        """
        if decision.action == BudgetAction.ACCEPT:
            return snippets
        
        if decision.action == BudgetAction.REDUCE_COUNT:
            # 减少条数，保留最重要的（按顺序，假设已排序）
            return snippets[:decision.allowed_count]
        
        if decision.action == BudgetAction.TRUNCATE:
            # 截断每条证据
            target_per_item = decision.allowed_chars // len(snippets) if snippets else 0
            result: list[EvidenceSnippet] = []
            
            for snippet in snippets:
                if snippet.char_count <= target_per_item:
                    result.append(snippet)
                else:
                    # 截断 excerpt
                    truncated_excerpt = snippet.excerpt[:target_per_item - 3] + "..."
                    result.append(EvidenceSnippet(
                        evidence_uid=snippet.evidence_uid,
                        chunk_uid=snippet.chunk_uid,
                        artifact_uid=snippet.artifact_uid,
                        citation=snippet.citation,
                        title=snippet.title,
                        excerpt=truncated_excerpt,
                        source_url=snippet.source_url,
                        char_count=len(truncated_excerpt),
                        is_conflict=snippet.is_conflict,
                    ))
            
            return result
        
        return snippets

    def get_planned_cost(self, snippets: list[EvidenceSnippet]) -> dict[str, int]:
        """获取计划成本（用于策略引擎）。

        Args:
            snippets: 证据片段

        Returns:
            包含 token_estimate 的字典
        """
        total_chars = sum(s.char_count for s in snippets)
        token_estimate = self.estimate_tokens("x" * total_chars)  # 近似估算
        
        return {
            "token_estimate": token_estimate,
            "char_count": total_chars,
            "evidence_count": len(snippets),
        }
