"""证据选择器（EvidenceSelector）。

在每个章节内对候选证据做排序/去重/过滤，选出最相关、最可信的证据。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from baize_core.llm.context_engine.schemas import EvidenceCandidate

logger = logging.getLogger(__name__)

# 高质量域名列表（从 deep_research.py 精简）
PREFERRED_DOMAINS: frozenset[str] = frozenset({
    # 主流新闻媒体
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "theguardian.com", "nytimes.com", "washingtonpost.com",
    "cnn.com", "aljazeera.com", "ft.com", "economist.com",
    "wsj.com", "bloomberg.com", "politico.com",
    "foreignpolicy.com", "foreignaffairs.com",
    # 军事/国防
    "defensenews.com", "janes.com", "defense.gov",
    "breakingdefense.com", "defenseone.com",
    # 智库/研究机构
    "rand.org", "csis.org", "cfr.org", "brookings.edu",
    "carnegieendowment.org", "atlanticcouncil.org",
    "iiss.org", "sipri.org", "heritage.org",
    # 政府/官方
    "state.gov", "whitehouse.gov", "nato.int", "un.org",
    # 学术
    "nature.com", "sciencedirect.com",
})

# 低质量域名模式
LOW_QUALITY_PATTERNS: tuple[str, ...] = (
    ".cn", ".com.cn", "zhihu.com", "baidu.com",
    "weibo.com", "sina.com", "sohu.com", "163.com",
    "qq.com", "tencent.com", "bilibili.com",
    "facebook.com", "twitter.com", "instagram.com",
    "tiktok.com", "youtube.com",
)


@dataclass
class SelectorConfig:
    """选择器配置。"""

    max_candidates: int = 20  # 最大候选数
    min_credibility: float = 0.2  # 最低可信度
    prefer_recent: bool = True  # 偏好最新
    dedupe_by_content: bool = True  # 按内容去重
    dedupe_similarity_threshold: float = 0.8  # 去重相似度阈值
    
    # 评分权重
    credibility_weight: float = 0.3
    domain_weight: float = 0.25
    relevance_weight: float = 0.35
    recency_weight: float = 0.1


@dataclass
class EvidenceSelector:
    """证据选择器。

    对候选证据进行评分、排序、去重，返回最优的 Top-K 证据。
    """

    config: SelectorConfig = field(default_factory=SelectorConfig)
    
    # 可选：外部相关性评分函数（用于接入 HybridRetriever）
    relevance_scorer: Callable[[str, str], float] | None = None

    def select(
        self,
        candidates: list[EvidenceCandidate],
        section_question: str,
        top_k: int | None = None,
    ) -> list[EvidenceCandidate]:
        """选择最优证据。

        Args:
            candidates: 候选证据列表
            section_question: 章节问题（用于相关性评分）
            top_k: 返回数量，默认使用 config.max_candidates

        Returns:
            排序后的证据列表
        """
        if not candidates:
            return []

        top_k = top_k or self.config.max_candidates

        # 1. 预处理：提取域名，过滤低可信度
        processed = self._preprocess(candidates)
        
        # 2. 去重
        if self.config.dedupe_by_content:
            processed = self._deduplicate(processed)
        
        # 3. 评分
        scored = self._score_all(processed, section_question)
        
        # 4. 排序并返回 Top-K
        scored.sort(key=lambda x: x[1], reverse=True)
        
        result = [item[0] for item in scored[:top_k]]
        
        logger.debug(
            "EvidenceSelector: %d candidates -> %d selected (top_k=%d)",
            len(candidates), len(result), top_k
        )
        
        return result

    def _preprocess(
        self, candidates: list[EvidenceCandidate]
    ) -> list[EvidenceCandidate]:
        """预处理：提取域名，标记优先域名，过滤低质量。"""
        result: list[EvidenceCandidate] = []
        
        for cand in candidates:
            # 过滤低可信度
            if cand.base_credibility < self.config.min_credibility:
                continue
            
            # 提取域名
            if cand.uri:
                try:
                    parsed = urlparse(cand.uri)
                    domain = parsed.netloc.lower()
                    cand.domain = domain
                    
                    # 检查是否优先域名
                    base_domain = self._extract_base_domain(domain)
                    cand.is_preferred_domain = base_domain in PREFERRED_DOMAINS
                    
                    # 过滤低质量域名
                    if any(pattern in domain for pattern in LOW_QUALITY_PATTERNS):
                        continue
                except Exception:
                    pass
            
            result.append(cand)
        
        return result

    def _extract_base_domain(self, domain: str) -> str:
        """提取基础域名（去除 www 等前缀）。"""
        if domain.startswith("www."):
            return domain[4:]
        return domain

    def _deduplicate(
        self, candidates: list[EvidenceCandidate]
    ) -> list[EvidenceCandidate]:
        """按内容去重。"""
        seen_hashes: set[str] = set()
        seen_texts: list[str] = []
        result: list[EvidenceCandidate] = []
        
        for cand in candidates:
            # 按哈希去重
            if cand.text_sha256 in seen_hashes:
                continue
            seen_hashes.add(cand.text_sha256)
            
            # 按文本相似度去重（简单前缀匹配）
            text_prefix = cand.text[:200].lower().strip()
            is_duplicate = False
            for seen in seen_texts:
                if self._text_similarity(text_prefix, seen) > self.config.dedupe_similarity_threshold:
                    is_duplicate = True
                    break
            
            if is_duplicate:
                continue
            
            seen_texts.append(text_prefix)
            result.append(cand)
        
        return result

    def _text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单 Jaccard）。"""
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def _score_all(
        self,
        candidates: list[EvidenceCandidate],
        section_question: str,
    ) -> list[tuple[EvidenceCandidate, float]]:
        """对所有候选评分。"""
        scored: list[tuple[EvidenceCandidate, float]] = []
        
        for cand in candidates:
            score = self._compute_score(cand, section_question)
            scored.append((cand, score))
        
        return scored

    def _compute_score(
        self,
        candidate: EvidenceCandidate,
        section_question: str,
    ) -> float:
        """计算单个证据的综合评分。"""
        # 可信度分数
        credibility_score = candidate.base_credibility
        if candidate.score_total is not None:
            credibility_score = (credibility_score + candidate.score_total) / 2
        
        # 域名分数
        domain_score = 0.5
        if candidate.is_preferred_domain:
            domain_score = 1.0
        elif candidate.domain and any(
            pattern in candidate.domain for pattern in LOW_QUALITY_PATTERNS
        ):
            domain_score = 0.1
        
        # 相关性分数
        if self.relevance_scorer:
            relevance_score = self.relevance_scorer(section_question, candidate.text)
        else:
            relevance_score = self._simple_relevance(section_question, candidate.text)
        
        # 冲突惩罚
        conflict_penalty = 0.0
        if candidate.conflict_types:
            conflict_penalty = 0.1 * len(candidate.conflict_types)
        
        # 综合评分
        total = (
            self.config.credibility_weight * credibility_score
            + self.config.domain_weight * domain_score
            + self.config.relevance_weight * relevance_score
            - conflict_penalty
        )
        
        return max(0.0, min(1.0, total))

    def _simple_relevance(self, question: str, text: str) -> float:
        """简单相关性评分（词项覆盖）。"""
        question_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', question.lower()))
        text_words = set(re.findall(r'[\u4e00-\u9fff]+|\w+', text[:1000].lower()))
        
        if not question_words:
            return 0.5
        
        # 计算问题词在文本中的覆盖率
        covered = len(question_words & text_words)
        coverage = covered / len(question_words)
        
        return min(1.0, coverage * 1.2)  # 轻微放大


def create_candidates_from_evidence_chain(
    evidence_items: list,
    chunk_map: dict,
    artifact_map: dict,
) -> list[EvidenceCandidate]:
    """从证据链创建候选列表。

    Args:
        evidence_items: Evidence 对象列表
        chunk_map: chunk_uid -> Chunk 映射
        artifact_map: artifact_uid -> Artifact 映射

    Returns:
        EvidenceCandidate 列表
    """
    candidates: list[EvidenceCandidate] = []
    
    for evidence in evidence_items:
        chunk = chunk_map.get(evidence.chunk_uid)
        if chunk is None:
            continue
        
        artifact = artifact_map.get(chunk.artifact_uid)
        if artifact is None:
            continue
        
        candidate = EvidenceCandidate(
            evidence_uid=evidence.evidence_uid,
            chunk_uid=evidence.chunk_uid,
            artifact_uid=chunk.artifact_uid,
            text=chunk.text,
            text_sha256=chunk.text_sha256,
            uri=evidence.uri,
            summary=evidence.summary,
            base_credibility=evidence.base_credibility,
            score_total=evidence.score.total if evidence.score else None,
            conflict_types=evidence.conflict_types or [],
        )
        candidates.append(candidate)
    
    return candidates
