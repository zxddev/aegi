"""KG 可视化端点 API 集成测试 — 用 mock Neo4jStore。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from aegi_core.api.main import create_app
from aegi_core.infra.neo4j_store import Neo4jStore


# ---------------------------------------------------------------------------
# 假 Neo4jStore
# ---------------------------------------------------------------------------


class _FakeNeo4j:
    """API 级别测试用的最小 mock。"""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def ensure_indexes(self) -> None: ...

    async def get_subgraph(self, case_uid: str, *, limit: int = 5000) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "uid": "n1",
                    "name": "Node1",
                    "type": "Entity",
                    "labels": ["Entity"],
                    "props": {},
                },
                {
                    "uid": "n2",
                    "name": "Node2",
                    "type": "Event",
                    "labels": ["Event"],
                    "props": {},
                },
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "RELATED", "props": {}},
            ],
        }

    async def get_neighbors(
        self, node_uid: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        if node_uid == "n1":
            return [
                {
                    "neighbor": {"uid": "n2", "name": "Node2", "type": "Event"},
                    "rel_type": "RELATED",
                    "props": {},
                }
            ]
        return []

    async def get_isolated_nodes(
        self, case_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return [
            {
                "props": {"uid": "iso1", "name": "Isolated", "type": "Entity"},
                "labels": ["Entity"],
            }
        ]

    # PLACEHOLDER_MORE_METHODS

    async def get_relationship_stats(self, case_uid: str) -> list[dict[str, Any]]:
        return [{"rel_type": "RELATED", "count": 1}]

    async def get_temporal_events(
        self,
        case_uid: str,
        start_date=None,
        end_date=None,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return [
            {
                "uid": "ev1",
                "label": "Event1",
                "type": "military",
                "timestamp_ref": "2025-01-01",
            }
        ]

    async def get_entity_timeline(
        self, entity_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return []

    async def find_multi_hop_paths(
        self,
        source_uid: str,
        target_uid: str,
        *,
        max_depth: int = 5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return [
            {
                "nodes": [
                    {"uid": source_uid, "name": "Src", "type": "E"},
                    {"uid": target_uid, "name": "Tgt", "type": "E"},
                ],
                "rels": [
                    {
                        "type": "LINKED",
                        "source": source_uid,
                        "target": target_uid,
                        "props": {},
                    }
                ],
            }
        ]

    async def search_entities(self, keywords, case_uid, *, limit=10):
        return []

    async def find_path(self, src, tgt, *, max_depth=5):
        return []

    async def count_nodes(self):
        return {}


# ---------------------------------------------------------------------------
# 测试客户端 fixture
# ---------------------------------------------------------------------------

_fake_neo4j = _FakeNeo4j()


@pytest.fixture()
def client():
    from aegi_core.api.deps import get_neo4j_store

    fake_neo = _FakeNeo4j()
    app = create_app()
    app.dependency_overrides[get_neo4j_store] = lambda: fake_neo
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


def test_get_case_graph(client):
    resp = client.get("/cases/test_case/kg/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] == 2
    assert data["edge_count"] == 1
    assert len(data["nodes"]) == 2
    assert data["nodes"][0]["uid"] == "n1"


def test_get_entity_neighborhood(client):
    resp = client.get("/cases/test_case/kg/graph/entity/n1?hops=1&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_count"] >= 1


def test_get_communities(client):
    resp = client.get("/cases/test_case/kg/communities?algorithm=louvain&min_size=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "communities" in data
    assert "algorithm" in data
    assert data["algorithm"] == "louvain"


def test_get_centrality(client):
    resp = client.get("/cases/test_case/kg/centrality?algorithm=pagerank&top_k=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "rankings" in data
    assert data["algorithm"] == "pagerank"


def test_get_gaps(client):
    resp = client.get("/cases/test_case/kg/gaps")
    assert resp.status_code == 200
    data = resp.json()
    assert "isolated_nodes" in data
    assert len(data["isolated_nodes"]) == 1
    assert data["isolated_nodes"][0]["uid"] == "iso1"


def test_get_temporal(client):
    resp = client.get("/cases/test_case/kg/temporal")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_count"] == 1
    assert len(data["events"]) == 1


def test_find_paths(client):
    resp = client.post(
        "/cases/test_case/kg/paths",
        json={"source_uid": "n1", "target_uid": "n2", "max_depth": 3, "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path_count"] == 1
    assert data["source_uid"] == "n1"
    assert data["target_uid"] == "n2"
    assert len(data["paths"]) == 1
    assert data["paths"][0]["length"] == 1


def test_centrality_invalid_algorithm(client):
    resp = client.get("/cases/test_case/kg/centrality?algorithm=invalid")
    assert resp.status_code == 422


def test_communities_invalid_algorithm(client):
    resp = client.get("/cases/test_case/kg/communities?algorithm=invalid")
    assert resp.status_code == 422
