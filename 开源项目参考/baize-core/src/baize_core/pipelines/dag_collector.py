"""采集 DAG - 定时采集 RSS/变更检测源。

实现情报采集流水线：
1. RSS 订阅源采集
2. 网页变更检测
3. 内容归档到 MinIO
4. 生成 Artifact 记录
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CollectorConfig:
    """采集 DAG 配置。"""

    dag_id: str = "intel_collector"
    schedule_interval: str = "*/30 * * * *"  # 每 30 分钟
    start_date: datetime = field(default_factory=lambda: datetime(2024, 1, 1))
    catchup: bool = False
    max_active_runs: int = 1
    default_args: dict[str, Any] = field(default_factory=dict)

    # RSS 配置
    rss_feeds: list[str] = field(default_factory=list)
    rss_timeout: int = 30

    # 变更检测配置
    changedetection_url: str = ""
    changedetection_api_key: str = ""

    # MinIO 配置
    minio_bucket: str = "artifacts"


def create_collector_dag(config: CollectorConfig) -> Any:
    """创建采集 DAG。

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
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        **config.default_args,
    }

    dag = DAG(
        dag_id=config.dag_id,
        default_args=default_args,
        description="情报采集流水线",
        schedule_interval=config.schedule_interval,
        start_date=config.start_date,
        catchup=config.catchup,
        max_active_runs=config.max_active_runs,
        tags=["intel", "collector"],
    )

    with dag:
        # 任务 1: 采集 RSS 源
        collect_rss = PythonOperator(
            task_id="collect_rss",
            python_callable=_collect_rss_feeds,
            op_kwargs={
                "feeds": config.rss_feeds,
                "timeout": config.rss_timeout,
            },
        )

        # 任务 2: 检查变更检测
        check_changes = PythonOperator(
            task_id="check_changes",
            python_callable=_check_changedetection,
            op_kwargs={
                "url": config.changedetection_url,
                "api_key": config.changedetection_api_key,
            },
        )

        # 任务 3: 归档内容
        archive_content = PythonOperator(
            task_id="archive_content",
            python_callable=_archive_to_minio,
            op_kwargs={"bucket": config.minio_bucket},
        )

        # 任务 4: 创建 Artifact 记录
        create_artifacts = PythonOperator(
            task_id="create_artifacts",
            python_callable=_create_artifact_records,
        )

        # 定义依赖
        [collect_rss, check_changes] >> archive_content >> create_artifacts

    return dag


def _collect_rss_feeds(
    feeds: list[str], timeout: int, **context: Any
) -> list[dict[str, Any]]:
    """采集 RSS 源。"""
    import asyncio

    from baize_core.adapters.rsshub import fetch_rss_items

    collected_items: list[dict[str, Any]] = []

    async def _fetch_all() -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for feed_url in feeds:
            try:
                feed_items = await fetch_rss_items(feed_url, timeout=timeout)
                items.extend(feed_items)
                logger.info("采集 RSS 成功: %s (%d 条)", feed_url, len(feed_items))
            except Exception as exc:
                logger.warning("采集 RSS 失败: %s - %s", feed_url, exc)
        return items

    collected_items = asyncio.run(_fetch_all())
    context["ti"].xcom_push(key="rss_items", value=collected_items)
    return collected_items


def _check_changedetection(
    url: str, api_key: str, **context: Any
) -> list[dict[str, Any]]:
    """检查变更检测。"""
    if not url:
        logger.info("变更检测未配置，跳过")
        return []

    import asyncio

    from baize_core.adapters.changedetection import fetch_changes

    async def _fetch() -> list[dict[str, Any]]:
        try:
            return await fetch_changes(url, api_key)
        except Exception as exc:
            logger.warning("变更检测失败: %s", exc)
            return []

    changes = asyncio.run(_fetch())
    context["ti"].xcom_push(key="changes", value=changes)
    return changes


def _archive_to_minio(bucket: str, **context: Any) -> list[str]:
    """归档内容到 MinIO。"""
    import asyncio

    rss_items = context["ti"].xcom_pull(key="rss_items", task_ids="collect_rss") or []
    changes = context["ti"].xcom_pull(key="changes", task_ids="check_changes") or []

    all_items = rss_items + changes
    storage_refs: list[str] = []

    async def _archive() -> list[str]:
        from baize_core.config.settings import get_settings
        from baize_core.storage.minio_store import MinIOStore

        settings = get_settings()
        store = MinIOStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
        )
        await store.connect()

        refs: list[str] = []
        for item in all_items:
            try:
                content = item.get("content", "")
                if not content:
                    continue
                ref = await store.upload_content(
                    bucket=bucket,
                    content=content.encode("utf-8"),
                    content_type="text/html",
                    metadata={"source": item.get("source", "unknown")},
                )
                refs.append(ref)
            except Exception as exc:
                logger.warning("归档失败: %s", exc)

        await store.close()
        return refs

    storage_refs = asyncio.run(_archive())
    context["ti"].xcom_push(key="storage_refs", value=storage_refs)
    logger.info("归档完成: %d 个文件", len(storage_refs))
    return storage_refs


def _create_artifact_records(**context: Any) -> int:
    """创建 Artifact 记录。"""
    import asyncio
    from uuid import uuid4

    storage_refs = (
        context["ti"].xcom_pull(key="storage_refs", task_ids="archive_content") or []
    )
    rss_items = context["ti"].xcom_pull(key="rss_items", task_ids="collect_rss") or []

    async def _create() -> int:
        from baize_core.config.settings import get_settings
        from baize_core.storage.postgres import PostgresStore

        settings = get_settings()
        store = PostgresStore.from_dsn(settings.database_url)
        await store.connect()

        created = 0
        for i, ref in enumerate(storage_refs):
            try:
                item = rss_items[i] if i < len(rss_items) else {}
                await store.create_artifact(
                    artifact_uid=str(uuid4()),
                    storage_ref=ref,
                    origin_url=item.get("link", ""),
                    origin_tool="rss_collector",
                    fetched_at=datetime.utcnow(),
                    content_hash=item.get("hash", ""),
                )
                created += 1
            except Exception as exc:
                logger.warning("创建 Artifact 失败: %s", exc)

        await store.close()
        return created

    count = asyncio.run(_create())
    logger.info("创建 Artifact 记录: %d 条", count)
    return count


def _create_mock_dag(config: CollectorConfig) -> dict[str, Any]:
    """创建模拟 DAG（用于非 Airflow 环境）。"""
    return {
        "dag_id": config.dag_id,
        "schedule_interval": config.schedule_interval,
        "tasks": [
            "collect_rss",
            "check_changes",
            "archive_content",
            "create_artifacts",
        ],
        "mock": True,
    }
