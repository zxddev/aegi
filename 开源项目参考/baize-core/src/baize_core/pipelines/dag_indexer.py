"""索引构建 DAG - GraphRAG 索引增量更新。

实现知识图谱索引流水线：
1. 加载新增 Artifact/Chunk
2. 实体/事件抽取
3. 社区检测
4. 向量索引更新
5. 图谱索引更新
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IndexerConfig:
    """索引 DAG 配置。"""

    dag_id: str = "graphrag_indexer"
    schedule_interval: str = "0 */4 * * *"  # 每 4 小时
    start_date: datetime = field(default_factory=lambda: datetime(2024, 1, 1))
    catchup: bool = False
    max_active_runs: int = 1
    default_args: dict[str, Any] = field(default_factory=dict)

    # 批量处理配置
    batch_size: int = 100

    # 模型配置
    extraction_model: str = "extractor"


def create_indexer_dag(config: IndexerConfig) -> Any:
    """创建索引构建 DAG。

    Args:
        config: DAG 配置

    Returns:
        Airflow DAG 对象
    """
    try:
        from airflow import DAG
        from airflow.operators.python import PythonOperator
    except ImportError:
        logger.warning("Airflow 未安装，返回模拟 DAG")
        return _create_mock_dag(config)

    default_args = {
        "owner": "baize-core",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
        **config.default_args,
    }

    dag = DAG(
        dag_id=config.dag_id,
        default_args=default_args,
        description="GraphRAG 索引构建流水线",
        schedule_interval=config.schedule_interval,
        start_date=config.start_date,
        catchup=config.catchup,
        max_active_runs=config.max_active_runs,
        tags=["graphrag", "indexer"],
    )

    with dag:
        # 任务 1: 加载待处理数据
        load_data = PythonOperator(
            task_id="load_pending_data",
            python_callable=_load_pending_data,
            op_kwargs={"batch_size": config.batch_size},
        )

        # 任务 2: 实体/事件抽取
        extract_entities = PythonOperator(
            task_id="extract_entities",
            python_callable=_extract_entities,
            op_kwargs={"model": config.extraction_model},
        )

        # 任务 3: 社区检测
        detect_communities = PythonOperator(
            task_id="detect_communities",
            python_callable=_detect_communities,
        )

        # 任务 4: 向量索引更新
        update_vectors = PythonOperator(
            task_id="update_vector_index",
            python_callable=_update_vector_index,
        )

        # 任务 5: 图谱索引更新
        update_graph = PythonOperator(
            task_id="update_graph_index",
            python_callable=_update_graph_index,
        )

        # 任务 6: 标记处理完成
        mark_complete = PythonOperator(
            task_id="mark_complete",
            python_callable=_mark_processing_complete,
        )

        # 定义依赖
        load_data >> extract_entities >> detect_communities
        detect_communities >> [update_vectors, update_graph] >> mark_complete

    return dag


def _load_pending_data(batch_size: int, **context: Any) -> list[dict[str, Any]]:
    """加载待处理的 Artifact/Chunk。"""
    import asyncio

    async def _load() -> list[dict[str, Any]]:
        from baize_core.config.settings import get_settings
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        # 加载未索引的 Chunk（get_unindexed_chunks 已返回正确格式的 dict）
        chunks = await store.get_unindexed_chunks(limit=batch_size)
        await store.close()

        return chunks

    pending = asyncio.run(_load())
    context["ti"].xcom_push(key="pending_chunks", value=pending)
    logger.info("加载待处理 Chunk: %d 条", len(pending))
    return pending


def _extract_entities(model: str, **context: Any) -> list[dict[str, Any]]:
    """抽取实体和事件。

    注意：此函数需要完整的 GraphRagPipeline 实例化，
    包括 LlmRunner、PostgresStore 和 Neo4jStore。
    当前实现返回空列表作为占位。
    """
    import asyncio

    pending = (
        context["ti"].xcom_pull(key="pending_chunks", task_ids="load_pending_data")
        or []
    )

    if not pending:
        context["ti"].xcom_push(key="entities", value=[])
        logger.info("无待处理数据，跳过实体抽取")
        return []

    async def _extract() -> list[dict[str, Any]]:
        # TODO: 需要完整实现 GraphRagPipeline 实体抽取
        # 当前占位实现，返回空列表
        # 完整实现需要：
        # 1. 从上下文获取 task_id
        # 2. 初始化 LlmRunner、PostgresStore、Neo4jStore
        # 3. 调用 GraphRagPipeline.index_chunks()
        logger.info("实体抽取待实现，待处理 %d 个 chunk", len(pending))
        return []

    extracted = asyncio.run(_extract())
    context["ti"].xcom_push(key="entities", value=extracted)
    logger.info("抽取实体: %d 个", len(extracted))
    return extracted


def _detect_communities(**context: Any) -> list[dict[str, Any]]:
    """社区检测。"""
    from baize_core.graph.community import (
        CommunityEdge,
        CommunityNode,
        LouvainDetector,
    )

    entities = (
        context["ti"].xcom_pull(key="entities", task_ids="extract_entities") or []
    )

    if not entities:
        context["ti"].xcom_push(key="communities", value=[])
        logger.info("无实体，跳过社区检测")
        return []

    # 将实体转换为 CommunityNode
    nodes: list[CommunityNode] = []
    edges: list[CommunityEdge] = []
    node_ids: set[str] = set()

    for entity in entities:
        node_id = entity.get("entity_uid") or entity.get("id", "")
        if node_id and node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append(
                CommunityNode(
                    node_id=node_id,
                    label=entity.get("name", ""),
                    node_type=entity.get("type", "unknown"),
                    properties=entity,
                )
            )
        # 从 relations 字段构建边
        for rel in entity.get("relations", []):
            target_id = rel.get("target_id", "")
            if target_id:
                edges.append(
                    CommunityEdge(
                        source_id=node_id,
                        target_id=target_id,
                        relation_type=rel.get("type", "related"),
                        weight=rel.get("weight", 1.0),
                    )
                )

    if not nodes:
        context["ti"].xcom_push(key="communities", value=[])
        logger.info("无有效节点，跳过社区检测")
        return []

    detector = LouvainDetector()
    hierarchy = detector.detect(nodes, edges)

    # 将社区层次结构转换为 dict 列表
    communities: list[dict[str, Any]] = []
    for community in hierarchy.communities.values():
        communities.append(
            {
                "community_id": community.community_id,
                "level": community.level,
                "node_count": len(community.nodes),
                "key_entities": community.key_entities,
                "summary": community.summary,
            }
        )

    context["ti"].xcom_push(key="communities", value=communities)
    logger.info("检测社区: %d 个", len(communities))
    return communities


def _update_vector_index(**context: Any) -> int:
    """更新向量索引。"""
    import asyncio

    pending = (
        context["ti"].xcom_pull(key="pending_chunks", task_ids="load_pending_data")
        or []
    )

    async def _update() -> int:
        from baize_core.config.settings import get_settings
        from baize_core.storage.qdrant_store import QdrantStore

        settings = get_settings()
        store = QdrantStore(config=settings.qdrant_url)
        await store.connect()

        indexed = 0
        for chunk in pending:
            try:
                await store.index_chunk(
                    chunk_uid=chunk["chunk_uid"],
                    text=chunk["text"],
                )
                indexed += 1
            except Exception as exc:
                logger.warning("向量索引失败: %s - %s", chunk["chunk_uid"], exc)

        await store.close()
        return indexed

    count = asyncio.run(_update())
    logger.info("更新向量索引: %d 条", count)
    return count


def _update_graph_index(**context: Any) -> int:
    """更新图谱索引。"""
    import asyncio

    entities = (
        context["ti"].xcom_pull(key="entities", task_ids="extract_entities") or []
    )
    communities = (
        context["ti"].xcom_pull(key="communities", task_ids="detect_communities") or []
    )

    async def _update() -> int:
        from baize_core.config.settings import get_settings
        from baize_core.graph.neo4j_store import Neo4jStore

        settings = get_settings()
        store = Neo4jStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        await store.connect()

        indexed = 0
        for entity in entities:
            try:
                await store.upsert_entity(entity)
                indexed += 1
            except Exception as exc:
                logger.warning("图谱索引失败: %s", exc)

        for community in communities:
            try:
                await store.upsert_community(community)
            except Exception as exc:
                logger.warning("社区索引失败: %s", exc)

        await store.close()
        return indexed

    count = asyncio.run(_update())
    logger.info("更新图谱索引: %d 条", count)
    return count


def _mark_processing_complete(**context: Any) -> int:
    """标记处理完成。"""
    import asyncio

    pending = (
        context["ti"].xcom_pull(key="pending_chunks", task_ids="load_pending_data")
        or []
    )

    async def _mark() -> int:
        from baize_core.config.settings import get_settings
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        marked = 0
        for chunk in pending:
            try:
                await store.mark_chunk_indexed(chunk["chunk_uid"])
                marked += 1
            except Exception as exc:
                logger.warning("标记失败: %s - %s", chunk["chunk_uid"], exc)

        await store.close()
        return marked

    count = asyncio.run(_mark())
    logger.info("标记处理完成: %d 条", count)
    return count


def _create_mock_dag(config: IndexerConfig) -> dict[str, Any]:
    """创建模拟 DAG。"""
    return {
        "dag_id": config.dag_id,
        "schedule_interval": config.schedule_interval,
        "tasks": [
            "load_pending_data",
            "extract_entities",
            "detect_communities",
            "update_vector_index",
            "update_graph_index",
            "mark_complete",
        ],
        "mock": True,
    }
