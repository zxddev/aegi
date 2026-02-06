"""API 请求模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.schemas.entity_event import Entity, Event
from baize_core.schemas.evidence import Artifact, Chunk, Claim, Evidence, Report
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.storm import ReportConfig
from baize_core.schemas.task import TaskSpec


class ReportExportRequest(BaseModel):
    """报告导出请求。"""

    task: TaskSpec | None = None
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    report: Report | None = None


class ArtifactUploadRequest(BaseModel):
    """Artifact 上传请求。"""

    payload_base64: str = Field(min_length=1)
    source_url: str | None = None
    mime_type: str = Field(min_length=1)
    fetch_trace_id: str | None = None
    license_note: str | None = None


class EntityBatchRequest(BaseModel):
    """实体批量写入请求。"""

    entities: list[Entity] = Field(min_length=1)


class EntityBatchResponse(BaseModel):
    """实体批量写入响应。"""

    entity_uids: list[str] = Field(default_factory=list)


class EventBatchRequest(BaseModel):
    """事件批量写入请求。"""

    events: list[Event] = Field(min_length=1)


class EventBatchResponse(BaseModel):
    """事件批量写入响应。"""

    event_uids: list[str] = Field(default_factory=list)


class ToolchainIngestRequest(BaseModel):
    """MCP 工具链写入请求。"""

    task_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    max_results: int = Field(default=10, ge=1, le=50)
    language: str = Field(default="auto", min_length=1)
    time_range: str = Field(default="all", min_length=1)
    max_depth: int = Field(default=1, ge=1, le=5)
    max_pages: int = Field(default=10, ge=1, le=50)
    obey_robots_txt: bool = True
    timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)


class ToolchainIngestResponse(BaseModel):
    """MCP 工具链写入响应。"""

    artifact_uids: list[str] = Field(default_factory=list)
    chunk_uids: list[str] = Field(default_factory=list)
    evidence_uids: list[str] = Field(default_factory=list)


class StormRunRequest(BaseModel):
    """STORM 研究请求。"""

    task: TaskSpec
    report_config: ReportConfig


class StormRunResponse(BaseModel):
    """STORM 研究响应。"""

    outline_uid: str
    report_uid: str
    report_ref: str
    review: ReviewResult


class ReplayResponse(BaseModel):
    """审计回放响应。"""

    task_id: str = Field(min_length=1)
    reports: list[Report] = Field(default_factory=list)
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    policy_decisions: list[PolicyDecisionRecord] = Field(default_factory=list)
    model_traces: list[ModelTrace] = Field(default_factory=list)


class AuditQueryRequest(BaseModel):
    """审计查询请求。"""

    # 时间范围
    start_time: str | None = Field(default=None, description="开始时间（ISO 格式）")
    end_time: str | None = Field(default=None, description="结束时间（ISO 格式）")

    # 过滤条件
    task_id: str | None = Field(default=None, description="任务 ID")
    tool_name: str | None = Field(default=None, description="工具名称")
    model_name: str | None = Field(default=None, description="模型名称")
    success: bool | None = Field(default=None, description="是否成功")

    # 分页
    limit: int = Field(default=100, ge=1, le=1000, description="返回数量限制")
    offset: int = Field(default=0, ge=0, description="偏移量")

    # 排序
    order_by: str = Field(default="created_at", description="排序字段")
    order_desc: bool = Field(default=True, description="是否降序")


class AuditQueryResponse(BaseModel):
    """审计查询响应。"""

    tool_traces: list[ToolTrace] = Field(default_factory=list)
    model_traces: list[ModelTrace] = Field(default_factory=list)
    policy_decisions: list[PolicyDecisionRecord] = Field(default_factory=list)
    total_count: int = Field(default=0, description="总记录数")
    has_more: bool = Field(default=False, description="是否有更多记录")


class AuditSummaryResponse(BaseModel):
    """审计摘要响应。"""

    # 时间范围
    start_time: str | None = None
    end_time: str | None = None

    # 工具调用统计
    tool_calls_total: int = Field(default=0, description="工具调用总数")
    tool_calls_success: int = Field(default=0, description="成功的工具调用数")
    tool_calls_failed: int = Field(default=0, description="失败的工具调用数")
    tool_success_rate: float = Field(default=0.0, description="工具调用成功率")

    # 模型调用统计
    model_calls_total: int = Field(default=0, description="模型调用总数")
    model_calls_success: int = Field(default=0, description="成功的模型调用数")
    model_calls_failed: int = Field(default=0, description="失败的模型调用数")
    model_success_rate: float = Field(default=0.0, description="模型调用成功率")

    # Token 统计
    total_input_tokens: int = Field(default=0, description="总输入 token 数")
    total_output_tokens: int = Field(default=0, description="总输出 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")

    # 策略统计
    policy_decisions_total: int = Field(default=0, description="策略决策总数")
    policy_allows: int = Field(default=0, description="允许的策略决策数")
    policy_denies: int = Field(default=0, description="拒绝的策略决策数")

    # 按工具/模型细分
    tool_breakdown: dict[str, int] = Field(
        default_factory=dict, description="按工具名称细分的调用数"
    )
    model_breakdown: dict[str, int] = Field(
        default_factory=dict, description="按模型名称细分的调用数"
    )

    # 错误类型统计
    error_breakdown: dict[str, int] = Field(
        default_factory=dict, description="按错误类型细分的数量"
    )


class GatewayToolTrace(BaseModel):
    """MCP Gateway 工具审计记录。"""

    trace_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    started_at: datetime | None = None
    duration_ms: int | None = None
    success: bool | None = None
    error_type: str | None = None
    error_message: str | None = None
    result_ref: str | None = None
    policy_decision_id: str | None = None
    caller_trace_id: str | None = None
    caller_policy_decision_id: str | None = None


class AuditTraceChainResponse(BaseModel):
    """按 trace_id 查询的审计链路响应。"""

    trace_id: str = Field(min_length=1)
    local_tool_trace: ToolTrace | None = None
    gateway_tool_trace: GatewayToolTrace | None = None


class AuditDecisionChainResponse(BaseModel):
    """按决策 ID 查询的审计链路响应。"""

    decision_id: str = Field(min_length=1)
    local_tool_traces: list[ToolTrace] = Field(default_factory=list)
    gateway_tool_traces: list[GatewayToolTrace] = Field(default_factory=list)


class AuditIntegrityCheckRequest(BaseModel):
    """审计链路完整性校验请求。"""

    task_id: str = Field(min_length=1)


class AuditIntegrityIssue(BaseModel):
    """审计链路问题。"""

    trace_id: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    detail: str | None = None


class AuditIntegrityTraceReport(BaseModel):
    """单条工具调用的链路完整性状态。"""

    trace_id: str = Field(min_length=1)
    local_tool_trace: ToolTrace
    gateway_tool_trace: GatewayToolTrace | None = None
    ok: bool = True
    issues: list[AuditIntegrityIssue] = Field(default_factory=list)


class AuditIntegrityCheckResponse(BaseModel):
    """审计链路完整性校验响应。"""

    task_id: str = Field(min_length=1)
    total_traces: int = 0
    matched_gateway_traces: int = 0
    broken_traces: int = 0
    ok: bool = True
    issues: list[AuditIntegrityIssue] = Field(default_factory=list)
    traces: list[AuditIntegrityTraceReport] = Field(default_factory=list)
