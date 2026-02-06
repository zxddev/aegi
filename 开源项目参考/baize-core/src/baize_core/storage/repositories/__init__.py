"""存储 Repository 模块。

提供按领域划分的 Repository 类，实现数据访问层的职责分离。
PostgresStore 作为 Facade 聚合所有 Repository，保持 API 向后兼容。
"""

from baize_core.storage.repositories.audit_repository import AuditRepository
from baize_core.storage.repositories.base import BaseRepository
from baize_core.storage.repositories.entity_repository import EntityRepository
from baize_core.storage.repositories.evidence_repository import EvidenceRepository
from baize_core.storage.repositories.retention_repository import RetentionRepository
from baize_core.storage.repositories.review_repository import ReviewRepository
from baize_core.storage.repositories.storm_repository import StormRepository
from baize_core.storage.repositories.task_repository import TaskRepository

__all__ = [
    "AuditRepository",
    "BaseRepository",
    "EntityRepository",
    "EvidenceRepository",
    "RetentionRepository",
    "ReviewRepository",
    "StormRepository",
    "TaskRepository",
]
