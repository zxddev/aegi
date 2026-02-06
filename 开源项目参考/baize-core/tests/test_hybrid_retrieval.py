"""混合检索测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from baize_core.retrieval.hybrid import (
    FusionMethod,
    HybridRetriever,
    HybridSearchConfig,
    LLMReranker,
    reciprocal_rank_fusion,
    weighted_fusion,
)
from baize_core.storage.opensearch_store import ChunkSearchResult as OSChunkResult
from baize_core.storage.qdrant_store import VectorSearchResult as QdrantResult


class TestReciprocalRankFusion:
    """RRF 算法测试。"""

    def test_single_ranking(self) -> None:
        """测试单个排序列表。"""
        ranking = [("a", 1.0), ("b", 0.8), ("c", 0.6)]
        result = reciprocal_rank_fusion([ranking], k=60)
        # 检查顺序保持
        assert result[0][0] == "a"
        assert result[1][0] == "b"
        assert result[2][0] == "c"

    def test_multiple_rankings(self) -> None:
        """测试多个排序列表融合。"""
        ranking1 = [("a", 1.0), ("b", 0.8), ("c", 0.6)]
        ranking2 = [("b", 1.0), ("c", 0.8), ("a", 0.6)]
        result = reciprocal_rank_fusion([ranking1, ranking2], k=60)
        # b 在两个列表中都靠前，应该排第一
        assert result[0][0] == "b"

    def test_disjoint_rankings(self) -> None:
        """测试不重叠的排序列表。"""
        ranking1 = [("a", 1.0), ("b", 0.8)]
        ranking2 = [("c", 1.0), ("d", 0.8)]
        result = reciprocal_rank_fusion([ranking1, ranking2], k=60)
        assert len(result) == 4

    def test_empty_ranking(self) -> None:
        """测试空排序列表。"""
        result = reciprocal_rank_fusion([[]], k=60)
        assert result == []


class TestWeightedFusion:
    """加权融合测试。"""

    def test_equal_weights(self) -> None:
        """测试相等权重。"""
        ranking1 = [("a", 1.0), ("b", 0.5)]
        ranking2 = [("b", 1.0), ("a", 0.5)]
        result = weighted_fusion([ranking1, ranking2], [0.5, 0.5])
        # a 和 b 的分数应该相同
        scores = {item: score for item, score in result}
        assert abs(scores["a"] - scores["b"]) < 0.01

    def test_different_weights(self) -> None:
        """测试不同权重。"""
        ranking1 = [("a", 1.0)]  # 权重 0.7
        ranking2 = [("b", 1.0)]  # 权重 0.3
        result = weighted_fusion([ranking1, ranking2], [0.7, 0.3])
        assert result[0][0] == "a"
        assert result[0][1] == 0.7

    def test_weight_mismatch(self) -> None:
        """测试权重数量不匹配。"""
        with pytest.raises(ValueError):
            weighted_fusion([[], []], [0.5])


class TestLLMReranker:
    """LLM Reranker 测试。"""

    @pytest.mark.asyncio
    async def test_rerank(self) -> None:
        """测试 LLM 重排序。"""

        def mock_llm(prompt: str) -> str:
            # 模拟：包含 "important" 的文档得高分
            if "important" in prompt:
                return "8"
            return "3"

        reranker = LLMReranker(llm_call=mock_llm)
        documents = [
            "This is a normal document.",
            "This is an important document.",
            "Another normal one.",
        ]
        result = await reranker.rerank("query", documents, top_k=2)
        # 第二个文档（索引 1）应该排第一
        assert result[0][0] == 1
        assert result[0][1] == 0.8

    @pytest.mark.asyncio
    async def test_rerank_empty(self) -> None:
        """测试空文档列表。"""

        def mock_llm(prompt: str) -> str:
            return "5"

        reranker = LLMReranker(llm_call=mock_llm)
        result = await reranker.rerank("query", [])
        assert result == []


class TestHybridRetriever:
    """混合检索器测试。"""

    @pytest.fixture
    def mock_os_store(self) -> AsyncMock:
        """Mock OpenSearch store。"""
        store = AsyncMock()
        store.search_chunks = AsyncMock(
            return_value=[
                OSChunkResult(
                    chunk_uid="chk_1",
                    artifact_uid="art_1",
                    text="文档1内容",
                    score=1.5,
                    highlights=["<em>文档1</em>"],
                ),
                OSChunkResult(
                    chunk_uid="chk_2",
                    artifact_uid="art_1",
                    text="文档2内容",
                    score=1.2,
                    highlights=[],
                ),
            ]
        )
        return store

    @pytest.fixture
    def mock_qdrant_store(self) -> AsyncMock:
        """Mock Qdrant store。"""
        store = AsyncMock()
        store.search = AsyncMock(
            return_value=[
                QdrantResult(
                    chunk_uid="chk_2",
                    artifact_uid="art_1",
                    text="文档2内容",
                    score=0.95,
                    metadata={},
                ),
                QdrantResult(
                    chunk_uid="chk_3",
                    artifact_uid="art_1",
                    text="文档3内容",
                    score=0.85,
                    metadata={},
                ),
            ]
        )
        return store

    @pytest.mark.asyncio
    async def test_rrf_search(
        self, mock_os_store: AsyncMock, mock_qdrant_store: AsyncMock
    ) -> None:
        """测试 RRF 融合搜索。"""
        config = HybridSearchConfig(fusion_method=FusionMethod.RRF)
        retriever = HybridRetriever(
            opensearch_store=mock_os_store,
            qdrant_store=mock_qdrant_store,
            config=config,
        )
        embedding = [0.1] * 1536
        results = await retriever.search("查询", query_embedding=embedding)
        # chk_2 在两个来源都有，应该排名靠前
        assert any(r.chunk_uid == "chk_2" for r in results)
        # 应该有 3 个唯一结果
        chunk_uids = [r.chunk_uid for r in results]
        assert len(set(chunk_uids)) == 3

    @pytest.mark.asyncio
    async def test_weighted_search(
        self, mock_os_store: AsyncMock, mock_qdrant_store: AsyncMock
    ) -> None:
        """测试加权融合搜索。"""
        config = HybridSearchConfig(
            fusion_method=FusionMethod.WEIGHTED,
            lexical_weight=0.3,
            semantic_weight=0.7,
        )
        retriever = HybridRetriever(
            opensearch_store=mock_os_store,
            qdrant_store=mock_qdrant_store,
            config=config,
        )
        embedding = [0.1] * 1536
        results = await retriever.search("查询", query_embedding=embedding)
        assert len(results) > 0
        # 所有结果都应该有分数
        for r in results:
            assert r.score >= 0

    @pytest.mark.asyncio
    async def test_rerank_search(
        self, mock_os_store: AsyncMock, mock_qdrant_store: AsyncMock
    ) -> None:
        """测试 Reranker 融合搜索。"""
        mock_reranker = AsyncMock()
        mock_reranker.rerank = AsyncMock(return_value=[(0, 0.9), (1, 0.8), (2, 0.7)])
        config = HybridSearchConfig(
            fusion_method=FusionMethod.RERANK,
            final_limit=3,
        )
        retriever = HybridRetriever(
            opensearch_store=mock_os_store,
            qdrant_store=mock_qdrant_store,
            config=config,
            reranker=mock_reranker,
        )
        embedding = [0.1] * 1536
        results = await retriever.search("查询", query_embedding=embedding)
        mock_reranker.rerank.assert_called_once()
        # 结果应该有 rerank_score
        assert all(r.rerank_score is not None for r in results)

    @pytest.mark.asyncio
    async def test_search_with_embedding_func(
        self, mock_os_store: AsyncMock, mock_qdrant_store: AsyncMock
    ) -> None:
        """测试使用 embedding 函数。"""

        def mock_embedding(text: str) -> list[float]:
            return [0.1] * 1536

        config = HybridSearchConfig()
        retriever = HybridRetriever(
            opensearch_store=mock_os_store,
            qdrant_store=mock_qdrant_store,
            config=config,
            embedding_func=mock_embedding,
        )
        await retriever.search("查询")
        # 应该调用了语义搜索
        mock_qdrant_store.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_lexical_only_search(
        self, mock_os_store: AsyncMock, mock_qdrant_store: AsyncMock
    ) -> None:
        """测试仅全文搜索（无 embedding）。"""
        config = HybridSearchConfig()
        retriever = HybridRetriever(
            opensearch_store=mock_os_store,
            qdrant_store=mock_qdrant_store,
            config=config,
        )
        results = await retriever.search("查询")
        # 仅调用全文搜索
        mock_os_store.search_chunks.assert_called_once()
        # 语义搜索应该返回空
        # 结果仅来自全文搜索
        assert len(results) == 2
