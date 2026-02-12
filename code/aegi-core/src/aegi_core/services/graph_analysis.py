"""图分析服务 — 社区发现、中心性、缺口分析、时序、路径。

从 Neo4j 提取子图 → 构建 networkx.Graph → 跑算法。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from aegi_core.infra.neo4j_store import Neo4jStore


# ---------------------------------------------------------------------------
# 结果数据类
# ---------------------------------------------------------------------------


@dataclass
class CommunityResult:
    communities: list[dict[str, Any]] = field(default_factory=list)
    algorithm: str = "louvain"
    modularity: float | None = None
    node_count: int = 0
    community_count: int = 0


@dataclass
class CentralityResult:
    rankings: list[dict[str, Any]] = field(default_factory=list)
    algorithm: str = "pagerank"


@dataclass
class GapAnalysisResult:
    isolated_nodes: list[dict[str, Any]] = field(default_factory=list)
    weakly_connected_components: int = 0
    largest_component_size: int = 0
    smallest_component_size: int = 0
    density: float = 0.0
    relationship_distribution: list[dict[str, Any]] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


# PLACEHOLDER_TEMPORAL


@dataclass
class TemporalAnalysisResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    entity_timelines: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    time_range: dict[str, str | None] = field(default_factory=dict)
    event_count: int = 0


@dataclass
class PathAnalysisResult:
    paths: list[dict[str, Any]] = field(default_factory=list)
    source_uid: str = ""
    target_uid: str = ""
    path_count: int = 0


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _build_nx_graph(subgraph_data: dict[str, Any]) -> nx.Graph:
    """从 Neo4j 子图数据构建 networkx Graph。"""
    G = nx.Graph()
    for node in subgraph_data.get("nodes", []):
        uid = node.get("uid", "")
        if not uid:
            continue
        G.add_node(
            uid,
            name=node.get("name", ""),
            type=node.get("type", ""),
            labels=node.get("labels", []),
            props=node.get("props", {}),
        )
    for edge in subgraph_data.get("edges", []):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src and tgt:
            G.add_edge(
                src, tgt, rel_type=edge.get("type", ""), props=edge.get("props", {})
            )
    return G


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


async def detect_communities(
    neo4j: Neo4jStore,
    case_uid: str,
    *,
    algorithm: str = "louvain",
    min_community_size: int = 2,
) -> CommunityResult:
    subgraph_data = await neo4j.get_subgraph(case_uid)
    G = _build_nx_graph(subgraph_data)

    if G.number_of_nodes() == 0:
        return CommunityResult(algorithm=algorithm)

    if algorithm == "label_propagation":
        raw_communities = list(nx.community.label_propagation_communities(G))
        modularity = None
    else:
        raw_communities = list(nx.community.louvain_communities(G, seed=42))
        try:
            modularity = nx.community.modularity(G, raw_communities)
        except (ZeroDivisionError, nx.NetworkXError):
            modularity = None

    communities = []
    for i, comm in enumerate(raw_communities):
        if len(comm) < min_community_size:
            continue
        nodes = []
        for uid in comm:
            data = G.nodes[uid]
            nodes.append(
                {
                    "uid": uid,
                    "name": data.get("name", ""),
                    "type": data.get("type", ""),
                    "labels": data.get("labels", []),
                }
            )
        communities.append(
            {
                "community_id": i,
                "nodes": nodes,
                "size": len(nodes),
            }
        )

    return CommunityResult(
        communities=communities,
        algorithm=algorithm,
        modularity=modularity,
        node_count=G.number_of_nodes(),
        community_count=len(communities),
    )


async def compute_centrality(
    neo4j: Neo4jStore,
    case_uid: str,
    *,
    algorithm: str = "pagerank",
    top_k: int = 20,
) -> CentralityResult:
    subgraph_data = await neo4j.get_subgraph(case_uid)
    G = _build_nx_graph(subgraph_data)

    if G.number_of_nodes() == 0:
        return CentralityResult(algorithm=algorithm)

    if algorithm == "betweenness":
        scores = nx.betweenness_centrality(G)
    elif algorithm == "degree":
        scores = nx.degree_centrality(G)
    else:
        scores = nx.pagerank(G)

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    rankings = []
    for uid, score in sorted_scores:
        data = G.nodes[uid]
        rankings.append(
            {
                "uid": uid,
                "name": data.get("name", ""),
                "type": data.get("type", ""),
                "score": round(score, 6),
            }
        )

    return CentralityResult(rankings=rankings, algorithm=algorithm)


async def analyze_gaps(neo4j: Neo4jStore, case_uid: str) -> GapAnalysisResult:
    subgraph_data = await neo4j.get_subgraph(case_uid)
    G = _build_nx_graph(subgraph_data)
    isolated_raw = await neo4j.get_isolated_nodes(case_uid)
    rel_stats = await neo4j.get_relationship_stats(case_uid)

    isolated_nodes = []
    for item in isolated_raw:
        props = item.get("props", {})
        isolated_nodes.append(
            {
                "uid": props.get("uid", ""),
                "name": props.get("name", props.get("label", "")),
                "type": props.get("type", ""),
                "labels": item.get("labels", []),
            }
        )

    components = list(nx.connected_components(G)) if G.number_of_nodes() > 0 else []
    comp_sizes = [len(c) for c in components]

    return GapAnalysisResult(
        isolated_nodes=isolated_nodes,
        weakly_connected_components=len(components),
        largest_component_size=max(comp_sizes, default=0),
        smallest_component_size=min(comp_sizes, default=0),
        density=nx.density(G) if G.number_of_nodes() > 0 else 0.0,
        relationship_distribution=rel_stats,
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
    )


async def analyze_temporal(
    neo4j: Neo4jStore,
    case_uid: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    entity_uids: list[str] | None = None,
) -> TemporalAnalysisResult:
    events = await neo4j.get_temporal_events(case_uid, start_date, end_date)

    entity_timelines: dict[str, list[dict[str, Any]]] = {}
    if entity_uids:
        for uid in entity_uids:
            timeline = await neo4j.get_entity_timeline(uid)
            entity_timelines[uid] = timeline

    return TemporalAnalysisResult(
        events=events,
        entity_timelines=entity_timelines,
        time_range={"start": start_date, "end": end_date},
        event_count=len(events),
    )


async def find_paths(
    neo4j: Neo4jStore,
    source_uid: str,
    target_uid: str,
    *,
    max_depth: int = 5,
    limit: int = 10,
) -> PathAnalysisResult:
    raw_paths = await neo4j.find_multi_hop_paths(
        source_uid,
        target_uid,
        max_depth=max_depth,
        limit=limit,
    )
    return PathAnalysisResult(
        paths=raw_paths,
        source_uid=source_uid,
        target_uid=target_uid,
        path_count=len(raw_paths),
    )
