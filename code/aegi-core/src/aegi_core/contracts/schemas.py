# Author: msq
"""共享契约 Schema (Gate-0)。

来源: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
约束: 所有功能变更必须依赖共享契约；Foundation 必须预留多模态兼容字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from enum import Enum

from pydantic import BaseModel, Field

_T = TypeVar("_T")


# -- 多模态枚举 (task 4.1) ------------------------------------------------


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# -- 媒体时间范围 (task 4.2) -----------------------------------------------


class MediaTimeRange(BaseModel):
    start_ms: int | None = None
    end_ms: int | None = None


# -- 核心 Schema (task 1.1) ----------------------------------------------------


class SourceClaimV1(BaseModel):
    uid: str
    case_uid: str
    artifact_version_uid: str
    chunk_uid: str
    evidence_uid: str
    quote: str
    selectors: list[dict] = Field(default_factory=list)
    attributed_to: str | None = None
    modality: Modality | None = None
    segment_ref: str | None = None
    media_time_range: MediaTimeRange | None = None
    language: str | None = None
    original_quote: str | None = None
    translation: str | None = None
    translation_meta: dict | None = None
    created_at: datetime


class AssertionV1(BaseModel):
    uid: str
    case_uid: str
    kind: str
    value: dict = Field(default_factory=dict)
    source_claim_uids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    modality: Modality | None = None
    segment_ref: str | None = None
    media_time_range: MediaTimeRange | None = None
    created_at: datetime


class AssertionFeedbackCreate(BaseModel):
    """创建 Assertion 反馈。"""

    user_id: str
    verdict: Literal["agree", "disagree", "need_more_evidence", "partially_agree"]
    confidence_override: float | None = Field(default=None, ge=0.0, le=1.0)
    comment: str | None = Field(default=None, max_length=2000)
    suggested_value: dict[str, Any] | None = None


class AssertionFeedbackV1(BaseModel):
    """Assertion 反馈响应体。"""

    uid: str
    assertion_uid: str
    case_uid: str
    user_id: str
    verdict: str
    confidence_override: float | None = None
    comment: str | None = None
    suggested_value: dict[str, Any] | None = None
    created_at: datetime


class AssertionFeedbackSummary(BaseModel):
    """某个 Assertion 的反馈汇总。"""

    assertion_uid: str
    total_feedback: int
    agree_count: int
    disagree_count: int
    need_more_evidence_count: int
    partially_agree_count: int
    avg_confidence_override: float | None = None
    consensus: str


class CaseFeedbackStats(BaseModel):
    """某个 Case 的反馈统计。"""

    case_uid: str
    total_assertions: int
    assertions_with_feedback: int
    feedback_coverage: float
    overall_agreement_rate: float | None = None
    disputed_assertions: list[str] = Field(default_factory=list)


class HypothesisV1(BaseModel):
    uid: str
    case_uid: str
    label: str
    supporting_assertion_uids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    modality: Modality | None = None
    segment_ref: str | None = None
    media_time_range: MediaTimeRange | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime


class NarrativeV1(BaseModel):
    uid: str
    case_uid: str
    title: str
    assertion_uids: list[str] = Field(default_factory=list)
    hypothesis_uids: list[str] = Field(default_factory=list)
    modality: Modality | None = None
    segment_ref: str | None = None
    media_time_range: MediaTimeRange | None = None
    created_at: datetime


# -- 分页响应 -------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[_T]):
    items: list[_T]
    total: int
    offset: int
    limit: int


# -- 报告 Schema ------------------------------------------------------------


class ReportType(str, Enum):
    BRIEFING = "briefing"
    ACH_MATRIX = "ach_matrix"
    EVIDENCE_CHAIN = "evidence_chain"
    NARRATIVE = "narrative"
    QUALITY = "quality"


class ReportSectionV1(BaseModel):
    name: str
    title: str
    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ReportV1(BaseModel):
    uid: str
    case_uid: str
    report_type: str
    title: str
    sections: list[ReportSectionV1] = Field(default_factory=list)
    rendered_markdown: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime | None = None


class ReportSummaryV1(BaseModel):
    uid: str
    case_uid: str
    report_type: str
    title: str
    created_at: datetime | None = None


# -- KG 可视化 Schema -------------------------------------------------


class GraphNodeV1(BaseModel):
    uid: str
    name: str
    type: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    community_id: int | None = None
    centrality_score: float | None = None


class GraphEdgeV1(BaseModel):
    source_uid: str
    target_uid: str
    rel_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphDataResponse(BaseModel):
    nodes: list[GraphNodeV1]
    edges: list[GraphEdgeV1]
    node_count: int = 0
    edge_count: int = 0


class CommunityV1(BaseModel):
    community_id: int
    nodes: list[GraphNodeV1]
    size: int = 0


class CommunityResponse(BaseModel):
    communities: list[CommunityV1]
    algorithm: str
    modularity: float | None = None
    community_count: int = 0


class CentralityRankingV1(BaseModel):
    uid: str
    name: str
    type: str
    score: float


class CentralityResponse(BaseModel):
    rankings: list[CentralityRankingV1]
    algorithm: str


class GapAnalysisResponse(BaseModel):
    isolated_nodes: list[GraphNodeV1]
    weakly_connected_components: int = 0
    largest_component_size: int = 0
    density: float = 0.0
    relationship_type_distribution: list[dict[str, Any]] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


class TemporalEventV1(BaseModel):
    uid: str
    label: str
    event_type: str
    timestamp_ref: str | None = None
    related_entity_uid: str | None = None
    rel_type: str | None = None


class TemporalResponse(BaseModel):
    events: list[TemporalEventV1]
    entity_timelines: dict[str, list[TemporalEventV1]] = Field(default_factory=dict)
    time_range: dict[str, str | None] = Field(default_factory=dict)
    event_count: int = 0


class PathNodeV1(BaseModel):
    uid: str
    name: str
    type: str


class PathRelV1(BaseModel):
    source_uid: str
    target_uid: str
    rel_type: str


class PathV1(BaseModel):
    nodes: list[PathNodeV1]
    rels: list[PathRelV1]
    length: int = 0


class PathRequest(BaseModel):
    source_uid: str
    target_uid: str
    max_depth: int = 5
    rel_types: list[str] | None = None
    node_types: list[str] | None = None
    limit: int = 10


class PathResponse(BaseModel):
    paths: list[PathV1]
    source_uid: str
    target_uid: str
    path_count: int = 0
