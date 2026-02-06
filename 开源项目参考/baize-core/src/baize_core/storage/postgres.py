"""Postgres 存储 Facade。

PostgresStore 作为外观类，委托给各领域 Repository 实现具体操作。
保持原有 API 向后兼容，内部使用 Repository 模式重构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.schemas.entity_event import Entity, EntityType, Event, EventType, GeoBBox
from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report
from baize_core.schemas.review_request import (
    ReviewCreateRequest,
    ReviewRequest,
)
from baize_core.schemas.storm import StormIteration, StormOutline, StormSectionSpec
from baize_core.schemas.task import TaskResponse, TaskSpec
from baize_core.storage import models
from baize_core.storage.database import create_engine, create_session_factory
from baize_core.storage.repositories import (
    AuditRepository,
    EntityRepository,
    EvidenceRepository,
    RetentionRepository,
    ReviewRepository,
    StormRepository,
    TaskRepository,
)


@dataclass
class PostgresStore:
    """Postgres 存储外观类。

    委托给各领域 Repository 实现具体操作，保持原有 API 向后兼容。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]
    _engine: AsyncEngine | None = field(default=None, repr=False)

    # 内部 Repository 实例
    _task_repo: TaskRepository = field(init=False, repr=False)
    _evidence_repo: EvidenceRepository = field(init=False, repr=False)
    _storm_repo: StormRepository = field(init=False, repr=False)
    _audit_repo: AuditRepository = field(init=False, repr=False)
    _entity_repo: EntityRepository = field(init=False, repr=False)
    _retention_repo: RetentionRepository = field(init=False, repr=False)
    _review_repo: ReviewRepository = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """初始化各 Repository。"""
        self._task_repo = TaskRepository(self.session_factory)
        self._evidence_repo = EvidenceRepository(self.session_factory)
        self._storm_repo = StormRepository(self.session_factory)
        self._audit_repo = AuditRepository(self.session_factory)
        self._entity_repo = EntityRepository(self.session_factory)
        self._retention_repo = RetentionRepository(self.session_factory)
        self._review_repo = ReviewRepository(self.session_factory)

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgresStore:
        """从 DSN 创建存储实例。"""
        engine = create_engine(dsn)
        session_factory = create_session_factory(engine)
        return cls(session_factory=session_factory, _engine=engine)

    async def connect(self) -> None:
        """建立数据库连接（兼容接口）。"""
        return None

    async def close(self) -> None:
        """关闭数据库连接（兼容接口）。"""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    # =========================================================================
    # Task 操作（委托给 TaskRepository）
    # =========================================================================

    async def create_task(self, task: TaskSpec) -> TaskResponse:
        """创建任务记录。"""
        return await self._task_repo.create(task)

    async def get_tasks_since(self, cutoff: datetime) -> list[models.TaskModel]:
        """获取指定时间之后的任务。"""
        return await self._task_repo.get_since(cutoff)

    # =========================================================================
    # Evidence 操作（委托给 EvidenceRepository）
    # =========================================================================

    async def get_artifacts_since(self, cutoff: datetime) -> list[models.ArtifactModel]:
        """获取指定时间之后的 Artifact。"""
        return await self._evidence_repo.get_artifacts_since(cutoff)

    async def get_evidence_since(self, cutoff: datetime) -> list[models.EvidenceModel]:
        """获取指定时间之后的 Evidence。"""
        return await self._evidence_repo.get_evidence_since(cutoff)

    async def get_artifact(self, artifact_uid: str) -> models.ArtifactModel | None:
        """获取指定 Artifact。"""
        return await self._evidence_repo.get_artifact(artifact_uid)

    async def get_evidence(self, evidence_uid: str) -> models.EvidenceModel | None:
        """获取指定 Evidence。"""
        return await self._evidence_repo.get_evidence(evidence_uid)

    async def create_artifact(
        self,
        *,
        artifact_uid: str,
        storage_ref: str,
        source_url: str,
        fetched_at: datetime,
        content_sha256: str,
        mime_type: str,
        origin_tool: str | None = None,
        fetch_trace_id: str | None = None,
        license_note: str | None = None,
    ) -> models.ArtifactModel:
        """创建单个 Artifact 记录。"""
        return await self._evidence_repo.create_artifact(
                artifact_uid=artifact_uid,
            storage_ref=storage_ref,
            source_url=source_url,
                fetched_at=fetched_at,
            content_sha256=content_sha256,
                mime_type=mime_type,
                origin_tool=origin_tool,
            fetch_trace_id=fetch_trace_id,
            license_note=license_note,
            )

    async def get_task_evidence_chain(self, task_id: str) -> dict[str, Any] | None:
        """获取任务证据链。"""
        return await self._evidence_repo.get_task_evidence_chain(task_id)

    async def store_artifacts(self, artifacts: list[Artifact]) -> None:
        """写入 Artifact。"""
        return await self._evidence_repo.store_artifacts(artifacts)

    async def store_evidence_chain(
        self,
        *,
        artifacts: list[Artifact],
        chunks: list[Chunk],
        evidence_items: list[Evidence],
        claims: list[Claim],
    ) -> None:
        """写入完整证据链。"""
        return await self._evidence_repo.store_evidence_chain(
            artifacts=artifacts,
            chunks=chunks,
            evidence_items=evidence_items,
            claims=claims,
        )

    async def store_chunks(self, chunks: list[Chunk]) -> None:
        """写入 Chunk。"""
        return await self._evidence_repo.store_chunks(chunks)

    async def store_evidence(self, evidence_items: list[Evidence]) -> None:
        """写入 Evidence。"""
        return await self._evidence_repo.store_evidence(evidence_items)

    async def store_claims(self, claims: list[Claim]) -> None:
        """写入 Claim 与关联表。"""
        return await self._evidence_repo.store_claims(claims)

    async def store_report(self, report: Report) -> None:
        """写入 Report 与引用。"""
        return await self._evidence_repo.store_report(report)

    async def save_quality_report(self, report: dict[str, Any]) -> None:
        """保存质量报告（预留接口）。"""
        return await self._evidence_repo.save_quality_report(report)

    async def get_unindexed_chunks(self, limit: int) -> list[dict[str, Any]]:
        """获取待索引的 Chunk 列表。"""
        return await self._evidence_repo.get_unindexed_chunks(limit)

    async def mark_chunk_indexed(self, chunk_uid: str) -> None:
        """标记 Chunk 已索引（当前为兼容占位）。"""
        return await self._evidence_repo.mark_chunk_indexed(chunk_uid)

    # =========================================================================
    # Storm 操作（委托给 StormRepository）
    # =========================================================================

    async def store_storm_outline(self, outline: StormOutline) -> None:
        """写入 STORM 大纲与章节。"""
        return await self._storm_repo.store_outline(outline)

    async def store_storm_sections(
        self, outline_uid: str, sections: list[StormSectionSpec]
    ) -> None:
        """补充写入章节。"""
        return await self._storm_repo.store_sections(outline_uid, sections)

    async def store_storm_iterations(self, iterations: list[StormIteration]) -> None:
        """写入章节研究迭代。"""
        return await self._storm_repo.store_iterations(iterations)

    async def store_storm_section_evidence(
        self, *, section_uid: str, evidence_uids: list[str]
    ) -> None:
        """写入章节证据关联。"""
        return await self._storm_repo.store_section_evidence(
            section_uid=section_uid, evidence_uids=evidence_uids
        )

    # =========================================================================
    # Audit 操作（委托给 AuditRepository）
    # =========================================================================

    async def record_policy_decision(self, record: PolicyDecisionRecord) -> None:
        """写入策略决策审计。"""
        return await self._audit_repo.record_policy_decision(record)

    async def record_tool_trace(self, trace: ToolTrace) -> None:
        """写入工具调用审计。"""
        return await self._audit_repo.record_tool_trace(trace)

    async def record_model_trace(self, trace: ModelTrace) -> None:
        """写入模型调用审计。"""
        return await self._audit_repo.record_model_trace(trace)

    async def query_tool_traces(
        self,
        *,
        task_id: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ToolTrace]:
        """查询工具调用记录。"""
        return await self._audit_repo.query_tool_traces(
            task_id=task_id,
            tool_name=tool_name,
            success=success,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    async def list_tool_traces_by_task(self, task_id: str) -> list[ToolTrace]:
        """按任务读取全部工具调用记录。"""
        return await self._audit_repo.list_tool_traces_by_task(task_id)

    async def query_tool_traces_by_policy_decision_id(
        self, decision_id: str
    ) -> list[ToolTrace]:
        """按策略决策 ID 查询工具调用记录。"""
        return await self._audit_repo.query_tool_traces_by_policy_decision_id(
            decision_id
        )

    async def query_model_traces(
        self,
        *,
        task_id: str | None = None,
        model_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ModelTrace]:
        """查询模型调用记录。"""
        return await self._audit_repo.query_model_traces(
            task_id=task_id,
            model_name=model_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    async def query_policy_decisions(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PolicyDecisionRecord]:
        """查询策略决策记录。"""
        return await self._audit_repo.query_policy_decisions(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    async def get_tool_trace(self, trace_id: str) -> ToolTrace | None:
        """获取单个工具调用记录。"""
        return await self._audit_repo.get_tool_trace(trace_id)

    async def get_model_trace(self, trace_id: str) -> ModelTrace | None:
        """获取单个模型调用记录。"""
        return await self._audit_repo.get_model_trace(trace_id)

    async def get_tool_trace_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取工具调用统计。"""
        return await self._audit_repo.get_tool_trace_stats(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_model_trace_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取模型调用统计。"""
        return await self._audit_repo.get_model_trace_stats(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_policy_decision_stats(
        self,
        *,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """获取策略决策统计。"""
        return await self._audit_repo.get_policy_decision_stats(
            task_id=task_id,
            start_time=start_time,
            end_time=end_time,
        )

    # =========================================================================
    # Entity/Event 操作（委托给 EntityRepository）
    # =========================================================================

    async def store_entities(self, entities: list[Entity]) -> None:
        """写入实体与证据关联。"""
        return await self._entity_repo.store_entities(entities)

    async def get_entity_by_uid(self, entity_uid: str) -> Entity | None:
        """按 UID 读取实体。"""
        return await self._entity_repo.get_by_uid(entity_uid)

    async def list_entities(
        self,
        *,
        entity_types: list[EntityType] | None,
        bbox: GeoBBox | None,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        """按条件查询实体列表。"""
        return await self._entity_repo.list_entities(
            entity_types=entity_types,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )

    async def store_events(self, events: list[Event]) -> None:
        """写入事件与关联关系。"""
        return await self._entity_repo.store_events(events)

    async def get_event_by_uid(self, event_uid: str) -> Event | None:
        """按 UID 读取事件。"""
        return await self._entity_repo.get_event_by_uid(event_uid)

    async def list_events(
        self,
        *,
        event_types: list[EventType] | None,
        time_start: datetime | None,
        time_end: datetime | None,
        bbox: GeoBBox | None,
        limit: int,
        offset: int,
    ) -> list[Event]:
        """按条件查询事件列表。"""
        return await self._entity_repo.list_events(
            event_types=event_types,
            time_start=time_start,
            time_end=time_end,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )

    # =========================================================================
    # Retention 操作（委托给 RetentionRepository）
    # =========================================================================

    async def soft_delete_task_data(self, task_id: str) -> dict[str, int]:
        """按 task_id 软删除关联证据链数据。"""
        return await self._retention_repo.soft_delete_task_data(task_id)

    async def mark_expired_unreferenced(
        self, *, now: datetime | None = None, batch_size: int = 200
    ) -> dict[str, int]:
        """标记过期且无引用的数据为软删除。"""
        return await self._retention_repo.mark_expired_unreferenced(
            now=now, batch_size=batch_size
        )

    async def hard_delete_soft_deleted_data(
        self,
        *,
        now: datetime | None = None,
        grace_days: int = 7,
        batch_size: int = 200,
    ) -> dict[str, object]:
        """物理删除已软删除且超过宽限期的数据。"""
        return await self._retention_repo.hard_delete_soft_deleted_data(
            now=now, grace_days=grace_days, batch_size=batch_size
        )

    async def get_retention_stats(self, *, grace_days: int = 7) -> dict[str, int]:
        """获取 retention/cleanup 统计信息。"""
        return await self._retention_repo.get_stats(grace_days=grace_days)

    # =========================================================================
    # Review 操作（委托给 ReviewRepository）
    # =========================================================================

    async def create_review_request(
        self, decision: ReviewCreateRequest
    ) -> ReviewRequest:
        """创建审查请求。"""
        return await self._review_repo.create(decision)

    async def get_review_request(self, review_id: str) -> ReviewRequest:
        """读取审查请求。"""
        return await self._review_repo.get(review_id)

    async def approve_review(self, review_id: str) -> ReviewRequest:
        """通过审查。"""
        return await self._review_repo.approve(review_id)

    async def reject_review(self, review_id: str, reason: str | None) -> ReviewRequest:
        """拒绝审查。"""
        return await self._review_repo.reject(review_id, reason)
