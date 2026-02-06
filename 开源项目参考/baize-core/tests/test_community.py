"""GraphRAG 社区测试。"""

from __future__ import annotations

from baize_core.graph.community import (
    Community,
    CommunityEdge,
    CommunityHierarchy,
    CommunityNode,
    LouvainDetector,
)


class TestCommunityNode:
    """CommunityNode 测试。"""

    def test_create_node(self) -> None:
        """测试创建节点。"""
        node = CommunityNode(
            node_id="n1",
            label="测试节点",
            node_type="entity",
            properties={"key": "value"},
        )
        assert node.node_id == "n1"
        assert node.label == "测试节点"


class TestCommunity:
    """Community 测试。"""

    def test_size(self) -> None:
        """测试社区大小。"""
        nodes = [
            CommunityNode(node_id=f"n{i}", label=f"节点{i}", node_type="entity")
            for i in range(5)
        ]
        community = Community(
            community_id="c1",
            level=0,
            nodes=nodes,
            edges=[],
        )
        assert community.size == 5


class TestCommunityHierarchy:
    """CommunityHierarchy 测试。"""

    def test_get_communities_at_level(self) -> None:
        """测试获取指定层级社区。"""
        c1 = Community(community_id="c1", level=0, nodes=[], edges=[])
        c2 = Community(community_id="c2", level=0, nodes=[], edges=[])
        c3 = Community(community_id="c3", level=1, nodes=[], edges=[])
        hierarchy = CommunityHierarchy(
            communities={"c1": c1, "c2": c2, "c3": c3},
            levels=2,
            root_community_ids=["c3"],
        )
        level_0 = hierarchy.get_communities_at_level(0)
        assert len(level_0) == 2


class TestLouvainDetector:
    """Louvain 检测器测试。"""

    def test_detect_empty(self) -> None:
        """测试空图检测。"""
        detector = LouvainDetector()
        hierarchy = detector.detect([], [])
        assert hierarchy.levels == 0
        assert len(hierarchy.communities) == 0

    def test_detect_simple_graph(self) -> None:
        """测试简单图检测。"""
        nodes = [
            CommunityNode(node_id="a", label="A", node_type="entity"),
            CommunityNode(node_id="b", label="B", node_type="entity"),
            CommunityNode(node_id="c", label="C", node_type="entity"),
            CommunityNode(node_id="d", label="D", node_type="entity"),
        ]
        edges = [
            CommunityEdge(source_id="a", target_id="b", relation_type="related"),
            CommunityEdge(source_id="b", target_id="c", relation_type="related"),
            CommunityEdge(source_id="c", target_id="d", relation_type="related"),
        ]
        detector = LouvainDetector()
        hierarchy = detector.detect(nodes, edges)
        assert hierarchy.levels >= 1
        assert len(hierarchy.communities) >= 1
        # 所有节点都应该在某个社区中
        all_node_ids = set()
        for community in hierarchy.communities.values():
            all_node_ids.update(n.node_id for n in community.nodes)
        assert all_node_ids == {"a", "b", "c", "d"}
