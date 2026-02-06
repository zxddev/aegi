"""上下文工程核心数据结构。

定义证据选择、压缩、预算管理、章节写作所需的数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CompressionMode(str, Enum):
    """压缩模式。"""

    EXTRACTIVE = "extractive"  # 抽取式（规则/句子级）
    LLM_NOTES = "llm_notes"  # LLM 生成 FactCard
    HYBRID = "hybrid"  # 混合模式


class WriterStrategy(str, Enum):
    """写作策略。"""

    SINGLE_PASS = "single_pass"  # 单次调用
    MAP_REDUCE = "map_reduce"  # Map-Reduce 模式
    REFINE = "refine"  # 迭代精炼模式


@dataclass
class EvidenceCandidate:
    """证据候选项（选择器输入）。

    封装 Evidence + Chunk 的必要信息，用于排序和选择。
    """

    evidence_uid: str
    chunk_uid: str
    artifact_uid: str
    text: str  # Chunk.text 原文
    text_sha256: str  # Chunk.text_sha256
    uri: str | None = None
    summary: str | None = None  # Evidence.summary
    base_credibility: float = 0.5
    score_total: float | None = None  # Evidence.score.total
    conflict_types: list[str] = field(default_factory=list)
    domain: str | None = None  # 从 uri 提取的域名
    is_preferred_domain: bool = False  # 是否优先域名


@dataclass
class EvidenceSnippet:
    """压缩后的证据片段（压缩器输出）。

    包含可引用的文本片段和元数据。
    """

    evidence_uid: str
    chunk_uid: str
    artifact_uid: str
    citation: int  # 引用编号
    title: str  # 显示标题
    excerpt: str  # 压缩后的摘录
    source_url: str | None = None
    char_count: int = 0  # 摘录字符数
    is_conflict: bool = False  # 是否冲突证据

    def to_citation_block(self) -> str:
        """转换为引用块格式。"""
        conflict_mark = "（冲突证据）" if self.is_conflict else ""
        return f"[{self.citation}] 标题: {self.title}{conflict_mark}\n内容: {self.excerpt}"


@dataclass
class FactCard:
    """事实卡片（LLM-notes 模式产物）。

    结构化的事实抽取结果，用于 Map-Reduce 写作。
    """

    evidence_uid: str
    citation: int
    facts: list[str]  # 关键事实列表
    entities: list[str]  # 涉及实体
    dates: list[str]  # 涉及日期
    source_summary: str  # 来源摘要
    relevance_note: str  # 与章节问题的相关性说明

    def to_markdown(self) -> str:
        """转换为 Markdown 格式。"""
        lines = [f"### 证据 [{self.citation}]"]
        if self.facts:
            lines.append("**关键事实**:")
            for fact in self.facts:
                lines.append(f"- {fact}")
        if self.entities:
            lines.append(f"**涉及实体**: {', '.join(self.entities)}")
        if self.dates:
            lines.append(f"**相关日期**: {', '.join(self.dates)}")
        if self.relevance_note:
            lines.append(f"**相关性**: {self.relevance_note}")
        return "\n".join(lines)


@dataclass
class PromptBudget:
    """Prompt 预算配置与状态。

    管理上下文预算分配和使用跟踪。
    """

    max_tokens: int = 8000  # 最大 token 数（保守估计）
    max_chars: int = 32000  # 最大字符数（约 4 字符/token）
    reserved_for_system: int = 500  # 系统指令预留
    reserved_for_output: int = 2000  # 输出预留
    max_evidence_count: int = 15  # 最大证据条数
    max_chars_per_evidence: int = 800  # 每条证据最大字符数

    # 使用跟踪
    used_chars: int = 0
    evidence_count: int = 0

    @property
    def available_chars(self) -> int:
        """可用字符数。"""
        return self.max_chars - self.reserved_for_system - self.reserved_for_output - self.used_chars

    @property
    def can_add_evidence(self) -> bool:
        """是否还能添加证据。"""
        return (
            self.evidence_count < self.max_evidence_count
            and self.available_chars > 100
        )

    def allocate(self, chars: int) -> bool:
        """尝试分配字符预算。

        Args:
            chars: 需要的字符数

        Returns:
            是否分配成功
        """
        if chars <= self.available_chars:
            self.used_chars += chars
            self.evidence_count += 1
            return True
        return False

    def get_remaining_per_evidence(self, remaining_evidence: int) -> int:
        """计算剩余每条证据的平均可用字符数。"""
        if remaining_evidence <= 0:
            return 0
        return min(
            self.available_chars // remaining_evidence,
            self.max_chars_per_evidence,
        )


@dataclass
class SectionWriteConfig:
    """章节写作配置。"""

    strategy: WriterStrategy = WriterStrategy.SINGLE_PASS
    compression_mode: CompressionMode = CompressionMode.EXTRACTIVE
    budget: PromptBudget = field(default_factory=PromptBudget)
    
    # Map-Reduce 配置
    batch_size: int = 8  # 每批证据数
    max_iterations: int = 5  # 最大迭代次数
    
    # 写作要求
    min_paragraphs: int = 4
    max_paragraphs: int = 8
    min_citations_per_paragraph: int = 1
    
    # 缓存控制
    use_cache: bool = True
    cache_ttl_hours: int = 24


@dataclass
class SectionWriteResult:
    """章节写作结果。"""

    section_id: str
    markdown: str
    citations_used: list[int]  # 使用的引用编号
    evidence_uids_used: list[str]  # 使用的证据 UID
    
    # 执行统计
    llm_calls: int = 1
    total_input_chars: int = 0
    total_output_chars: int = 0
    strategy_used: WriterStrategy = WriterStrategy.SINGLE_PASS
    
    # 降级信息
    degraded: bool = False
    degradation_reason: str | None = None
    
    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)
