# Author: msq
"""Neo4j graph store for AEGI entities, events, and relations."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import anyio


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

    async def _run_sync(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """将同步 Neo4j 操作放到线程池执行，避免阻塞事件循环。"""
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))

    async def connect(self) -> None:
        await self._run_sync(self._get_driver)

    async def close(self) -> None:
        if self._driver is not None:
            await self._run_sync(self._driver.close)
            self._driver = None

    def _sync_ensure_indexes(self) -> None:
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

    async def ensure_indexes(self) -> None:
        await self._run_sync(self._sync_ensure_indexes)

    def _sync_upsert_nodes(self, label: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            s.run(
                f"UNWIND $rows AS row MERGE (n:{label} {{uid: row.uid}}) SET n += row",
                rows=rows,
            )

    async def upsert_nodes(self, label: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        await self._run_sync(self._sync_upsert_nodes, label, rows)

    def _sync_upsert_edges(
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

    async def upsert_edges(
        self,
        source_label: str,
        target_label: str,
        rel_type: str,
        edges: list[dict[str, Any]],
    ) -> None:
        if not edges:
            return
        await self._run_sync(
            self._sync_upsert_edges,
            source_label,
            target_label,
            rel_type,
            edges,
        )

    def _sync_get_neighbors(self, node_uid: str, limit: int) -> list[dict[str, Any]]:
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

    async def get_neighbors(
        self,
        node_uid: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._run_sync(self._sync_get_neighbors, node_uid, limit)

    def _sync_find_path(
        self,
        source_uid: str,
        target_uid: str,
        max_depth: int,
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                f"MATCH path = shortestPath((a {{uid: $src}})-[*1..{max_depth}]-(b {{uid: $tgt}})) "
                "RETURN [n IN nodes(path) | properties(n)] AS nodes, "
                "[r IN relationships(path) | {type: type(r), props: properties(r)}] AS rels",
                src=source_uid,
                tgt=target_uid,
            )
            return [{"nodes": rec["nodes"], "rels": rec["rels"]} for rec in result]

    async def find_path(
        self,
        source_uid: str,
        target_uid: str,
        *,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        return await self._run_sync(
            self._sync_find_path,
            source_uid,
            target_uid,
            max_depth,
        )

    def _sync_run_cypher(self, query: str, params: dict) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(query, **params)
            return [dict(rec) for rec in result]

    async def run_cypher(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return await self._run_sync(self._sync_run_cypher, query, params)

    def _sync_count_nodes(self) -> dict[str, int]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            counts = {}
            for label in ("Entity", "Event", "Assertion", "SourceClaim"):
                r = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
                counts[label.lower()] = r["c"] if r else 0
            r = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()
            counts["relationships"] = r["c"] if r else 0
            return counts

    async def count_nodes(self) -> dict[str, int]:
        return await self._run_sync(self._sync_count_nodes)

    def _sync_delete_all(self) -> None:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            s.run("MATCH (n) DETACH DELETE n")

    async def delete_all(self) -> None:
        await self._run_sync(self._sync_delete_all)
