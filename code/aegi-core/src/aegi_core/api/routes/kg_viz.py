"""KG visualization & analysis API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from aegi_core.api.deps import get_neo4j_store
from aegi_core.contracts.schemas import (
    CentralityRankingV1,
    CentralityResponse,
    CommunityResponse,
    CommunityV1,
    GapAnalysisResponse,
    GraphDataResponse,
    GraphEdgeV1,
    GraphNodeV1,
    PathRequest,
    PathResponse,
    PathV1,
    PathNodeV1,
    PathRelV1,
    TemporalEventV1,
    TemporalResponse,
)
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services import graph_analysis

router = APIRouter(tags=["kg-viz"])


@router.get("/cases/{case_uid}/kg/graph")
async def get_case_graph(
    case_uid: str,
    limit: int = Query(5000, ge=1, le=10000),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> GraphDataResponse:
    data = await neo4j.get_subgraph(case_uid, limit=limit)
    nodes = [
        GraphNodeV1(
            uid=n.get("uid", ""),
            name=n.get("name", ""),
            type=n.get("type", ""),
            labels=n.get("labels", []),
            properties=n.get("props", {}),
        )
        for n in data.get("nodes", [])
    ]
    edges = [
        GraphEdgeV1(
            source_uid=e.get("source", ""),
            target_uid=e.get("target", ""),
            rel_type=e.get("type", ""),
            properties=e.get("props", {}),
        )
        for e in data.get("edges", [])
    ]
    return GraphDataResponse(
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


@router.get("/cases/{case_uid}/kg/graph/entity/{entity_uid}")
async def get_entity_neighborhood(
    case_uid: str,
    entity_uid: str,
    hops: int = Query(2, ge=1, le=4),
    limit: int = Query(50, ge=1, le=200),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> GraphDataResponse:
    """Get N-hop neighborhood subgraph for a specific entity."""
    seen_nodes: dict[str, GraphNodeV1] = {}
    seen_edges: list[GraphEdgeV1] = []
    frontier = [entity_uid]

    for _hop in range(hops):
        next_frontier: list[str] = []
        for uid in frontier:
            if uid in seen_nodes and _hop > 0:
                continue
            neighbors = await neo4j.get_neighbors(uid, limit=limit)
            for nb in neighbors:
                nb_data = nb["neighbor"]
                nb_uid = nb_data.get("uid", "")
                if not nb_uid:
                    continue
                if nb_uid not in seen_nodes:
                    seen_nodes[nb_uid] = GraphNodeV1(
                        uid=nb_uid,
                        name=nb_data.get("name", nb_data.get("label", "")),
                        type=nb_data.get("type", ""),
                    )
                    next_frontier.append(nb_uid)
                seen_edges.append(
                    GraphEdgeV1(
                        source_uid=uid,
                        target_uid=nb_uid,
                        rel_type=nb["rel_type"],
                        properties=nb.get("props", {}),
                    )
                )
            if uid not in seen_nodes:
                seen_nodes[uid] = GraphNodeV1(uid=uid, name="", type="")
        frontier = next_frontier

    nodes = list(seen_nodes.values())
    return GraphDataResponse(
        nodes=nodes,
        edges=seen_edges,
        node_count=len(nodes),
        edge_count=len(seen_edges),
    )


@router.get("/cases/{case_uid}/kg/communities")
async def get_communities(
    case_uid: str,
    algorithm: str = Query("louvain", pattern="^(louvain|label_propagation)$"),
    min_size: int = Query(2, ge=1),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> CommunityResponse:
    result = await graph_analysis.detect_communities(
        neo4j,
        case_uid,
        algorithm=algorithm,
        min_community_size=min_size,
    )
    communities = [
        CommunityV1(
            community_id=c["community_id"],
            nodes=[
                GraphNodeV1(
                    uid=n["uid"],
                    name=n["name"],
                    type=n["type"],
                    labels=n.get("labels", []),
                )
                for n in c["nodes"]
            ],
            size=c["size"],
        )
        for c in result.communities
    ]
    return CommunityResponse(
        communities=communities,
        algorithm=result.algorithm,
        modularity=result.modularity,
        community_count=result.community_count,
    )


@router.get("/cases/{case_uid}/kg/centrality")
async def get_centrality(
    case_uid: str,
    algorithm: str = Query("pagerank", pattern="^(pagerank|betweenness|degree)$"),
    top_k: int = Query(20, ge=1, le=100),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> CentralityResponse:
    result = await graph_analysis.compute_centrality(
        neo4j,
        case_uid,
        algorithm=algorithm,
        top_k=top_k,
    )
    rankings = [
        CentralityRankingV1(
            uid=r["uid"], name=r["name"], type=r["type"], score=r["score"]
        )
        for r in result.rankings
    ]
    return CentralityResponse(rankings=rankings, algorithm=result.algorithm)


@router.get("/cases/{case_uid}/kg/gaps")
async def get_gaps(
    case_uid: str,
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> GapAnalysisResponse:
    result = await graph_analysis.analyze_gaps(neo4j, case_uid)
    isolated = [
        GraphNodeV1(
            uid=n["uid"], name=n["name"], type=n["type"], labels=n.get("labels", [])
        )
        for n in result.isolated_nodes
    ]
    return GapAnalysisResponse(
        isolated_nodes=isolated,
        weakly_connected_components=result.weakly_connected_components,
        largest_component_size=result.largest_component_size,
        density=result.density,
        relationship_type_distribution=result.relationship_distribution,
        node_count=result.node_count,
        edge_count=result.edge_count,
    )


@router.get("/cases/{case_uid}/kg/temporal")
async def get_temporal(
    case_uid: str,
    start_date: str | None = None,
    end_date: str | None = None,
    entity_uids: str | None = Query(None, description="Comma-separated entity UIDs"),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> TemporalResponse:
    uids = (
        [u.strip() for u in entity_uids.split(",") if u.strip()]
        if entity_uids
        else None
    )
    result = await graph_analysis.analyze_temporal(
        neo4j,
        case_uid,
        start_date=start_date,
        end_date=end_date,
        entity_uids=uids,
    )
    events = [
        TemporalEventV1(
            uid=e.get("uid", ""),
            label=e.get("label", ""),
            event_type=e.get("type", ""),
            timestamp_ref=e.get("timestamp_ref"),
        )
        for e in result.events
    ]
    entity_timelines: dict[str, list[TemporalEventV1]] = {}
    for uid, timeline in result.entity_timelines.items():
        entity_timelines[uid] = [
            TemporalEventV1(
                uid=t["event"].get("uid", ""),
                label=t["event"].get("label", ""),
                event_type=t["event"].get("type", ""),
                timestamp_ref=t["event"].get("timestamp_ref"),
                related_entity_uid=uid,
                rel_type=t.get("rel_type"),
            )
            for t in timeline
        ]
    return TemporalResponse(
        events=events,
        entity_timelines=entity_timelines,
        time_range=result.time_range,
        event_count=result.event_count,
    )


@router.post("/cases/{case_uid}/kg/paths")
async def find_paths(
    case_uid: str,
    body: PathRequest,
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> PathResponse:
    result = await graph_analysis.find_paths(
        neo4j,
        body.source_uid,
        body.target_uid,
        max_depth=body.max_depth,
        limit=body.limit,
    )
    paths = []
    for p in result.paths:
        nodes = [
            PathNodeV1(
                uid=n.get("uid", ""), name=n.get("name", ""), type=n.get("type", "")
            )
            for n in p.get("nodes", [])
        ]
        rels = [
            PathRelV1(
                source_uid=r.get("source", ""),
                target_uid=r.get("target", ""),
                rel_type=r.get("type", ""),
            )
            for r in p.get("rels", [])
        ]
        paths.append(PathV1(nodes=nodes, rels=rels, length=len(rels)))
    return PathResponse(
        paths=paths,
        source_uid=body.source_uid,
        target_uid=body.target_uid,
        path_count=len(paths),
    )
