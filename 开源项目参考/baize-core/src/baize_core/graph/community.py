"""GraphRAG 社区摘要模块。

实现基于图的社区发现和摘要生成：
- 社区检测（Louvain/Leiden 算法）
- 层次化社区结构
- 社区摘要生成
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CommunityNode:
    """社区节点。"""

    node_id: str
    label: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommunityEdge:
    """社区边。"""

    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Community:
    """社区结构。"""

    community_id: str
    level: int  # 层次级别（0 为最细粒度）
    nodes: list[CommunityNode]
    edges: list[CommunityEdge]
    parent_id: str | None = None  # 父社区 ID
    child_ids: list[str] = field(default_factory=list)
    summary: str | None = None
    key_entities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> int:
        """社区节点数。"""
        return len(self.nodes)


@dataclass
class CommunityHierarchy:
    """社区层次结构。"""

    communities: dict[str, Community]  # community_id -> Community
    levels: int  # 层次数量
    root_community_ids: list[str]  # 顶层社区 ID 列表

    def get_communities_at_level(self, level: int) -> list[Community]:
        """获取指定层级的所有社区。"""
        return [c for c in self.communities.values() if c.level == level]

    def get_children(self, community_id: str) -> list[Community]:
        """获取子社区。"""
        community = self.communities.get(community_id)
        if community is None:
            return []
        return [
            self.communities[cid]
            for cid in community.child_ids
            if cid in self.communities
        ]


class CommunityDetector(ABC):
    """社区检测器抽象基类。"""

    @abstractmethod
    def detect(
        self,
        nodes: list[CommunityNode],
        edges: list[CommunityEdge],
        resolution: float = 1.0,
    ) -> CommunityHierarchy:
        """执行社区检测。

        Args:
            nodes: 节点列表
            edges: 边列表
            resolution: 分辨率参数（影响社区粒度）

        Returns:
            社区层次结构
        """


class LouvainDetector(CommunityDetector):
    """Louvain 社区检测算法。"""

    def detect(
        self,
        nodes: list[CommunityNode],
        edges: list[CommunityEdge],
        resolution: float = 1.0,
    ) -> CommunityHierarchy:
        """使用 Louvain 算法检测社区。"""
        try:
            import networkx as nx
            from networkx.algorithms.community import louvain_communities
        except ImportError as e:
            raise ImportError("networkx 未安装。请运行: pip install networkx") from e

        # 构建 NetworkX 图
        graph = nx.Graph()
        for node in nodes:
            graph.add_node(
                node.node_id, **{"label": node.label, "type": node.node_type}
            )
        for edge in edges:
            graph.add_edge(
                edge.source_id,
                edge.target_id,
                weight=edge.weight,
                type=edge.relation_type,
            )

        if len(graph.nodes) == 0:
            return CommunityHierarchy(communities={}, levels=0, root_community_ids=[])

        # 执行 Louvain 社区检测
        communities_list = louvain_communities(graph, resolution=resolution, seed=42)

        # 构建社区结构
        node_map = {n.node_id: n for n in nodes}
        communities: dict[str, Community] = {}

        for idx, node_set in enumerate(communities_list):
            community_id = f"community_{idx}"
            community_nodes = [node_map[nid] for nid in node_set if nid in node_map]
            # 获取社区内部的边
            community_edges = [
                e for e in edges if e.source_id in node_set and e.target_id in node_set
            ]
            communities[community_id] = Community(
                community_id=community_id,
                level=0,
                nodes=community_nodes,
                edges=community_edges,
                key_entities=[n.label for n in community_nodes[:5]],
            )

        return CommunityHierarchy(
            communities=communities,
            levels=1,
            root_community_ids=list(communities.keys()),
        )


class CommunitySummarizer:
    """社区摘要生成器。"""

    def __init__(
        self,
        llm_call: Callable[[str, str], str],
        max_nodes_in_prompt: int = 20,
    ) -> None:
        """初始化摘要生成器。

        Args:
            llm_call: LLM 调用函数 (system, user) -> response
            max_nodes_in_prompt: prompt 中最大节点数
        """
        self._llm_call = llm_call
        self._max_nodes = max_nodes_in_prompt

    async def summarize_community(self, community: Community) -> str:
        """生成单个社区的摘要。"""
        # 构建节点描述
        nodes_desc = []
        for node in community.nodes[: self._max_nodes]:
            desc = f"- {node.label} ({node.node_type})"
            if node.properties:
                props = ", ".join(
                    f"{k}: {v}" for k, v in list(node.properties.items())[:3]
                )
                desc += f": {props}"
            nodes_desc.append(desc)

        # 构建关系描述
        edges_desc = []
        for edge in community.edges[: self._max_nodes]:
            source = next(
                (n.label for n in community.nodes if n.node_id == edge.source_id),
                edge.source_id,
            )
            target = next(
                (n.label for n in community.nodes if n.node_id == edge.target_id),
                edge.target_id,
            )
            edges_desc.append(f"- {source} --[{edge.relation_type}]--> {target}")

        prompt = f"""请为以下知识图谱社区生成一个简洁的摘要。

社区包含 {len(community.nodes)} 个实体和 {len(community.edges)} 个关系。

主要实体：
{chr(10).join(nodes_desc)}

主要关系：
{chr(10).join(edges_desc[:10])}

请生成：
1. 一段 2-3 句话的摘要，描述这个社区的主题和关键信息
2. 列出 3-5 个关键实体"""

        system = "你是一个知识图谱分析专家，擅长提取和总结图结构中的关键信息。"
        return self._llm_call(system, prompt)

    async def summarize_hierarchy(
        self,
        hierarchy: CommunityHierarchy,
    ) -> CommunityHierarchy:
        """为整个层次结构生成摘要。

        从最低层级开始，逐层向上生成摘要。
        """
        # 按层级排序（从低到高）
        for level in range(hierarchy.levels):
            communities = hierarchy.get_communities_at_level(level)
            for community in communities:
                if community.summary is None:
                    summary = await self.summarize_community(community)
                    community.summary = summary
        return hierarchy


class GraphRAGCommunityManager:
    """GraphRAG 社区管理器。

    整合社区检测和摘要生成。
    """

    def __init__(
        self,
        detector: CommunityDetector,
        summarizer: CommunitySummarizer | None = None,
    ) -> None:
        """初始化管理器。

        Args:
            detector: 社区检测器
            summarizer: 可选的摘要生成器
        """
        self._detector = detector
        self._summarizer = summarizer
        self._hierarchy: CommunityHierarchy | None = None

    def build_communities(
        self,
        nodes: list[CommunityNode],
        edges: list[CommunityEdge],
        resolution: float = 1.0,
    ) -> CommunityHierarchy:
        """构建社区结构。"""
        self._hierarchy = self._detector.detect(nodes, edges, resolution)
        return self._hierarchy

    async def generate_summaries(self) -> CommunityHierarchy:
        """生成社区摘要。"""
        if self._hierarchy is None:
            raise ValueError("请先调用 build_communities")
        if self._summarizer is None:
            raise ValueError("未配置摘要生成器")
        return await self._summarizer.summarize_hierarchy(self._hierarchy)

    def get_community_context(
        self,
        query: str,
        top_k: int = 3,
    ) -> list[Community]:
        """根据查询获取相关社区上下文。

        简单实现：基于关键词匹配。
        更完整的实现应使用向量相似度。
        """
        if self._hierarchy is None:
            return []

        query_lower = query.lower()
        scored_communities: list[tuple[Community, float]] = []

        for community in self._hierarchy.communities.values():
            score = 0.0
            # 检查实体标签
            for node in community.nodes:
                if query_lower in node.label.lower():
                    score += 1.0
            # 检查摘要
            if community.summary and query_lower in community.summary.lower():
                score += 0.5
            if score > 0:
                scored_communities.append((community, score))

        # 按分数排序
        scored_communities.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored_communities[:top_k]]
