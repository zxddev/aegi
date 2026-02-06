"""Airflow DAG 流水线定义模块。

提供以下调度能力：
- 定时采集 RSS/变更检测源
- GraphRAG 索引增量更新
- 质量闸门检查
"""

from baize_core.pipelines.dag_collector import (
    CollectorConfig,
    create_collector_dag,
)
from baize_core.pipelines.dag_indexer import (
    IndexerConfig,
    create_indexer_dag,
)
from baize_core.pipelines.dag_quality import (
    QualityConfig,
    create_quality_dag,
)

__all__ = [
    "create_collector_dag",
    "CollectorConfig",
    "create_indexer_dag",
    "IndexerConfig",
    "create_quality_dag",
    "QualityConfig",
]
