"""混合检索模块。

结合全文搜索（OpenSearch）和语义搜索（Qdrant），
使用 Reciprocal Rank Fusion (RRF) 或 Reranker 进行结果融合。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from baize_core.storage.opensearch_store import ChunkSearchResult as OSChunkResult
from baize_core.storage.opensearch_store import OpenSearchStore
from baize_core.storage.qdrant_store import QdrantStore
from baize_core.storage.qdrant_store import VectorSearchResult as QdrantResult

logger = logging.getLogger(__name__)


class FusionMethod(Enum):
    """融合方法。"""

    RRF = "rrf"  # Reciprocal Rank Fusion
    WEIGHTED = "weighted"  # 加权融合
    RERANK = "rerank"  # 使用 Reranker 重排序


@dataclass
class HybridSearchResult:
    """混合搜索结果。"""

    chunk_uid: str
    artifact_uid: str
    text: str
    score: float  # 融合后的分数
    lexical_score: float | None = None  # 全文搜索分数
    semantic_score: float | None = None  # 语义搜索分数
    rerank_score: float | None = None  # Reranker 分数
    highlights: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HybridSearchConfig:
    """混合搜索配置。"""

    # 各检索源权重
    lexical_weight: float = 0.3
    semantic_weight: float = 0.7
    # RRF 参数
    rrf_k: int = 60  # RRF 常数 k
    # 结果限制
    lexical_limit: int = 20
    semantic_limit: int = 20
    final_limit: int = 10
    # 融合方法
    fusion_method: FusionMethod = FusionMethod.RRF
    # 语义搜索阈值
    semantic_score_threshold: float | None = None


class Reranker(ABC):
    """Reranker 基类。"""

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """对文档进行重排序。

        Args:
            query: 查询文本
            documents: 待排序文档列表
            top_k: 返回 top-k 结果

        Returns:
            列表，每项为 (原始索引, 分数)
        """


class CrossEncoderReranker(Reranker):
    """Cross-Encoder Reranker。

    使用 sentence-transformers 的 CrossEncoder 进行重排序。
    """

    def __init__(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> None:
        """初始化 Cross-Encoder。

        Args:
            model_name: 模型名称
        """
        self._model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> Any:
        """确保模型已加载。"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self._model_name)
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers 未安装。请运行: pip install sentence-transformers"
                ) from e
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """使用 Cross-Encoder 对文档进行重排序。"""
        if not documents:
            return []
        model = self._ensure_model()
        # 构建查询-文档对
        pairs = [[query, doc] for doc in documents]
        # 预测分数
        scores = model.predict(pairs)
        # 构建索引-分数对
        indexed_scores = list(enumerate(scores))
        # 按分数降序排序
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        if top_k:
            indexed_scores = indexed_scores[:top_k]
        return [(idx, float(score)) for idx, score in indexed_scores]


class LLMReranker(Reranker):
    """LLM Reranker。

    使用 LLM 进行文档相关性评估和重排序。
    """

    def __init__(
        self,
        llm_call: Callable[[str], str],
        batch_size: int = 5,
    ) -> None:
        """初始化 LLM Reranker。

        Args:
            llm_call: LLM 调用函数，接受 prompt 返回响应
            batch_size: 每批处理的文档数
        """
        self._llm_call = llm_call
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """使用 LLM 对文档进行重排序。"""
        if not documents:
            return []
        # 简化实现：对每个文档评估相关性
        scores: list[tuple[int, float]] = []
        for idx, doc in enumerate(documents):
            prompt = self._build_relevance_prompt(query, doc)
            try:
                response = self._llm_call(prompt)
                score = self._parse_relevance_score(response)
                scores.append((idx, score))
            except Exception as e:
                logger.warning("LLM rerank 失败: %s", e)
                scores.append((idx, 0.0))
        # 按分数降序排序
        scores.sort(key=lambda x: x[1], reverse=True)
        if top_k:
            scores = scores[:top_k]
        return scores

    def _build_relevance_prompt(self, query: str, document: str) -> str:
        """构建相关性评估 prompt。"""
        return f"""请评估以下文档与查询的相关性。

查询: {query}

文档:
{document[:1000]}

请给出 0-10 的相关性评分，其中：
- 0 表示完全不相关
- 5 表示部分相关
- 10 表示高度相关

只输出数字评分，不要其他内容。"""

    def _parse_relevance_score(self, response: str) -> float:
        """解析相关性分数。"""
        try:
            score = float(response.strip())
            return min(max(score / 10.0, 0.0), 1.0)
        except ValueError:
            return 0.5  # 默认中等相关


def reciprocal_rank_fusion(
    rankings: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion (RRF) 算法。

    Args:
        rankings: 多个排序列表，每个列表包含 (item_id, score) 对
        k: RRF 常数，默认 60

    Returns:
        融合后的排序列表
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (item_id, _) in enumerate(ranking):
            if item_id not in scores:
                scores[item_id] = 0.0
            scores[item_id] += 1.0 / (k + rank + 1)
    # 按 RRF 分数排序
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_items


def weighted_fusion(
    rankings: list[list[tuple[str, float]]],
    weights: list[float],
) -> list[tuple[str, float]]:
    """加权融合算法。

    Args:
        rankings: 多个排序列表，每个列表包含 (item_id, score) 对
        weights: 各排序列表的权重

    Returns:
        融合后的排序列表
    """
    if len(rankings) != len(weights):
        raise ValueError("rankings 和 weights 长度必须相同")
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights, strict=False):
        # 归一化分数
        if not ranking:
            continue
        max_score = max(score for _, score in ranking) if ranking else 1.0
        for item_id, score in ranking:
            normalized = score / max_score if max_score > 0 else 0.0
            if item_id not in scores:
                scores[item_id] = 0.0
            scores[item_id] += normalized * weight
    # 按融合分数排序
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_items


class HybridRetriever:
    """混合检索器。

    结合 OpenSearch 全文搜索和 Qdrant 语义搜索。
    """

    def __init__(
        self,
        opensearch_store: OpenSearchStore,
        qdrant_store: QdrantStore,
        config: HybridSearchConfig,
        embedding_func: Callable[[str], list[float]] | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        """初始化混合检索器。

        Args:
            opensearch_store: OpenSearch 存储
            qdrant_store: Qdrant 存储
            config: 搜索配置
            embedding_func: 文本转向量函数
            reranker: 可选的 Reranker
        """
        self._os_store = opensearch_store
        self._qdrant_store = qdrant_store
        self._config = config
        self._embedding_func = embedding_func
        self._reranker = reranker

    async def search(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        artifact_uid: str | None = None,
        task_id: str | None = None,
    ) -> list[HybridSearchResult]:
        """执行混合搜索。

        Args:
            query: 查询文本
            query_embedding: 可选，查询向量（如果未提供则使用 embedding_func）
            artifact_uid: 可选，限定 artifact
            task_id: 可选，限定 task

        Returns:
            混合搜索结果列表
        """
        # 获取 embedding
        if query_embedding is None and self._embedding_func is not None:
            query_embedding = self._embedding_func(query)

        # 并行执行两种搜索
        lexical_results = await self._lexical_search(query, artifact_uid, task_id)
        semantic_results: list[QdrantResult] = []
        if query_embedding is not None:
            semantic_results = await self._semantic_search(
                query_embedding, artifact_uid, task_id
            )

        # 构建结果映射
        results_map: dict[str, HybridSearchResult] = {}

        # 处理全文搜索结果
        for lexical_result in lexical_results:
            results_map[lexical_result.chunk_uid] = HybridSearchResult(
                chunk_uid=lexical_result.chunk_uid,
                artifact_uid=lexical_result.artifact_uid,
                text=lexical_result.text,
                score=0.0,
                lexical_score=lexical_result.score,
                highlights=lexical_result.highlights,
            )

        # 处理语义搜索结果
        for semantic_result in semantic_results:
            if semantic_result.chunk_uid in results_map:
                results_map[
                    semantic_result.chunk_uid
                ].semantic_score = semantic_result.score
            else:
                results_map[semantic_result.chunk_uid] = HybridSearchResult(
                    chunk_uid=semantic_result.chunk_uid,
                    artifact_uid=semantic_result.artifact_uid,
                    text=semantic_result.text,
                    score=0.0,
                    semantic_score=semantic_result.score,
                    metadata=semantic_result.metadata,
                )

        # 融合排序
        if self._config.fusion_method == FusionMethod.RERANK and self._reranker:
            results = await self._rerank_fusion(query, list(results_map.values()))
        elif self._config.fusion_method == FusionMethod.WEIGHTED:
            results = self._weighted_fusion(list(results_map.values()))
        else:
            results = self._rrf_fusion(lexical_results, semantic_results, results_map)

        return results[: self._config.final_limit]

    async def _lexical_search(
        self,
        query: str,
        artifact_uid: str | None,
        task_id: str | None,
    ) -> list[OSChunkResult]:
        """执行全文搜索。"""
        return await self._os_store.search_chunks(
            query=query,
            max_results=self._config.lexical_limit,
            artifact_uid=artifact_uid,
            task_id=task_id,
        )

    async def _semantic_search(
        self,
        query_embedding: list[float],
        artifact_uid: str | None,
        task_id: str | None,
    ) -> list[QdrantResult]:
        """执行语义搜索。"""
        return await self._qdrant_store.search(
            query_embedding=query_embedding,
            limit=self._config.semantic_limit,
            artifact_uid=artifact_uid,
            task_id=task_id,
            score_threshold=self._config.semantic_score_threshold,
        )

    def _rrf_fusion(
        self,
        lexical_results: list[OSChunkResult],
        semantic_results: list[QdrantResult],
        results_map: dict[str, HybridSearchResult],
    ) -> list[HybridSearchResult]:
        """RRF 融合。"""
        lexical_ranking = [(r.chunk_uid, r.score) for r in lexical_results]
        semantic_ranking = [(r.chunk_uid, r.score) for r in semantic_results]
        fused = reciprocal_rank_fusion(
            [lexical_ranking, semantic_ranking],
            k=self._config.rrf_k,
        )
        results: list[HybridSearchResult] = []
        for chunk_uid, score in fused:
            if chunk_uid in results_map:
                result = results_map[chunk_uid]
                result.score = score
                results.append(result)
        return results

    def _weighted_fusion(
        self,
        results: list[HybridSearchResult],
    ) -> list[HybridSearchResult]:
        """加权融合。"""
        for result in results:
            score = 0.0
            if result.lexical_score is not None:
                score += result.lexical_score * self._config.lexical_weight
            if result.semantic_score is not None:
                score += result.semantic_score * self._config.semantic_weight
            result.score = score
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    async def _rerank_fusion(
        self,
        query: str,
        results: list[HybridSearchResult],
    ) -> list[HybridSearchResult]:
        """Reranker 融合。"""
        if not self._reranker or not results:
            return results
        documents = [r.text for r in results]
        reranked = await self._reranker.rerank(
            query=query,
            documents=documents,
            top_k=self._config.final_limit,
        )
        reranked_results: list[HybridSearchResult] = []
        for orig_idx, score in reranked:
            result = results[orig_idx]
            result.rerank_score = score
            result.score = score
            reranked_results.append(result)
        return reranked_results
