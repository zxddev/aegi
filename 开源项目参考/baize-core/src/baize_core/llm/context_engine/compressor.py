"""证据压缩器（EvidenceCompressor）。

把每条证据压缩到可控大小的"可引用片段"。
支持 extractive（规则/句子级抽取）和 LLM-notes（FactCard）两种模式。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from baize_core.llm.context_engine.schemas import (
    CompressionMode,
    EvidenceCandidate,
    EvidenceSnippet,
    FactCard,
)

logger = logging.getLogger(__name__)


@dataclass
class CompressorConfig:
    """压缩器配置。"""

    mode: CompressionMode = CompressionMode.EXTRACTIVE
    max_excerpt_chars: int = 600  # 默认摘录最大字符数
    min_excerpt_chars: int = 100  # 最小字符数
    preserve_first_sentences: int = 2  # 保留开头句子数
    preserve_numbers: bool = True  # 保留数字/日期
    preserve_entities: bool = True  # 保留实体名称
    
    # FactCard 模式配置
    factcard_max_facts: int = 5  # 每张卡片最多事实数
    factcard_cache_enabled: bool = True


# 简单的内存缓存
_excerpt_cache: dict[str, str] = {}
_factcard_cache: dict[str, FactCard] = {}


def _cache_key(text_sha256: str, question: str, max_chars: int) -> str:
    """生成缓存键。"""
    combined = f"{text_sha256}|{question}|{max_chars}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class EvidenceCompressor:
    """证据压缩器。

    支持两种压缩模式：
    1. EXTRACTIVE: 规则抽取，快速稳定
    2. LLM_NOTES: LLM 生成 FactCard，质量更高但需要额外调用
    """

    config: CompressorConfig = field(default_factory=CompressorConfig)
    
    # 可选：LLM 调用函数（用于 FactCard 生成）
    llm_call: Callable[[str, str], Awaitable[str]] | None = None

    def compress(
        self,
        candidate: EvidenceCandidate,
        citation: int,
        max_chars: int | None = None,
        section_question: str = "",
    ) -> EvidenceSnippet:
        """压缩单条证据为 EvidenceSnippet。

        Args:
            candidate: 证据候选
            citation: 引用编号
            max_chars: 最大字符数（覆盖配置）
            section_question: 章节问题（用于相关性抽取）

        Returns:
            压缩后的证据片段
        """
        max_chars = max_chars or self.config.max_excerpt_chars
        
        # 检查缓存
        cache_key = _cache_key(candidate.text_sha256, section_question, max_chars)
        if cache_key in _excerpt_cache:
            excerpt = _excerpt_cache[cache_key]
        else:
            excerpt = self._extractive_compress(
                candidate.text,
                max_chars,
                section_question,
            )
            _excerpt_cache[cache_key] = excerpt
        
        # 构建标题
        title = self._build_title(candidate)
        
        return EvidenceSnippet(
            evidence_uid=candidate.evidence_uid,
            chunk_uid=candidate.chunk_uid,
            artifact_uid=candidate.artifact_uid,
            citation=citation,
            title=title,
            excerpt=excerpt,
            source_url=candidate.uri,
            char_count=len(excerpt),
            is_conflict=bool(candidate.conflict_types),
        )

    def compress_batch(
        self,
        candidates: list[EvidenceCandidate],
        start_citation: int = 1,
        max_chars_per_item: int | None = None,
        section_question: str = "",
    ) -> list[EvidenceSnippet]:
        """批量压缩证据。

        Args:
            candidates: 证据候选列表
            start_citation: 起始引用编号
            max_chars_per_item: 每条最大字符数
            section_question: 章节问题

        Returns:
            压缩后的证据片段列表
        """
        snippets: list[EvidenceSnippet] = []
        
        for i, candidate in enumerate(candidates):
            citation = start_citation + i
            snippet = self.compress(
                candidate,
                citation,
                max_chars_per_item,
                section_question,
            )
            snippets.append(snippet)
        
        return snippets

    async def generate_factcard(
        self,
        candidate: EvidenceCandidate,
        citation: int,
        section_question: str,
    ) -> FactCard | None:
        """使用 LLM 生成 FactCard。

        Args:
            candidate: 证据候选
            citation: 引用编号
            section_question: 章节问题

        Returns:
            FactCard 或 None（如果 LLM 不可用或失败）
        """
        if self.llm_call is None:
            return None
        
        # 检查缓存
        cache_key = _cache_key(candidate.text_sha256, section_question, 0)
        if self.config.factcard_cache_enabled and cache_key in _factcard_cache:
            return _factcard_cache[cache_key]
        
        try:
            prompt = self._build_factcard_prompt(candidate.text, section_question)
            response = await self.llm_call("system", prompt)
            factcard = self._parse_factcard_response(response, candidate, citation)
            
            if factcard and self.config.factcard_cache_enabled:
                _factcard_cache[cache_key] = factcard
            
            return factcard
        except Exception as e:
            logger.warning("FactCard 生成失败: %s", e)
            return None

    def _extractive_compress(
        self,
        text: str,
        max_chars: int,
        question: str = "",
    ) -> str:
        """抽取式压缩。

        策略：
        1. 优先保留开头句子
        2. 保留包含问题关键词的句子
        3. 保留包含数字/日期的句子
        4. 截断到最大长度
        """
        if len(text) <= max_chars:
            return text.strip()
        
        # 分句
        sentences = self._split_sentences(text)
        if not sentences:
            return text[:max_chars].strip() + "..."
        
        # 评分每个句子
        scored_sentences = self._score_sentences(sentences, question)
        
        # 选择句子
        selected: list[str] = []
        current_len = 0
        
        # 先保留开头句子
        for i in range(min(self.config.preserve_first_sentences, len(sentences))):
            sent = sentences[i]
            if current_len + len(sent) + 1 <= max_chars:
                selected.append(sent)
                current_len += len(sent) + 1
        
        # 按分数添加其他句子
        for sent, score in scored_sentences:
            if sent in selected:
                continue
            if current_len + len(sent) + 1 <= max_chars:
                selected.append(sent)
                current_len += len(sent) + 1
            if current_len >= max_chars * 0.9:
                break
        
        # 按原始顺序排序
        sentence_order = {s: i for i, s in enumerate(sentences)}
        selected.sort(key=lambda s: sentence_order.get(s, 999))
        
        result = " ".join(selected)
        
        # 如果仍然超长，截断
        if len(result) > max_chars:
            result = result[:max_chars - 3].strip() + "..."
        
        return result

    def _split_sentences(self, text: str) -> list[str]:
        """分句。"""
        # 中英文分句
        pattern = r'(?<=[。！？.!?])\s*'
        sentences = re.split(pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _score_sentences(
        self, sentences: list[str], question: str
    ) -> list[tuple[str, float]]:
        """对句子评分。"""
        question_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', question.lower()))
        scored: list[tuple[str, float]] = []
        
        for sent in sentences:
            score = 0.0
            sent_lower = sent.lower()
            
            # 关键词匹配
            if question_words:
                sent_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', sent_lower))
                overlap = len(question_words & sent_words)
                score += overlap * 0.2
            
            # 数字/日期加分
            if self.config.preserve_numbers:
                numbers = re.findall(r'\d+', sent)
                if numbers:
                    score += 0.1 * min(len(numbers), 3)
            
            # 长度适中加分（避免太短或太长）
            if 50 < len(sent) < 200:
                score += 0.1
            
            scored.append((sent, score))
        
        # 按分数排序
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _build_title(self, candidate: EvidenceCandidate) -> str:
        """构建证据标题。"""
        if candidate.summary:
            return candidate.summary[:100]
        if candidate.uri:
            # 从 URL 提取标题
            return candidate.uri.split("/")[-1][:80] or candidate.uri[:80]
        return "证据"

    def _build_factcard_prompt(self, text: str, question: str) -> str:
        """构建 FactCard 生成 prompt。"""
        return f"""请从以下文本中抽取与问题相关的关键事实。

问题：{question}

文本：
{text[:2000]}

请输出：
1. 关键事实（最多5条，每条一句话）
2. 涉及的实体（人物、组织、地点）
3. 相关日期
4. 与问题的相关性说明（一句话）

请使用以下格式：
事实: <事实1>
事实: <事实2>
...
实体: <实体列表，逗号分隔>
日期: <日期列表，逗号分隔>
相关性: <相关性说明>"""

    def _parse_factcard_response(
        self,
        response: str,
        candidate: EvidenceCandidate,
        citation: int,
    ) -> FactCard | None:
        """解析 FactCard 响应。"""
        try:
            facts: list[str] = []
            entities: list[str] = []
            dates: list[str] = []
            relevance = ""
            
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("事实:") or line.startswith("事实："):
                    fact = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                    if fact:
                        facts.append(fact)
                elif line.startswith("实体:") or line.startswith("实体："):
                    entity_str = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                    entities = [e.strip() for e in entity_str.split(",") if e.strip()]
                elif line.startswith("日期:") or line.startswith("日期："):
                    date_str = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                    dates = [d.strip() for d in date_str.split(",") if d.strip()]
                elif line.startswith("相关性:") or line.startswith("相关性："):
                    relevance = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            
            if not facts:
                return None
            
            return FactCard(
                evidence_uid=candidate.evidence_uid,
                citation=citation,
                facts=facts[:self.config.factcard_max_facts],
                entities=entities[:10],
                dates=dates[:5],
                source_summary=candidate.summary or "",
                relevance_note=relevance,
            )
        except Exception as e:
            logger.warning("FactCard 解析失败: %s", e)
            return None


def clear_compression_cache() -> None:
    """清空压缩缓存。"""
    _excerpt_cache.clear()
    _factcard_cache.clear()
    logger.info("压缩缓存已清空")
