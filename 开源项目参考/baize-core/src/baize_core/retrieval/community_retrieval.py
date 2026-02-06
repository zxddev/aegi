"""社区检测与检索增强集成。

将 GraphRAG 社区检测与向量/全文检索相结合，实现：
- 社区级别的上下文检索
- 多粒度检索（实体、社区、全局）
- 检索增强生成
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from baize_core.graph.community import (
    Community,
    CommunityNode,
    GraphRAGCommunityManager,
)


class RetrievalLevel(str, Enum):
    """检索粒度级别。"""

    ENTITY = "entity"  # 实体级别
    COMMUNITY = "community"  # 社区级别
    GLOBAL = "global"  # 全局级别
    HYBRID = "hybrid"  # 混合级别


class RetrievalContext(BaseModel):
    """检索上下文。"""

    level: RetrievalLevel = Field(description="检索级别")
    content: str = Field(description="上下文内容")
    source_type: str = Field(description="来源类型")
    source_id: str = Field(description="来源 ID")
    relevance_score: float = Field(default=0.0, description="相关性分数")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommunityRetrievalConfig(BaseModel):
    """社区检索配置。"""

    # 检索级别配置
    entity_top_k: int = Field(default=10, description="实体级别 Top-K")
    community_top_k: int = Field(default=3, description="社区级别 Top-K")
    global_top_k: int = Field(default=1, description="全局级别 Top-K")

    # 权重配置
    entity_weight: float = Field(default=0.3, description="实体权重")
    community_weight: float = Field(default=0.5, description="社区权重")
    global_weight: float = Field(default=0.2, description="全局权重")

    # 检索阈值
    min_relevance_score: float = Field(default=0.1, description="最小相关性阈值")

    # 上下文限制
    max_context_tokens: int = Field(default=4000, description="最大上下文 token 数")
    max_entities_per_community: int = Field(
        default=20, description="每个社区最大实体数"
    )


class CommunityRetrievalResult(BaseModel):
    """社区检索结果。"""

    contexts: list[RetrievalContext] = Field(
        default_factory=list, description="检索到的上下文"
    )
    entities: list[dict[str, Any]] = Field(default_factory=list, description="相关实体")
    communities: list[str] = Field(default_factory=list, description="相关社区 ID")
    total_score: float = Field(default=0.0, description="总相关性分数")
    query_expansion: list[str] = Field(default_factory=list, description="查询扩展词")


# 类型别名
EmbeddingFunc = Callable[[str], Awaitable[list[float]]]
SimilaritySearchFunc = Callable[[list[float], int], Awaitable[list[dict[str, Any]]]]


@dataclass
class CommunityRetriever:
    """社区检索器。

    整合社区检测与向量检索。
    """

    community_manager: GraphRAGCommunityManager
    config: CommunityRetrievalConfig = field(default_factory=CommunityRetrievalConfig)

    # 向量检索函数
    embed_func: EmbeddingFunc | None = None
    similarity_search_func: SimilaritySearchFunc | None = None

    # 社区摘要嵌入缓存
    _community_embeddings: dict[str, list[float]] = field(default_factory=dict)

    async def retrieve(
        self,
        query: str,
        level: RetrievalLevel = RetrievalLevel.HYBRID,
    ) -> CommunityRetrievalResult:
        """执行检索。

        Args:
            query: 查询文本
            level: 检索级别

        Returns:
            检索结果
        """
        result = CommunityRetrievalResult()
        contexts: list[RetrievalContext] = []

        if level in {RetrievalLevel.ENTITY, RetrievalLevel.HYBRID}:
            entity_contexts = await self._retrieve_entity_level(query)
            contexts.extend(entity_contexts)

        if level in {RetrievalLevel.COMMUNITY, RetrievalLevel.HYBRID}:
            community_contexts = await self._retrieve_community_level(query)
            contexts.extend(community_contexts)

        if level in {RetrievalLevel.GLOBAL, RetrievalLevel.HYBRID}:
            global_contexts = await self._retrieve_global_level(query)
            contexts.extend(global_contexts)

        # 过滤和排序
        contexts = [
            c for c in contexts if c.relevance_score >= self.config.min_relevance_score
        ]
        contexts.sort(key=lambda x: x.relevance_score, reverse=True)

        # 截断到最大上下文
        result.contexts = self._truncate_contexts(contexts)

        # 提取实体和社区
        result.entities = self._extract_entities(result.contexts)
        result.communities = list(
            set(c.source_id for c in result.contexts if c.source_type == "community")
        )

        # 计算总分
        result.total_score = sum(c.relevance_score for c in result.contexts)

        return result

    async def _retrieve_entity_level(self, query: str) -> list[RetrievalContext]:
        """实体级别检索。"""
        contexts: list[RetrievalContext] = []

        # 基于关键词匹配
        query_lower = query.lower()
        hierarchy = self.community_manager._hierarchy
        if hierarchy is None:
            return contexts

        for community in hierarchy.communities.values():
            for node in community.nodes:
                score = 0.0
                if query_lower in node.label.lower():
                    score = 1.0
                elif any(
                    query_lower in str(v).lower() for v in node.properties.values()
                ):
                    score = 0.5

                if score > 0:
                    content = self._format_entity_context(node)
                    contexts.append(
                        RetrievalContext(
                            level=RetrievalLevel.ENTITY,
                            content=content,
                            source_type="entity",
                            source_id=node.node_id,
                            relevance_score=score * self.config.entity_weight,
                            metadata={
                                "label": node.label,
                                "type": node.node_type,
                                "community_id": community.community_id,
                            },
                        )
                    )

        # 向量检索（如果可用）
        if self.embed_func and self.similarity_search_func:
            query_embedding = await self.embed_func(query)
            similar_entities = await self.similarity_search_func(
                query_embedding, self.config.entity_top_k
            )
            for entity in similar_entities:
                contexts.append(
                    RetrievalContext(
                        level=RetrievalLevel.ENTITY,
                        content=entity.get("content", ""),
                        source_type="entity",
                        source_id=entity.get("id", ""),
                        relevance_score=entity.get("score", 0.5)
                        * self.config.entity_weight,
                        metadata=entity.get("metadata", {}),
                    )
                )

        return contexts[: self.config.entity_top_k]

    async def _retrieve_community_level(self, query: str) -> list[RetrievalContext]:
        """社区级别检索。"""
        contexts: list[RetrievalContext] = []

        # 获取相关社区
        communities = self.community_manager.get_community_context(
            query, self.config.community_top_k
        )

        for community in communities:
            content = self._format_community_context(community)
            score = self._compute_community_score(query, community)
            contexts.append(
                RetrievalContext(
                    level=RetrievalLevel.COMMUNITY,
                    content=content,
                    source_type="community",
                    source_id=community.community_id,
                    relevance_score=score * self.config.community_weight,
                    metadata={
                        "size": community.size,
                        "key_entities": community.key_entities,
                        "level": community.level,
                    },
                )
            )

        return contexts

    async def _retrieve_global_level(self, query: str) -> list[RetrievalContext]:
        """全局级别检索。"""
        contexts: list[RetrievalContext] = []

        hierarchy = self.community_manager._hierarchy
        if hierarchy is None:
            return contexts

        # 获取顶层社区摘要
        root_communities = [
            hierarchy.communities[cid]
            for cid in hierarchy.root_community_ids
            if cid in hierarchy.communities
        ]

        if not root_communities:
            return contexts

        # 生成全局摘要
        global_summary = self._generate_global_summary(root_communities)
        contexts.append(
            RetrievalContext(
                level=RetrievalLevel.GLOBAL,
                content=global_summary,
                source_type="global",
                source_id="global_context",
                relevance_score=0.8 * self.config.global_weight,
                metadata={
                    "community_count": len(root_communities),
                    "total_entities": sum(c.size for c in root_communities),
                },
            )
        )

        return contexts[: self.config.global_top_k]

    def _format_entity_context(self, node: CommunityNode) -> str:
        """格式化实体上下文。"""
        parts = [f"{node.label} ({node.node_type})"]
        if node.properties:
            props = "; ".join(f"{k}: {v}" for k, v in list(node.properties.items())[:5])
            parts.append(props)
        return ": ".join(parts)

    def _format_community_context(self, community: Community) -> str:
        """格式化社区上下文。"""
        parts = []

        # 摘要
        if community.summary:
            parts.append(f"社区摘要: {community.summary}")

        # 关键实体
        if community.key_entities:
            parts.append(f"关键实体: {', '.join(community.key_entities)}")

        # 主要节点
        node_labels = [n.label for n in community.nodes[:10]]
        if node_labels:
            parts.append(f"包含: {', '.join(node_labels)}")

        # 关系
        if community.edges:
            relations = []
            for edge in community.edges[:5]:
                source = next(
                    (n.label for n in community.nodes if n.node_id == edge.source_id),
                    edge.source_id,
                )
                target = next(
                    (n.label for n in community.nodes if n.node_id == edge.target_id),
                    edge.target_id,
                )
                relations.append(f"{source} --[{edge.relation_type}]--> {target}")
            parts.append(f"关系: {'; '.join(relations)}")

        return "\n".join(parts)

    def _compute_community_score(self, query: str, community: Community) -> float:
        """计算社区相关性分数。"""
        query_lower = query.lower()
        score = 0.0

        # 摘要匹配
        if community.summary and query_lower in community.summary.lower():
            score += 0.5

        # 实体匹配
        for node in community.nodes:
            if query_lower in node.label.lower():
                score += 0.2

        # 关键实体匹配
        for entity in community.key_entities:
            if query_lower in entity.lower():
                score += 0.3

        return min(1.0, score)

    def _generate_global_summary(self, communities: list[Community]) -> str:
        """生成全局摘要。"""
        parts = [f"知识图谱包含 {len(communities)} 个主要社区:"]

        for i, community in enumerate(communities[:5], 1):
            if community.summary:
                parts.append(f"{i}. {community.summary[:200]}")
            else:
                entities = ", ".join(community.key_entities[:3])
                parts.append(f"{i}. 包含 {community.size} 个实体, 关键: {entities}")

        return "\n".join(parts)

    def _truncate_contexts(
        self, contexts: list[RetrievalContext]
    ) -> list[RetrievalContext]:
        """截断上下文到最大 token 数。"""
        # 简单估算：每个字符约 0.5 token
        max_chars = self.config.max_context_tokens * 2
        total_chars = 0
        result = []

        for ctx in contexts:
            ctx_len = len(ctx.content)
            if total_chars + ctx_len <= max_chars:
                result.append(ctx)
                total_chars += ctx_len
            else:
                # 尝试截断
                remaining = max_chars - total_chars
                if remaining > 100:
                    truncated = RetrievalContext(
                        level=ctx.level,
                        content=ctx.content[:remaining] + "...",
                        source_type=ctx.source_type,
                        source_id=ctx.source_id,
                        relevance_score=ctx.relevance_score * 0.8,
                        metadata=ctx.metadata,
                    )
                    result.append(truncated)
                break

        return result

    def _extract_entities(
        self, contexts: list[RetrievalContext]
    ) -> list[dict[str, Any]]:
        """从上下文中提取实体。"""
        entities = []
        seen_ids: set[str] = set()

        for ctx in contexts:
            if ctx.source_type == "entity" and ctx.source_id not in seen_ids:
                seen_ids.add(ctx.source_id)
                entities.append(
                    {
                        "id": ctx.source_id,
                        "label": ctx.metadata.get("label", ""),
                        "type": ctx.metadata.get("type", ""),
                        "score": ctx.relevance_score,
                    }
                )

        return entities


def build_retrieval_prompt(
    query: str,
    result: CommunityRetrievalResult,
) -> str:
    """构建检索增强的提示词。

    Args:
        query: 用户查询
        result: 检索结果

    Returns:
        增强后的提示词
    """
    parts = ["## 相关上下文\n"]

    # 全局上下文
    global_contexts = [c for c in result.contexts if c.level == RetrievalLevel.GLOBAL]
    if global_contexts:
        parts.append("### 全局信息")
        for ctx in global_contexts:
            parts.append(ctx.content)
        parts.append("")

    # 社区上下文
    community_contexts = [
        c for c in result.contexts if c.level == RetrievalLevel.COMMUNITY
    ]
    if community_contexts:
        parts.append("### 相关主题")
        for ctx in community_contexts:
            parts.append(ctx.content)
        parts.append("")

    # 实体上下文
    entity_contexts = [c for c in result.contexts if c.level == RetrievalLevel.ENTITY]
    if entity_contexts:
        parts.append("### 相关实体")
        for ctx in entity_contexts[:10]:
            parts.append(f"- {ctx.content}")
        parts.append("")

    parts.append(f"## 问题\n{query}")

    return "\n".join(parts)
