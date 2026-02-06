# Author: msq
"""Neo4j graph store for AEGI entities, events, and relations."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Neo4jStore:
    """Neo4j graph store — adapted from baize-core for AEGI domain."""

    uri: str
    user: str
    password: str
    database: str = "neo4j"
    _driver: Any = field(default=None, repr=False)

    def _get_driver(self) -> Any:
        if self._driver is None:
            neo4j = importlib.import_module("neo4j")
            self._driver = neo4j.GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
        return self._driver

    async def connect(self) -> None:
        self._get_driver()

    async def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    async def ensure_indexes(self) -> None:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            for label, prop in [
                ("Entity", "uid"),
                ("Entity", "name"),
                ("Entity", "type"),
                ("Event", "uid"),
                ("Event", "type"),
                ("Assertion", "uid"),
                ("SourceClaim", "uid"),
            ]:
                s.run(
                    f"CREATE INDEX {label.lower()}_{prop}_idx IF NOT EXISTS "
                    f"FOR (n:{label}) ON (n.{prop})"
                )

    async def upsert_nodes(self, label: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            s.run(
                f"UNWIND $rows AS row MERGE (n:{label} {{uid: row.uid}}) SET n += row",
                rows=rows,
            )

    async def upsert_edges(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        edges: list[dict[str, Any]],
    ) -> None:
        if not edges:
            return
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            for e in edges:
                s.run(
                    f"MATCH (a:{source_label} {{uid: $src}}) "
                    f"MATCH (b:{target_label} {{uid: $tgt}}) "
                    f"MERGE (a)-[r:{rel_type}]->(b) "
                    f"SET r += $props",
                    src=e["source_uid"],
                    tgt=e["target_uid"],
                    props=e.get("properties", {}),
                )

    async def get_neighbors(
        self,
        node_uid: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (n {uid: $uid})-[r]-(m) "
                "RETURN m AS neighbor, type(r) AS rel_type, properties(r) AS props "
                "LIMIT $limit",
                uid=node_uid,
                limit=limit,
            )
            return [
                {
                    "neighbor": dict(rec["neighbor"]),
                    "rel_type": rec["rel_type"],
                    "props": rec["props"],
                }
                for rec in result
            ]

    async def find_path(
        self,
        source_uid: str,
        target_uid: str,
        *,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                f"MATCH path = shortestPath((a {{uid: $src}})-[*1..{max_depth}]-(b {{uid: $tgt}})) "
                "RETURN [n IN nodes(path) | properties(n)] AS nodes, "
                "[r IN relationships(path) | {{type: type(r), props: properties(r)}}] AS rels",
                src=source_uid,
                tgt=target_uid,
            )
            return [{"nodes": rec["nodes"], "rels": rec["rels"]} for rec in result]

    async def run_cypher(self, query: str, **params: Any) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(query, **params)
            return [dict(rec) for rec in result]

    async def count_nodes(self) -> dict[str, int]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            counts = {}
            for label in ("Entity", "Event", "Assertion", "SourceClaim"):
                r = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
                counts[label.lower()] = r["c"] if r else 0
            r = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()
            counts["relationships"] = r["c"] if r else 0
            return counts

    async def delete_all(self) -> None:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            s.run("MATCH (n) DETACH DELETE n")
