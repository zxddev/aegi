"""graph_analysis 服务单元测试 — 不需要 Neo4j。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from aegi_core.services.graph_analysis import (
    CommunityResult,
    CentralityResult,
    GapAnalysisResult,
    TemporalAnalysisResult,
    PathAnalysisResult,
    _build_nx_graph,
    detect_communities,
    compute_centrality,
    analyze_gaps,
    analyze_temporal,
    find_paths,
)


# ---------------------------------------------------------------------------
# 测试用假 Neo4jStore
# ---------------------------------------------------------------------------


class FakeNeo4jStore:
    """返回预设子图数据的 Mock Neo4jStore。"""

    def __init__(
        self,
        subgraph: dict[str, Any] | None = None,
        isolated: list[dict[str, Any]] | None = None,
        rel_stats: list[dict[str, Any]] | None = None,
        temporal_events: list[dict[str, Any]] | None = None,
        entity_timeline: list[dict[str, Any]] | None = None,
        multi_hop_paths: list[dict[str, Any]] | None = None,
    ):
        self._subgraph = subgraph or {"nodes": [], "edges": []}
        self._isolated = isolated or []
        self._rel_stats = rel_stats or []
        self._temporal_events = temporal_events or []
        self._entity_timeline = entity_timeline or []
        self._multi_hop_paths = multi_hop_paths or []

    # PLACEHOLDER_FAKE_METHODS

    async def get_subgraph(self, case_uid: str, *, limit: int = 5000) -> dict[str, Any]:
        return self._subgraph

    async def get_isolated_nodes(
        self, case_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self._isolated

    async def get_relationship_stats(self, case_uid: str) -> list[dict[str, Any]]:
        return self._rel_stats

    async def get_temporal_events(
        self,
        case_uid: str,
        start_date=None,
        end_date=None,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self._temporal_events

    async def get_entity_timeline(
        self, entity_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self._entity_timeline

    async def find_multi_hop_paths(
        self,
        source_uid: str,
        target_uid: str,
        *,
        max_depth: int = 5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._multi_hop_paths


# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------


def _triangle_subgraph() -> dict[str, Any]:
    """简单三角形: A--B--C--A。"""
    return {
        "nodes": [
            {
                "uid": "a",
                "name": "Alpha",
                "type": "Entity",
                "labels": ["Entity"],
                "props": {},
            },
            {
                "uid": "b",
                "name": "Beta",
                "type": "Entity",
                "labels": ["Entity"],
                "props": {},
            },
            {
                "uid": "c",
                "name": "Gamma",
                "type": "Entity",
                "labels": ["Entity"],
                "props": {},
            },
        ],
        "edges": [
            {"source": "a", "target": "b", "type": "ALLIED_WITH", "props": {}},
            {"source": "b", "target": "c", "type": "LOCATED_IN", "props": {}},
            {"source": "c", "target": "a", "type": "COOPERATES", "props": {}},
        ],
    }


def _star_subgraph() -> dict[str, Any]:
    """星形图: 中心节点连接 4 个叶子。"""
    nodes = [
        {
            "uid": "center",
            "name": "Hub",
            "type": "Entity",
            "labels": ["Entity"],
            "props": {},
        }
    ]
    edges = []
    for i in range(4):
        uid = f"leaf{i}"
        nodes.append(
            {
                "uid": uid,
                "name": f"Leaf{i}",
                "type": "Entity",
                "labels": ["Entity"],
                "props": {},
            }
        )
        edges.append(
            {"source": "center", "target": uid, "type": "CONNECTS", "props": {}}
        )
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# 测试: _build_nx_graph
# ---------------------------------------------------------------------------


def test_build_nx_graph_triangle():
    G = _build_nx_graph(_triangle_subgraph())
    assert G.number_of_nodes() == 3
    assert G.number_of_edges() == 3


def test_build_nx_graph_empty():
    G = _build_nx_graph({"nodes": [], "edges": []})
    assert G.number_of_nodes() == 0
    assert G.number_of_edges() == 0


# ---------------------------------------------------------------------------
# 测试: 社区检测
# ---------------------------------------------------------------------------


async def test_community_detection_louvain():
    neo = FakeNeo4jStore(subgraph=_star_subgraph())
    result = await detect_communities(
        neo, "case1", algorithm="louvain", min_community_size=1
    )
    assert isinstance(result, CommunityResult)
    assert result.algorithm == "louvain"
    assert result.node_count == 5
    assert result.community_count >= 1


async def test_community_detection_label_propagation():
    neo = FakeNeo4jStore(subgraph=_star_subgraph())
    result = await detect_communities(
        neo, "case1", algorithm="label_propagation", min_community_size=1
    )
    assert isinstance(result, CommunityResult)
    assert result.algorithm == "label_propagation"
    assert result.modularity is None  # LP 不计算 modularity


async def test_community_detection_min_size_filter():
    neo = FakeNeo4jStore(subgraph=_triangle_subgraph())
    result = await detect_communities(neo, "case1", min_community_size=10)
    assert result.community_count == 0


# ---------------------------------------------------------------------------
# 测试: 中心性
# ---------------------------------------------------------------------------


async def test_centrality_pagerank():
    neo = FakeNeo4jStore(subgraph=_star_subgraph())
    result = await compute_centrality(neo, "case1", algorithm="pagerank", top_k=3)
    assert isinstance(result, CentralityResult)
    assert result.algorithm == "pagerank"
    assert len(result.rankings) <= 3
    # Hub 节点中心性应最高
    assert result.rankings[0]["uid"] == "center"


async def test_centrality_betweenness():
    neo = FakeNeo4jStore(subgraph=_star_subgraph())
    result = await compute_centrality(neo, "case1", algorithm="betweenness", top_k=5)
    assert result.algorithm == "betweenness"
    assert result.rankings[0]["uid"] == "center"


async def test_centrality_degree():
    neo = FakeNeo4jStore(subgraph=_star_subgraph())
    result = await compute_centrality(neo, "case1", algorithm="degree", top_k=5)
    assert result.algorithm == "degree"
    assert result.rankings[0]["uid"] == "center"
    assert result.rankings[0]["score"] == 1.0  # 连接了所有其他节点


# ---------------------------------------------------------------------------
# 测试: 缺口分析
# ---------------------------------------------------------------------------


async def test_gap_analysis_isolated_nodes():
    isolated = [
        {
            "props": {"uid": "iso1", "name": "Isolated1", "type": "Entity"},
            "labels": ["Entity"],
        },
    ]
    neo = FakeNeo4jStore(
        subgraph=_triangle_subgraph(),
        isolated=isolated,
        rel_stats=[{"rel_type": "ALLIED_WITH", "count": 1}],
    )
    result = await analyze_gaps(neo, "case1")
    assert isinstance(result, GapAnalysisResult)
    assert len(result.isolated_nodes) == 1
    assert result.isolated_nodes[0]["uid"] == "iso1"


async def test_gap_analysis_components():
    neo = FakeNeo4jStore(subgraph=_triangle_subgraph(), rel_stats=[])
    result = await analyze_gaps(neo, "case1")
    assert result.weakly_connected_components == 1
    assert result.largest_component_size == 3


async def test_gap_analysis_density():
    neo = FakeNeo4jStore(subgraph=_triangle_subgraph(), rel_stats=[])
    result = await analyze_gaps(neo, "case1")
    assert result.density == 1.0  # 完全图 K3


# ---------------------------------------------------------------------------
# 测试: 空图 / 单节点边界情况
# ---------------------------------------------------------------------------


async def test_empty_graph():
    neo = FakeNeo4jStore()
    comm = await detect_communities(neo, "case1")
    assert comm.node_count == 0
    assert comm.community_count == 0

    cent = await compute_centrality(neo, "case1")
    assert len(cent.rankings) == 0

    gaps = await analyze_gaps(neo, "case1")
    assert gaps.node_count == 0
    assert gaps.density == 0.0


async def test_single_node_graph():
    subgraph = {
        "nodes": [
            {
                "uid": "solo",
                "name": "Solo",
                "type": "Entity",
                "labels": ["Entity"],
                "props": {},
            }
        ],
        "edges": [],
    }
    neo = FakeNeo4jStore(subgraph=subgraph)
    comm = await detect_communities(neo, "case1", min_community_size=1)
    assert comm.node_count == 1

    cent = await compute_centrality(neo, "case1")
    assert len(cent.rankings) == 1

    gaps = await analyze_gaps(neo, "case1")
    assert gaps.weakly_connected_components == 1
    assert gaps.density == 0.0


# ---------------------------------------------------------------------------
# 测试: 时序分析
# ---------------------------------------------------------------------------


async def test_temporal_analysis():
    events = [
        {
            "uid": "ev1",
            "label": "Event1",
            "type": "military",
            "timestamp_ref": "2025-01-01",
        },
        {
            "uid": "ev2",
            "label": "Event2",
            "type": "diplomatic",
            "timestamp_ref": "2025-02-01",
        },
    ]
    neo = FakeNeo4jStore(temporal_events=events)
    result = await analyze_temporal(neo, "case1")
    assert isinstance(result, TemporalAnalysisResult)
    assert result.event_count == 2


async def test_temporal_with_entity_timeline():
    timeline = [
        {
            "event": {
                "uid": "ev1",
                "label": "Ev1",
                "type": "mil",
                "timestamp_ref": "2025-01",
            },
            "rel_type": "PARTICIPATED_IN",
            "rel_props": {},
        },
    ]
    neo = FakeNeo4jStore(entity_timeline=timeline)
    result = await analyze_temporal(neo, "case1", entity_uids=["ent1"])
    assert "ent1" in result.entity_timelines
    assert len(result.entity_timelines["ent1"]) == 1


# ---------------------------------------------------------------------------
# 测试: 路径查找
# ---------------------------------------------------------------------------


async def test_find_paths():
    paths = [
        {
            "nodes": [
                {"uid": "a", "name": "A", "type": "E"},
                {"uid": "b", "name": "B", "type": "E"},
            ],
            "rels": [{"type": "LINKED", "source": "a", "target": "b", "props": {}}],
        }
    ]
    neo = FakeNeo4jStore(multi_hop_paths=paths)
    result = await find_paths(neo, "a", "b")
    assert isinstance(result, PathAnalysisResult)
    assert result.path_count == 1
    assert result.source_uid == "a"
    assert result.target_uid == "b"


async def test_find_paths_empty():
    neo = FakeNeo4jStore()
    result = await find_paths(neo, "x", "y")
    assert result.path_count == 0
