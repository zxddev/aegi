"""Neo4j 存储封装。

实现实体、事件、关系的存储与查询，支持：
- 实体/事件节点存储
- 实体间关系边存储
- Cypher 查询（路径查询、邻居查询、社区查询）
- 图索引管理
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from baize_core.schemas.entity_event import Entity, Event


class RelationType(str, Enum):
    """关系类型。"""

    # 实体间关系
    BELONGS_TO = "BELONGS_TO"  # 隶属关系（Unit→Organization）
    LOCATED_AT = "LOCATED_AT"  # 位置关系（Unit→Facility, Entity→Geography）
    OPERATES = "OPERATES"  # 运用关系（Unit→Equipment）
    ALLIED_WITH = "ALLIED_WITH"  # 同盟关系（Actor→Actor）
    HOSTILE_TO = "HOSTILE_TO"  # 敌对关系（Actor→Actor）
    COOPERATES_WITH = "COOPERATES_WITH"  # 合作关系（Organization→Organization）
    PARTICIPATES_IN = "PARTICIPATES_IN"  # 参与关系（Entity→Event）
    CAUSED_BY = "CAUSED_BY"  # 因果关系（Event→Event）
    FOLLOWS = "FOLLOWS"  # 时序关系（Event→Event）
    RELATED_TO = "RELATED_TO"  # 通用关联


class Relation(BaseModel):
    """实体间关系。"""

    relation_uid: str = Field(description="关系唯一标识")
    relation_type: RelationType = Field(description="关系类型")
    source_uid: str = Field(description="源节点 UID")
    target_uid: str = Field(description="目标节点 UID")
    properties: dict[str, Any] = Field(default_factory=dict, description="关系属性")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="置信度")
    evidence_uids: list[str] = Field(default_factory=list, description="支撑证据")


class PathResult(BaseModel):
    """路径查询结果。"""

    nodes: list[dict[str, Any]] = Field(description="路径上的节点")
    relationships: list[dict[str, Any]] = Field(description="路径上的关系")
    length: int = Field(description="路径长度")


class NeighborResult(BaseModel):
    """邻居查询结果。"""

    node: dict[str, Any] = Field(description="邻居节点")
    relationship: dict[str, Any] = Field(description="连接关系")
    direction: str = Field(description="关系方向：incoming/outgoing")


class CommunityResult(BaseModel):
    """社区查询结果。"""

    community_id: int = Field(description="社区标识")
    members: list[dict[str, Any]] = Field(description="社区成员")
    size: int = Field(description="社区大小")


@dataclass
class Neo4jStore:
    """Neo4j 数据访问。

    实现实体、事件、关系的存储与查询。
    """

    uri: str
    user: str
    password: str
    database: str = "neo4j"
    _driver_instance: Any = field(default=None, repr=False)

    def _driver(self) -> Any:
        """获取 Neo4j 驱动。"""
        if self._driver_instance is None:
            neo4j = importlib.import_module("neo4j")
            self._driver_instance = neo4j.GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
        return self._driver_instance

    async def connect(self) -> None:
        """建立驱动连接。"""
        self._driver()

    async def close(self) -> None:
        """关闭驱动连接。"""
        if self._driver_instance is not None:
            self._driver_instance.close()
            self._driver_instance = None

    async def upsert_entity(self, entity: Entity) -> None:
        """写入单个实体（兼容接口）。"""
        await self.upsert_entities([entity])

    async def upsert_community(self, community: dict[str, Any]) -> None:
        """写入社区信息（兼容接口）。"""
        return None

    # ==================== 索引管理 ====================

    async def ensure_indexes(self) -> None:
        """创建图索引以优化查询性能。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            # 实体节点索引
            session.run(
                "CREATE INDEX entity_uid_index IF NOT EXISTS FOR (e:Entity) ON (e.uid)"
            )
            session.run(
                "CREATE INDEX entity_type_index IF NOT EXISTS FOR (e:Entity) ON (e.type)"
            )
            session.run(
                "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name)"
            )
            # 事件节点索引
            session.run(
                "CREATE INDEX event_uid_index IF NOT EXISTS FOR (e:Event) ON (e.uid)"
            )
            session.run(
                "CREATE INDEX event_type_index IF NOT EXISTS FOR (e:Event) ON (e.type)"
            )

    # ==================== 节点存储 ====================

    async def upsert_entities(self, entities: Iterable[Entity]) -> None:
        """写入实体节点。"""
        payload = [
            {
                "uid": entity.entity_uid,
                "name": entity.name,
                "type": entity.entity_type.value,
                "summary": entity.summary or "",
                "aliases": entity.aliases,
            }
            for entity in entities
        ]
        if not payload:
            return
        driver = self._driver()
        with driver.session(database=self.database) as session:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Entity {uid: row.uid})
                SET e.name = row.name,
                    e.type = row.type,
                    e.summary = row.summary,
                    e.aliases = row.aliases
                """,
                rows=payload,
            )

    async def upsert_events(self, events: Iterable[Event]) -> None:
        """写入事件节点。"""
        payload = [
            {
                "uid": event.event_uid,
                "type": event.event_type.value,
                "summary": event.summary,
                "confidence": float(event.confidence),
                "time_start": event.time_start.isoformat()
                if event.time_start
                else None,
                "time_end": event.time_end.isoformat() if event.time_end else None,
                "location_name": event.location_name,
            }
            for event in events
        ]
        if not payload:
            return
        driver = self._driver()
        with driver.session(database=self.database) as session:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Event {uid: row.uid})
                SET e.type = row.type,
                    e.summary = row.summary,
                    e.confidence = row.confidence,
                    e.time_start = row.time_start,
                    e.time_end = row.time_end,
                    e.location_name = row.location_name
                """,
                rows=payload,
            )

    # ==================== 关系存储 ====================

    async def upsert_relations(self, relations: Iterable[Relation]) -> None:
        """写入实体间关系。"""
        payload = [
            {
                "uid": rel.relation_uid,
                "source_uid": rel.source_uid,
                "target_uid": rel.target_uid,
                "type": rel.relation_type.value,
                "confidence": float(rel.confidence),
                "properties": rel.properties,
                "evidence_uids": rel.evidence_uids,
            }
            for rel in relations
        ]
        if not payload:
            return
        driver = self._driver()
        with driver.session(database=self.database) as session:
            # 使用 APOC 或动态关系类型
            for row in payload:
                session.run(
                    f"""
                    MATCH (source {{uid: $source_uid}})
                    MATCH (target {{uid: $target_uid}})
                    MERGE (source)-[r:{row["type"]} {{uid: $uid}}]->(target)
                    SET r.confidence = $confidence,
                        r.properties = $properties,
                        r.evidence_uids = $evidence_uids
                    """,
                    uid=row["uid"],
                    source_uid=row["source_uid"],
                    target_uid=row["target_uid"],
                    confidence=row["confidence"],
                    properties=row["properties"],
                    evidence_uids=row["evidence_uids"],
                )

    async def upsert_event_participants(self, events: Iterable[Event]) -> None:
        """写入事件参与关系（Entity→Event）。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            for event in events:
                for participant in event.participants:
                    session.run(
                        """
                        MATCH (entity:Entity {uid: $entity_uid})
                        MATCH (event:Event {uid: $event_uid})
                        MERGE (entity)-[r:PARTICIPATES_IN]->(event)
                        SET r.role = $role
                        """,
                        entity_uid=participant.entity_uid,
                        event_uid=event.event_uid,
                        role=participant.role,
                    )

    # ==================== 查询接口 ====================

    async def get_entity(self, entity_uid: str) -> dict[str, Any] | None:
        """获取实体节点。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            result = session.run(
                "MATCH (e:Entity {uid: $uid}) RETURN e",
                uid=entity_uid,
            )
            record = result.single()
            if record is None:
                return None
            return dict(record["e"])

    async def get_event(self, event_uid: str) -> dict[str, Any] | None:
        """获取事件节点。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            result = session.run(
                "MATCH (e:Event {uid: $uid}) RETURN e",
                uid=event_uid,
            )
            record = result.single()
            if record is None:
                return None
            return dict(record["e"])

    async def get_neighbors(
        self,
        node_uid: str,
        relation_types: list[RelationType] | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> list[NeighborResult]:
        """获取节点的邻居。

        Args:
            node_uid: 节点 UID
            relation_types: 过滤的关系类型
            direction: 方向（incoming/outgoing/both）
            limit: 最大返回数量

        Returns:
            邻居列表
        """
        driver = self._driver()
        type_filter = ""
        if relation_types:
            types_str = "|".join(rt.value for rt in relation_types)
            type_filter = f":{types_str}"

        if direction == "outgoing":
            pattern = f"(n)-[r{type_filter}]->(neighbor)"
        elif direction == "incoming":
            pattern = f"(n)<-[r{type_filter}]-(neighbor)"
        else:
            pattern = f"(n)-[r{type_filter}]-(neighbor)"

        query = f"""
        MATCH {pattern}
        WHERE n.uid = $uid
        RETURN neighbor, r, 
               CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
        LIMIT $limit
        """

        results: list[NeighborResult] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, uid=node_uid, limit=limit)
            for record in records:
                results.append(
                    NeighborResult(
                        node=dict(record["neighbor"]),
                        relationship={
                            "type": record["r"].type,
                            **dict(record["r"]),
                        },
                        direction=record["direction"],
                    )
                )
        return results

    async def find_path(
        self,
        source_uid: str,
        target_uid: str,
        relation_types: list[RelationType] | None = None,
        max_depth: int = 5,
    ) -> list[PathResult]:
        """查找两个节点间的路径。

        Args:
            source_uid: 源节点 UID
            target_uid: 目标节点 UID
            relation_types: 过滤的关系类型
            max_depth: 最大路径深度

        Returns:
            路径列表
        """
        driver = self._driver()
        type_filter = ""
        if relation_types:
            types_str = "|".join(rt.value for rt in relation_types)
            type_filter = f":{types_str}"

        query = f"""
        MATCH path = shortestPath(
            (source {{uid: $source_uid}})-[r{type_filter}*1..{max_depth}]-(target {{uid: $target_uid}})
        )
        RETURN nodes(path) AS nodes, relationships(path) AS rels, length(path) AS len
        LIMIT 10
        """

        results: list[PathResult] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, source_uid=source_uid, target_uid=target_uid)
            for record in records:
                nodes = [dict(n) for n in record["nodes"]]
                rels = [{"type": r.type, **dict(r)} for r in record["rels"]]
                results.append(
                    PathResult(
                        nodes=nodes,
                        relationships=rels,
                        length=record["len"],
                    )
                )
        return results

    async def find_paths_all(
        self,
        source_uid: str,
        target_uid: str,
        relation_types: list[RelationType] | None = None,
        max_depth: int = 5,
        limit: int = 20,
    ) -> list[PathResult]:
        """查找两个节点间的所有路径。"""
        driver = self._driver()
        type_filter = ""
        if relation_types:
            types_str = "|".join(rt.value for rt in relation_types)
            type_filter = f":{types_str}"

        query = f"""
        MATCH path = (source {{uid: $source_uid}})-[r{type_filter}*1..{max_depth}]-(target {{uid: $target_uid}})
        RETURN nodes(path) AS nodes, relationships(path) AS rels, length(path) AS len
        ORDER BY len
        LIMIT $limit
        """

        results: list[PathResult] = []
        with driver.session(database=self.database) as session:
            records = session.run(
                query,
                source_uid=source_uid,
                target_uid=target_uid,
                limit=limit,
            )
            for record in records:
                nodes = [dict(n) for n in record["nodes"]]
                rels = [{"type": r.type, **dict(r)} for r in record["rels"]]
                results.append(
                    PathResult(
                        nodes=nodes,
                        relationships=rels,
                        length=record["len"],
                    )
                )
        return results

    async def get_entity_relations(
        self,
        entity_uid: str,
        relation_types: list[RelationType] | None = None,
    ) -> list[dict[str, Any]]:
        """获取实体的所有关系。

        返回格式：[{source, target, type, properties}]
        """
        driver = self._driver()
        type_filter = ""
        if relation_types:
            types_str = "|".join(rt.value for rt in relation_types)
            type_filter = f":{types_str}"

        query = f"""
        MATCH (e {{uid: $uid}})-[r{type_filter}]-(other)
        RETURN e AS source, other AS target, type(r) AS rel_type, properties(r) AS props,
               CASE WHEN startNode(r) = e THEN 'outgoing' ELSE 'incoming' END AS direction
        """

        results: list[dict[str, Any]] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, uid=entity_uid)
            for record in records:
                results.append(
                    {
                        "source": dict(record["source"]),
                        "target": dict(record["target"]),
                        "type": record["rel_type"],
                        "properties": record["props"],
                        "direction": record["direction"],
                    }
                )
        return results

    async def get_event_participants(self, event_uid: str) -> list[dict[str, Any]]:
        """获取事件的参与实体。"""
        driver = self._driver()
        query = """
        MATCH (entity:Entity)-[r:PARTICIPATES_IN]->(event:Event {uid: $uid})
        RETURN entity, r.role AS role
        """
        results: list[dict[str, Any]] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, uid=event_uid)
            for record in records:
                results.append(
                    {
                        "entity": dict(record["entity"]),
                        "role": record["role"],
                    }
                )
        return results

    async def get_entity_events(
        self, entity_uid: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """获取实体参与的事件。"""
        driver = self._driver()
        query = """
        MATCH (entity:Entity {uid: $uid})-[r:PARTICIPATES_IN]->(event:Event)
        RETURN event, r.role AS role
        ORDER BY event.time_start DESC
        LIMIT $limit
        """
        results: list[dict[str, Any]] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, uid=entity_uid, limit=limit)
            for record in records:
                results.append(
                    {
                        "event": dict(record["event"]),
                        "role": record["role"],
                    }
                )
        return results

    # ==================== 社区检测 ====================

    async def detect_communities_louvain(
        self,
        node_labels: list[str] | None = None,
        relation_types: list[RelationType] | None = None,
    ) -> list[CommunityResult]:
        """使用 Louvain 算法检测社区。

        需要安装 Neo4j GDS（Graph Data Science）库。
        """
        driver = self._driver()
        label_filter = "Entity" if node_labels is None else "|".join(node_labels)
        type_filter = (
            "*"
            if relation_types is None
            else "|".join(rt.value for rt in relation_types)
        )

        with driver.session(database=self.database) as session:
            # 创建图投影
            session.run(
                f"""
                CALL gds.graph.project(
                    'community_graph',
                    '{label_filter}',
                    '{type_filter}'
                )
                """
            )
            # 运行 Louvain 算法
            result = session.run(
                """
                CALL gds.louvain.stream('community_graph')
                YIELD nodeId, communityId
                RETURN gds.util.asNode(nodeId) AS node, communityId
                ORDER BY communityId
                """
            )
            # 按社区分组
            communities: dict[int, list[dict[str, Any]]] = {}
            for record in result:
                cid = record["communityId"]
                if cid not in communities:
                    communities[cid] = []
                communities[cid].append(dict(record["node"]))

            # 清理图投影
            session.run("CALL gds.graph.drop('community_graph', false)")

        return [
            CommunityResult(
                community_id=cid,
                members=members,
                size=len(members),
            )
            for cid, members in communities.items()
        ]

    async def get_entity_community(self, entity_uid: str) -> CommunityResult | None:
        """获取实体所属的社区。

        需要先运行社区检测并写入 communityId 属性。
        """
        driver = self._driver()
        query = """
        MATCH (e:Entity {uid: $uid})
        WHERE e.communityId IS NOT NULL
        WITH e.communityId AS cid
        MATCH (member:Entity {communityId: cid})
        RETURN cid AS communityId, collect(member) AS members
        """
        with driver.session(database=self.database) as session:
            result = session.run(query, uid=entity_uid)
            record = result.single()
            if record is None:
                return None
            members = [dict(m) for m in record["members"]]
            return CommunityResult(
                community_id=record["communityId"],
                members=members,
                size=len(members),
            )

    # ==================== 批量查询 ====================

    async def search_entities(
        self,
        entity_types: list[str] | None = None,
        name_contains: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """搜索实体。"""
        driver = self._driver()
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if entity_types:
            conditions.append("e.type IN $types")
            params["types"] = entity_types
        if name_contains:
            conditions.append("e.name CONTAINS $name_contains")
            params["name_contains"] = name_contains

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
        MATCH (e:Entity)
        {where_clause}
        RETURN e
        LIMIT $limit
        """

        results: list[dict[str, Any]] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, **params)
            for record in records:
                results.append(dict(record["e"]))
        return results

    async def search_events(
        self,
        event_types: list[str] | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """搜索事件。"""
        driver = self._driver()
        conditions = []
        params: dict[str, Any] = {"limit": limit}

        if event_types:
            conditions.append("e.type IN $types")
            params["types"] = event_types
        if time_start:
            conditions.append("e.time_start >= $time_start")
            params["time_start"] = time_start
        if time_end:
            conditions.append("e.time_end <= $time_end")
            params["time_end"] = time_end

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"""
        MATCH (e:Event)
        {where_clause}
        RETURN e
        ORDER BY e.time_start DESC
        LIMIT $limit
        """

        results: list[dict[str, Any]] = []
        with driver.session(database=self.database) as session:
            records = session.run(query, **params)
            for record in records:
                results.append(dict(record["e"]))
        return results

    async def count_nodes(self) -> dict[str, int]:
        """统计节点数量。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            entity_count = session.run(
                "MATCH (e:Entity) RETURN count(e) AS count"
            ).single()["count"]
            event_count = session.run(
                "MATCH (e:Event) RETURN count(e) AS count"
            ).single()["count"]
            rel_count = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS count"
            ).single()["count"]
        return {
            "entities": entity_count,
            "events": event_count,
            "relationships": rel_count,
        }

    async def delete_all(self) -> None:
        """删除所有节点和关系（谨慎使用）。"""
        driver = self._driver()
        with driver.session(database=self.database) as session:
            session.run("MATCH (n) DETACH DELETE n")
