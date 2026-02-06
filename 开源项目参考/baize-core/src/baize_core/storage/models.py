"""数据库 ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import Identity


class Base(DeclarativeBase):
    """ORM 基类。"""

    metadata = MetaData(schema="baize_core")


class TaskModel(Base):
    """任务表。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    constraints: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    time_window: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ArtifactModel(Base):
    """Artifact 表。"""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    artifact_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    storage_ref: Mapped[str] = mapped_column(Text, nullable=False)
    origin_tool: Mapped[str | None] = mapped_column(Text)
    fetch_trace_id: Mapped[str | None] = mapped_column(Text)
    license_note: Mapped[str | None] = mapped_column(Text)


class ChunkModel(Base):
    """Chunk 表。"""

    __tablename__ = "chunks"
    __table_args__ = (Index("chunks_artifact_uid_idx", "artifact_uid"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    chunk_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    artifact_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("artifacts.artifact_uid"),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_ref: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(Text, nullable=False)


class EvidenceModel(Base):
    """Evidence 表。"""

    __tablename__ = "evidence"
    __table_args__ = (Index("evidence_chunk_uid_idx", "chunk_uid"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    evidence_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    chunk_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("chunks.chunk_uid"),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    base_credibility: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[dict | None] = mapped_column(JSONB)
    conflict_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    conflict_with: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    summary: Mapped[str | None] = mapped_column(Text)


class ClaimModel(Base):
    """Claim 表。"""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    claim_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    contradictions: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )


class ClaimEvidenceModel(Base):
    """Claim-Evidence 关联表。"""

    __tablename__ = "claim_evidence"
    __table_args__ = (Index("claim_evidence_evidence_uid_idx", "evidence_uid"),)

    claim_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("claims.claim_uid"),
        primary_key=True,
    )
    evidence_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evidence.evidence_uid"),
        primary_key=True,
    )


class ReportModel(Base):
    """Report 表。"""

    __tablename__ = "reports"
    __table_args__ = (
        Index("reports_task_id_idx", "task_id"),
        Index("reports_outline_uid_idx", "outline_uid"),
    )

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    report_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tasks.task_id"),
        nullable=False,
    )
    outline_uid: Mapped[str | None] = mapped_column(Text)
    report_type: Mapped[str | None] = mapped_column(Text)
    content_ref: Mapped[str] = mapped_column(Text, nullable=False)
    conflict_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ReportReferenceModel(Base):
    """Report 引用表。"""

    __tablename__ = "report_references"
    __table_args__ = (Index("report_references_report_uid_idx", "report_uid"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    report_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("reports.report_uid"),
        nullable=False,
    )
    citation: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evidence.evidence_uid"),
        nullable=False,
    )
    chunk_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("chunks.chunk_uid"),
        nullable=False,
    )
    artifact_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("artifacts.artifact_uid"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_ref: Mapped[str] = mapped_column(Text, nullable=False)


class ReportModuleModel(Base):
    """预设报告模块表。"""

    __tablename__ = "report_modules"
    __table_args__ = (
        Index("report_modules_parent_id_idx", "parent_id"),
        Index("report_modules_is_active_idx", "is_active"),
    )

    module_id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("report_modules.module_id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    section_template: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    coverage_questions: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PolicyDecisionModel(Base):
    """策略决策审计表。"""

    __tablename__ = "policy_decisions"
    __table_args__ = (Index("policy_decisions_request_id_idx", "request_id"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    decision_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    allow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    enforced: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    hitl: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    hitl_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolTraceModel(Base):
    """工具调用审计表。"""

    __tablename__ = "tool_traces"
    __table_args__ = (Index("tool_traces_tool_name_idx", "tool_name"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(Text)
    policy_decision_id: Mapped[str | None] = mapped_column(Text)


class ModelTraceModel(Base):
    """模型调用审计表。"""

    __tablename__ = "model_traces"
    __table_args__ = (Index("model_traces_model_idx", "model"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    trace_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(Text)
    policy_decision_id: Mapped[str | None] = mapped_column(Text)


class ReviewRequestModel(Base):
    """审查请求表。"""

    __tablename__ = "review_requests"
    __table_args__ = (Index("review_requests_status_idx", "status"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    review_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    resume_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntityTypeModel(Base):
    """实体类型表。"""

    __tablename__ = "entity_types"

    entity_type_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class EventTypeModel(Base):
    """事件类型表。"""

    __tablename__ = "event_types"

    event_type_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class EntityModel(Base):
    """实体表。"""

    __tablename__ = "entities"
    __table_args__ = (
        Index("entities_entity_type_id_idx", "entity_type_id"),
        Index("entities_geo_point_gist_idx", "geo_point", postgresql_using="gist"),
        Index("entities_geo_bbox_gist_idx", "geo_bbox", postgresql_using="gist"),
        CheckConstraint(
            "jsonb_typeof(attrs) = 'object'", name="entities_attrs_object_check"
        ),
    )

    entity_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    entity_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    entity_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity_types.entity_type_id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    attrs: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    geo_point: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326))
    geo_bbox: Mapped[object | None] = mapped_column(Geometry("POLYGON", srid=4326))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EntityAliasModel(Base):
    """实体别名表。"""

    __tablename__ = "entity_aliases"
    __table_args__ = (Index("entity_aliases_alias_idx", "alias"),)

    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.entity_id"),
        primary_key=True,
    )
    alias: Mapped[str] = mapped_column(Text, primary_key=True)


class EventModel(Base):
    """事件表。"""

    __tablename__ = "events"
    __table_args__ = (
        Index("events_event_type_id_idx", "event_type_id"),
        Index("events_time_start_idx", "time_start"),
        Index("events_geo_point_gist_idx", "geo_point", postgresql_using="gist"),
        Index("events_geo_bbox_gist_idx", "geo_bbox", postgresql_using="gist"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0", name="events_confidence_check"
        ),
        CheckConstraint(
            "time_end IS NULL OR time_start IS NULL OR time_end >= time_start",
            name="events_time_range_check",
        ),
        CheckConstraint(
            "jsonb_typeof(attrs) = 'object'", name="events_attrs_object_check"
        ),
    )

    event_id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    event_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    event_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_types.event_type_id"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    time_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_name: Mapped[str | None] = mapped_column(Text)
    geo_point: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326))
    geo_bbox: Mapped[object | None] = mapped_column(Geometry("POLYGON", srid=4326))
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.0")
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    attrs: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EventParticipantModel(Base):
    """事件参与方表。"""

    __tablename__ = "event_participants"
    __table_args__ = (Index("event_participants_entity_id_idx", "entity_id"),)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.event_id"),
        primary_key=True,
    )
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.entity_id"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)


class EventEvidenceModel(Base):
    """事件证据关联表。"""

    __tablename__ = "event_evidence"
    __table_args__ = (Index("event_evidence_evidence_uid_idx", "evidence_uid"),)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.event_id"),
        primary_key=True,
    )
    evidence_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evidence.evidence_uid"),
        primary_key=True,
    )


class EntityEvidenceModel(Base):
    """实体证据关联表。"""

    __tablename__ = "entity_evidence"
    __table_args__ = (Index("entity_evidence_evidence_uid_idx", "evidence_uid"),)

    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entities.entity_id"),
        primary_key=True,
    )
    evidence_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evidence.evidence_uid"),
        primary_key=True,
    )


class StormOutlineModel(Base):
    """STORM 大纲表。"""

    __tablename__ = "storm_outlines"
    __table_args__ = (Index("storm_outlines_task_id_idx", "task_id"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    outline_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("tasks.task_id"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_checklist: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StormSectionModel(Base):
    """STORM 章节表。"""

    __tablename__ = "storm_sections"
    __table_args__ = (Index("storm_sections_outline_uid_idx", "outline_uid"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    section_uid: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    outline_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("storm_outlines.outline_uid"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_item_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    depth_policy: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StormSectionIterationModel(Base):
    """章节研究迭代表。"""

    __tablename__ = "storm_section_iterations"
    __table_args__ = (Index("storm_section_iterations_section_uid_idx", "section_uid"),)

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    section_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("storm_sections.section_uid"),
        nullable=False,
    )
    iteration_index: Mapped[int] = mapped_column(Integer, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StormSectionEvidenceModel(Base):
    """章节证据关联表。"""

    __tablename__ = "storm_section_evidence"
    __table_args__ = (Index("storm_section_evidence_evidence_uid_idx", "evidence_uid"),)

    section_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("storm_sections.section_uid"),
        primary_key=True,
    )
    evidence_uid: Mapped[str] = mapped_column(
        Text,
        ForeignKey("evidence.evidence_uid"),
        primary_key=True,
    )


class CheckpointModel(Base):
    """检查点表。"""

    __tablename__ = "checkpoints"
    __table_args__ = (
        Index("ix_checkpoints_thread_created", "thread_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    state_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    step: Mapped[str] = mapped_column(Text, nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    checkpoint_meta: Mapped[dict | None] = mapped_column(JSONB)
