"""审计回放服务。

- 按 trace_id 回放
- 时间线视图数据
- 证据链可视化数据
- 重跑支持（可选）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from baize_core.schemas.audit import ModelTrace, PolicyDecisionRecord, ToolTrace
from baize_core.schemas.evidence import AnchorType, ChunkAnchor, Report, ReportReference
from baize_core.storage import models
from baize_core.storage.postgres import PostgresStore


@dataclass
class TimelineEvent:
    """时间线事件。"""

    event_id: str
    event_type: str  # tool_call, model_call, policy_decision
    timestamp: datetime
    duration_ms: int
    success: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceNode:
    """证据链节点。"""

    node_id: str
    node_type: str  # artifact, chunk, evidence, claim
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceEdge:
    """证据链边。"""

    from_node: str
    to_node: str
    relation: str  # contains, supports, conflicts


@dataclass
class EvidenceChainView:
    """证据链可视化数据。"""

    nodes: list[EvidenceNode]
    edges: list[EvidenceEdge]


@dataclass
class ReplayResult:
    """回放结果。"""

    task_id: str
    trace_id: str | None
    reports: list[Report]
    tool_traces: list[ToolTrace]
    policy_decisions: list[PolicyDecisionRecord]
    model_traces: list[ModelTrace]
    timeline: list[TimelineEvent]
    evidence_chain: EvidenceChainView | None = None
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayService:
    """审计回放服务。"""

    store: PostgresStore

    async def replay_task(self, task_id: str) -> dict[str, object]:
        """按任务回放审计链路。"""

        reports = await self._load_reports(task_id)
        tool_traces = await self._load_tool_traces(task_id)
        policy_decisions = await self._load_policy_decisions(task_id)
        model_traces = await self._load_model_traces(task_id)
        return {
            "task_id": task_id,
            "reports": reports,
            "tool_traces": tool_traces,
            "policy_decisions": policy_decisions,
            "model_traces": model_traces,
        }

    async def replay_full(self, task_id: str) -> ReplayResult:
        """完整回放任务（含时间线和证据链）。

        Args:
            task_id: 任务 ID

        Returns:
            完整回放结果
        """
        # 加载基础数据
        reports = await self._load_reports(task_id)
        tool_traces = await self._load_tool_traces(task_id)
        policy_decisions = await self._load_policy_decisions(task_id)
        model_traces = await self._load_model_traces(task_id)

        # 获取 trace_id
        trace_id = None
        if model_traces:
            trace_id = (
                model_traces[0].trace_id.split("_")[0]
                if "_" in model_traces[0].trace_id
                else None
            )

        # 构建时间线
        timeline = self._build_timeline(tool_traces, model_traces, policy_decisions)

        # 构建证据链
        evidence_chain = await self._build_evidence_chain(task_id)

        # 计算摘要
        summary = self._compute_summary(
            tool_traces=tool_traces,
            model_traces=model_traces,
            policy_decisions=policy_decisions,
        )

        return ReplayResult(
            task_id=task_id,
            trace_id=trace_id,
            reports=reports,
            tool_traces=tool_traces,
            policy_decisions=policy_decisions,
            model_traces=model_traces,
            timeline=timeline,
            evidence_chain=evidence_chain,
            summary=summary,
        )

    async def replay_by_trace_id(self, trace_id: str) -> ReplayResult | None:
        """按 trace_id 回放。

        Args:
            trace_id: 追踪 ID

        Returns:
            回放结果，未找到返回 None
        """
        # 从 model_traces 中查找 task_id
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.ModelTraceModel.task_id)
                .where(models.ModelTraceModel.trace_id.like(f"{trace_id}%"))
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            task_id = row

        return await self.replay_full(task_id)

    def _build_timeline(
        self,
        tool_traces: list[ToolTrace],
        model_traces: list[ModelTrace],
        policy_decisions: list[PolicyDecisionRecord],
    ) -> list[TimelineEvent]:
        """构建时间线视图。"""
        events: list[TimelineEvent] = []

        # 添加工具调用事件
        for tool_trace in tool_traces:
            events.append(
                TimelineEvent(
                    event_id=tool_trace.trace_id,
                    event_type="tool_call",
                    timestamp=tool_trace.started_at or datetime.now(UTC),
                    duration_ms=tool_trace.duration_ms,
                    success=tool_trace.success,
                    summary=f"工具调用: {tool_trace.tool_name}",
                    details={
                        "tool_name": tool_trace.tool_name,
                        "error_type": tool_trace.error_type,
                        "error_message": tool_trace.error_message,
                    },
                )
            )

        # 添加模型调用事件
        for model_trace in model_traces:
            events.append(
                TimelineEvent(
                    event_id=model_trace.trace_id,
                    event_type="model_call",
                    timestamp=model_trace.started_at or datetime.now(UTC),
                    duration_ms=model_trace.duration_ms,
                    success=model_trace.success,
                    summary=f"模型调用: {model_trace.model} ({model_trace.stage})",
                    details={
                        "model": model_trace.model,
                        "stage": model_trace.stage,
                        "error_type": model_trace.error_type,
                        "error_message": model_trace.error_message,
                    },
                )
            )

        # 添加策略决策事件
        for decision in policy_decisions:
            events.append(
                TimelineEvent(
                    event_id=decision.decision_id,
                    event_type="policy_decision",
                    timestamp=decision.created_at or datetime.now(UTC),
                    duration_ms=0,
                    success=decision.allow,
                    summary=f"策略决策: {'允许' if decision.allow else '拒绝'}",
                    details={
                        "reason": decision.reason,
                        "enforced": decision.enforced,
                        "hitl": decision.hitl,
                    },
                )
            )

        # 按时间排序
        events.sort(key=lambda e: e.timestamp)
        return events

    async def _build_evidence_chain(self, task_id: str) -> EvidenceChainView | None:
        """构建证据链可视化数据。"""
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []

        async with self.store.session_factory() as session:
            # 加载 Evidence
            evidence_query = select(models.EvidenceModel)
            task_id_column = getattr(models.EvidenceModel, "task_id", None)
            if task_id_column is not None:
                evidence_query = evidence_query.where(task_id_column == task_id)
            evidence_result = await session.execute(evidence_query)
            evidence_rows = evidence_result.scalars().all()

            if not evidence_rows:
                return None

            # 收集相关的 chunk_uid 和 artifact_uid
            chunk_uids = {e.chunk_uid for e in evidence_rows if e.chunk_uid}

            # 加载 Chunks
            chunk_map: dict[str, Any] = {}
            if chunk_uids:
                chunk_result = await session.execute(
                    select(models.ChunkModel).where(
                        models.ChunkModel.chunk_uid.in_(chunk_uids)
                    )
                )
                for chunk in chunk_result.scalars().all():
                    chunk_map[chunk.chunk_uid] = chunk

            # 收集 artifact_uid
            artifact_uids = {
                c.artifact_uid for c in chunk_map.values() if c.artifact_uid
            }

            # 加载 Artifacts
            artifact_map: dict[str, Any] = {}
            if artifact_uids:
                artifact_result = await session.execute(
                    select(models.ArtifactModel).where(
                        models.ArtifactModel.artifact_uid.in_(artifact_uids)
                    )
                )
                for artifact in artifact_result.scalars().all():
                    artifact_map[artifact.artifact_uid] = artifact

            # 构建节点
            for artifact_uid, artifact in artifact_map.items():
                nodes.append(
                    EvidenceNode(
                        node_id=artifact_uid,
                        node_type="artifact",
                        label=f"Artifact: {artifact.origin_url[:30]}..."
                        if artifact.origin_url
                        else artifact_uid[:12],
                        metadata={
                            "origin_tool": artifact.origin_tool,
                            "fetched_at": artifact.fetched_at.isoformat()
                            if artifact.fetched_at
                            else None,
                        },
                    )
                )

            for chunk_uid, chunk in chunk_map.items():
                nodes.append(
                    EvidenceNode(
                        node_id=chunk_uid,
                        node_type="chunk",
                        label=f"Chunk: {chunk.text[:30]}..."
                        if chunk.text
                        else chunk_uid[:12],
                        metadata={
                            "artifact_uid": chunk.artifact_uid,
                        },
                    )
                )
                # 添加边：Artifact -> Chunk
                if chunk.artifact_uid in artifact_map:
                    edges.append(
                        EvidenceEdge(
                            from_node=chunk.artifact_uid,
                            to_node=chunk_uid,
                            relation="contains",
                        )
                    )

            for evidence in evidence_rows:
                nodes.append(
                    EvidenceNode(
                        node_id=evidence.evidence_uid,
                        node_type="evidence",
                        label=f"Evidence: {evidence.summary[:30]}..."
                        if evidence.summary
                        else evidence.evidence_uid[:12],
                        metadata={
                            "confidence": getattr(evidence, "confidence", None),
                            "extraction_method": getattr(
                                evidence, "extraction_method", None
                            ),
                        },
                    )
                )
                # 添加边：Chunk -> Evidence
                if evidence.chunk_uid in chunk_map:
                    edges.append(
                        EvidenceEdge(
                            from_node=evidence.chunk_uid,
                            to_node=evidence.evidence_uid,
                            relation="supports",
                        )
                    )

        return EvidenceChainView(nodes=nodes, edges=edges)

    def _compute_summary(
        self,
        tool_traces: list[ToolTrace],
        model_traces: list[ModelTrace],
        policy_decisions: list[PolicyDecisionRecord],
    ) -> dict[str, Any]:
        """计算回放摘要。"""
        tool_success = sum(1 for t in tool_traces if t.success)
        model_success = sum(1 for t in model_traces if t.success)
        policy_allowed = sum(1 for p in policy_decisions if p.allow)

        total_duration = sum(t.duration_ms for t in tool_traces) + sum(
            t.duration_ms for t in model_traces
        )

        return {
            "tool_calls": {
                "total": len(tool_traces),
                "success": tool_success,
                "failure": len(tool_traces) - tool_success,
            },
            "model_calls": {
                "total": len(model_traces),
                "success": model_success,
                "failure": len(model_traces) - model_success,
            },
            "policy_decisions": {
                "total": len(policy_decisions),
                "allowed": policy_allowed,
                "denied": len(policy_decisions) - policy_allowed,
            },
            "total_duration_ms": total_duration,
        }

    async def get_rerun_config(self, task_id: str) -> dict[str, Any] | None:
        """获取重跑配置（用于重新执行任务）。

        Args:
            task_id: 任务 ID

        Returns:
            重跑配置，未找到返回 None
        """
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.TaskModel).where(models.TaskModel.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            return {
                "task_id": task_id,
                "query": task.objective,
                "task_type": None,
                "config": {
                    "constraints": task.constraints,
                    "time_window": task.time_window,
                    "region": task.region,
                    "sensitivity": task.sensitivity,
                },
                "original_created_at": task.created_at.isoformat()
                if task.created_at
                else None,
            }

    async def _load_reports(self, task_id: str) -> list[Report]:
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.ReportModel).where(models.ReportModel.task_id == task_id)
            )
            report_rows = result.scalars().all()
            if not report_rows:
                return []
            report_uids = [row.report_uid for row in report_rows]
            references_result = await session.execute(
                select(models.ReportReferenceModel).where(
                    models.ReportReferenceModel.report_uid.in_(report_uids)
                )
            )
            references = references_result.scalars().all()
            reference_map: dict[str, list[ReportReference]] = {}
            for ref in references:
                reference_map.setdefault(ref.report_uid, []).append(
                    ReportReference(
                        citation=ref.citation,
                        evidence_uid=ref.evidence_uid,
                        chunk_uid=ref.chunk_uid,
                        artifact_uid=ref.artifact_uid,
                        source_url=ref.source_url,
                        anchor=ChunkAnchor(
                            type=AnchorType(ref.anchor_type),
                            ref=ref.anchor_ref,
                        ),
                    )
                )
            return [
                Report(
                    report_uid=row.report_uid,
                    task_id=row.task_id,
                    outline_uid=row.outline_uid,
                    report_type=row.report_type,
                    content_ref=row.content_ref,
                    references=reference_map.get(row.report_uid, []),
                    conflict_notes=row.conflict_notes,
                )
                for row in report_rows
            ]

    async def _load_tool_traces(self, task_id: str) -> list[ToolTrace]:
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.ToolTraceModel).where(
                    models.ToolTraceModel.task_id == task_id
                )
            )
            rows = result.scalars().all()
            return [
                ToolTrace(
                    trace_id=row.trace_id,
                    tool_name=row.tool_name,
                    task_id=row.task_id,
                    started_at=row.started_at,
                    duration_ms=row.duration_ms,
                    success=row.success,
                    error_type=row.error_type,
                    error_message=row.error_message,
                    result_ref=row.result_ref,
                    policy_decision_id=row.policy_decision_id,
                )
                for row in rows
            ]

    async def _load_policy_decisions(self, task_id: str) -> list[PolicyDecisionRecord]:
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.PolicyDecisionModel).where(
                    models.PolicyDecisionModel.task_id == task_id
                )
            )
            rows = result.scalars().all()
            return [
                PolicyDecisionRecord(
                    decision_id=row.decision_id,
                    request_id=row.request_id,
                    task_id=row.task_id,
                    action=row.action,
                    stage=row.stage,
                    allow=row.allow,
                    reason=row.reason,
                    enforced=row.enforced or {},
                    hitl=row.hitl or {},
                    hitl_required=row.hitl_required,
                    created_at=row.created_at,
                    decided_at=row.decided_at,
                )
                for row in rows
            ]

    async def _load_model_traces(self, task_id: str) -> list[ModelTrace]:
        async with self.store.session_factory() as session:
            result = await session.execute(
                select(models.ModelTraceModel).where(
                    models.ModelTraceModel.task_id == task_id
                )
            )
            rows = result.scalars().all()
            return [
                ModelTrace(
                    trace_id=row.trace_id,
                    model=row.model,
                    stage=row.stage,
                    task_id=row.task_id,
                    started_at=row.started_at,
                    duration_ms=row.duration_ms,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    success=row.success,
                    error_type=row.error_type,
                    error_message=row.error_message,
                    result_ref=row.result_ref,
                    policy_decision_id=row.policy_decision_id,
                )
                for row in rows
            ]
