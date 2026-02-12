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

    def _sync_search_entities(
        self, keywords: list[str], case_uid: str, limit: int
    ) -> list[dict[str, Any]]:
        """按关键词模糊搜索实体，返回实体属性列表。"""
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            # 用 OR 拼接多个关键词的 CONTAINS 条件
            where_clauses = " OR ".join(
                f"toLower(n.name) CONTAINS $kw{i}" for i in range(len(keywords))
            )
            params: dict[str, Any] = {
                f"kw{i}": kw.lower() for i, kw in enumerate(keywords)
            }
            params["case_uid"] = case_uid
            params["limit"] = limit
            result = s.run(
                f"MATCH (n:Entity {{case_uid: $case_uid}}) "
                f"WHERE {where_clauses} "
                f"RETURN properties(n) AS props LIMIT $limit",
                **params,
            )
            return [dict(rec["props"]) for rec in result]

    async def search_entities(
        self,
        keywords: list[str],
        case_uid: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """按关键词模糊搜索 case 内实体。"""
        if not keywords:
            return []
        return await self._run_sync(
            self._sync_search_entities, keywords, case_uid, limit
        )

    # -- Phase 3: KG analysis methods -------------------------------------------

    def _sync_get_subgraph(self, case_uid: str, limit: int) -> dict[str, Any]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (n {case_uid: $case_uid}) "
                "OPTIONAL MATCH (n)-[r]-(m {case_uid: $case_uid}) "
                "WITH collect(DISTINCT n) + collect(DISTINCT m) AS all_nodes, "
                "     collect(DISTINCT r) AS all_rels "
                "UNWIND all_nodes AS node "
                "WITH collect(DISTINCT {uid: node.uid, name: coalesce(node.name, node.label, ''), "
                "     type: coalesce(node.type, ''), labels: labels(node), "
                "     props: properties(node)})[..$limit] AS nodes, all_rels "
                "UNWIND all_rels AS rel "
                "WITH nodes, collect(DISTINCT CASE WHEN rel IS NOT NULL THEN "
                "     {source: startNode(rel).uid, target: endNode(rel).uid, "
                "      type: type(rel), props: properties(rel)} END) AS edges "
                "RETURN nodes, [e IN edges WHERE e IS NOT NULL] AS edges",
                case_uid=case_uid,
                limit=limit,
            )
            rec = result.single()
            if rec is None:
                return {"nodes": [], "edges": []}
            return {"nodes": rec["nodes"] or [], "edges": rec["edges"] or []}

    async def get_subgraph(self, case_uid: str, *, limit: int = 5000) -> dict[str, Any]:
        return await self._run_sync(self._sync_get_subgraph, case_uid, limit)

    def _sync_get_temporal_events(
        self, case_uid: str, start_date: str | None, end_date: str | None, limit: int
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            query = "MATCH (e:Event {case_uid: $case_uid}) WHERE e.timestamp_ref IS NOT NULL"
            params: dict[str, Any] = {"case_uid": case_uid, "limit": limit}
            if start_date:
                query += " AND e.timestamp_ref >= $start"
                params["start"] = start_date
            if end_date:
                query += " AND e.timestamp_ref <= $end"
                params["end"] = end_date
            query += (
                " RETURN properties(e) AS props ORDER BY e.timestamp_ref LIMIT $limit"
            )
            result = s.run(query, **params)
            return [dict(rec["props"]) for rec in result]

    async def get_temporal_events(
        self,
        case_uid: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return await self._run_sync(
            self._sync_get_temporal_events, case_uid, start_date, end_date, limit
        )

    def _sync_find_multi_hop_paths(
        self,
        source_uid: str,
        target_uid: str,
        max_depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                f"MATCH path = (a {{uid: $src}})-[*1..{max_depth}]-(b {{uid: $tgt}}) "
                "RETURN [n IN nodes(path) | {uid: n.uid, name: coalesce(n.name, n.label, ''), "
                "        type: coalesce(n.type, ''), labels: labels(n)}] AS nodes, "
                "       [r IN relationships(path) | {type: type(r), source: startNode(r).uid, "
                "        target: endNode(r).uid, props: properties(r)}] AS rels "
                "LIMIT $limit",
                src=source_uid,
                tgt=target_uid,
                limit=limit,
            )
            return [{"nodes": rec["nodes"], "rels": rec["rels"]} for rec in result]

    async def find_multi_hop_paths(
        self,
        source_uid: str,
        target_uid: str,
        *,
        max_depth: int = 5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return await self._run_sync(
            self._sync_find_multi_hop_paths, source_uid, target_uid, max_depth, limit
        )

    def _sync_get_isolated_nodes(
        self, case_uid: str, limit: int
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (n {case_uid: $case_uid}) WHERE NOT (n)--() "
                "RETURN properties(n) AS props, labels(n) AS labels LIMIT $limit",
                case_uid=case_uid,
                limit=limit,
            )
            return [
                {"props": dict(rec["props"]), "labels": list(rec["labels"])}
                for rec in result
            ]

    async def get_isolated_nodes(
        self, case_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self._run_sync(self._sync_get_isolated_nodes, case_uid, limit)

    def _sync_get_entity_timeline(
        self, entity_uid: str, limit: int
    ) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (e {uid: $uid})-[r]-(ev:Event) "
                "WHERE ev.timestamp_ref IS NOT NULL "
                "RETURN properties(ev) AS event, type(r) AS rel_type, properties(r) AS rel_props "
                "ORDER BY ev.timestamp_ref LIMIT $limit",
                uid=entity_uid,
                limit=limit,
            )
            return [
                {
                    "event": dict(rec["event"]),
                    "rel_type": rec["rel_type"],
                    "rel_props": dict(rec["rel_props"]),
                }
                for rec in result
            ]

    async def get_entity_timeline(
        self, entity_uid: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        return await self._run_sync(self._sync_get_entity_timeline, entity_uid, limit)

    def _sync_get_relationship_stats(self, case_uid: str) -> list[dict[str, Any]]:
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (n {case_uid: $case_uid})-[r]->(m {case_uid: $case_uid}) "
                "RETURN type(r) AS rel_type, count(r) AS count ORDER BY count DESC",
                case_uid=case_uid,
            )
            return [
                {"rel_type": rec["rel_type"], "count": rec["count"]} for rec in result
            ]

    async def get_relationship_stats(self, case_uid: str) -> list[dict[str, Any]]:
        return await self._run_sync(self._sync_get_relationship_stats, case_uid)

    def _sync_get_all_triples(self, case_uid: str) -> list[tuple[str, str, str]]:
        """提取 case 下所有三元组 (head_uid, relation_type, tail_uid)。"""
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (h {case_uid: $case_uid})-[r]->(t {case_uid: $case_uid}) "
                "RETURN h.uid AS head, type(r) AS relation, t.uid AS tail",
                case_uid=case_uid,
            )
            triples: list[tuple[str, str, str]] = []
            for rec in result:
                head = rec["head"]
                relation = rec["relation"]
                tail = rec["tail"]
                if head and relation and tail:
                    triples.append((str(head), str(relation), str(tail)))
            return triples

    async def get_all_triples(self, case_uid: str) -> list[tuple[str, str, str]]:
        return await self._run_sync(self._sync_get_all_triples, case_uid)

    def _sync_get_entity_names(self, case_uid: str) -> dict[str, str]:
        """获取 case 内实体名称映射。"""
        driver = self._get_driver()
        with driver.session(database=self.database) as s:
            result = s.run(
                "MATCH (n {case_uid: $case_uid}) "
                "RETURN n.uid AS uid, coalesce(n.name, n.label, n.uid) AS name",
                case_uid=case_uid,
            )
            mapping: dict[str, str] = {}
            for rec in result:
                uid = rec["uid"]
                if not uid:
                    continue
                mapping[str(uid)] = str(rec["name"] or uid)
            return mapping

    async def get_entity_names(self, case_uid: str) -> dict[str, str]:
        return await self._run_sync(self._sync_get_entity_names, case_uid)
