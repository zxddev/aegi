"""编排入口（Phase 0 实现）。"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import uuid4

from baize_core.audit.recorder import AuditRecorder
from baize_core.orchestration.review import ReviewAgent
from baize_core.policy.engine import PolicyEngine
from baize_core.schemas.audit import ToolTrace
from baize_core.schemas.entity_event import (
    Entity,
    EntityType,
    Event,
    EventType,
    GeoBBox,
)
from baize_core.schemas.evidence import (
    Artifact,
    Chunk,
    Claim,
    Evidence,
    Report,
    generate_deterministic_uid,
)
from baize_core.schemas.mcp_toolchain import (
    ArchiveUrlOutput,
    DocParseOutput,
    MetaSearchOutput,
    WebCrawlOutput,
)
from baize_core.schemas.policy import (
    ActionType,
    PlannedCost,
    PolicyPayload,
    PolicyRequest,
    RuntimeBudget,
    StageType,
)
from baize_core.schemas.review import ReviewResult
from baize_core.schemas.review_request import (
    ReviewCreateRequest,
    ReviewDecisionInput,
    ReviewRequest,
)
from baize_core.schemas.storm import ReportConfig
from baize_core.schemas.task import TaskResponse, TaskSpec
from baize_core.storage.minio_store import MinioArtifactStore
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.runner import ToolRunner


@dataclass
class Orchestrator:
    """最小编排器。"""

    policy_engine: PolicyEngine
    audit_recorder: AuditRecorder
    reviewer: ReviewAgent
    store: PostgresStore
    artifact_store: MinioArtifactStore
    tool_runner: ToolRunner
    review_graph: AsyncGraph | None = None
    ooda_graph: AsyncGraph | None = None
    storm_graph: AsyncGraph | None = None

    async def submit_task(self, task: TaskSpec) -> TaskResponse:
        """提交任务。"""

        return await self.store.create_task(task)

    async def delete_task_data(self, task_id: str) -> dict[str, int]:
        """按任务清理所有关联数据（软删除）。"""

        trace_id = f"trace_{uuid4().hex}"
        started_at = time.time()
        try:
            result = await self.store.soft_delete_task_data(task_id)
            duration_ms = int((time.time() - started_at) * 1000)
            await self.audit_recorder.record_tool_trace(
                ToolTrace(
                    trace_id=trace_id,
                    tool_name="data_cleanup",
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=True,
                    result_ref=json.dumps(result, ensure_ascii=False)[:256],
                )
            )
            return result
        except Exception as exc:  # pylint: disable=broad-exception-caught
            duration_ms = int((time.time() - started_at) * 1000)
            await self.audit_recorder.record_tool_trace(
                ToolTrace(
                    trace_id=trace_id,
                    tool_name="data_cleanup",
                    task_id=task_id,
                    duration_ms=duration_ms,
                    success=False,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            raise

    async def review_output(
        self,
        *,
        claims: list[Claim],
        evidence: list[Evidence],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        report: Report | None = None,
    ) -> ReviewResult:
        """调用审查子 agent。"""

        await self.store.store_evidence_chain(
            artifacts=artifacts,
            chunks=chunks,
            evidence_items=evidence,
            claims=claims,
        )
        if report is not None:
            await self.store.store_report(report)

        if self.review_graph is not None:
            state = {
                "claims": claims,
                "evidence": evidence,
                "chunks": chunks,
                "artifacts": artifacts,
                "report": report,
                "review": None,
            }
            result = await self.review_graph.ainvoke(state)
            review = result.get("review")
            if not isinstance(review, ReviewResult):
                raise ValueError("审查结果类型不正确")
            return review
        return self.reviewer.review(
            claims=claims,
            evidence=evidence,
            chunks=chunks,
            artifacts=artifacts,
            report=report,
        )

    async def run_ooda(
        self,
        *,
        task: TaskSpec,
        claims: list[Claim],
        evidence: list[Evidence],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        report: Report | None = None,
    ) -> ReviewResult:
        """运行 OODA 子图（占位）。"""

        if self.ooda_graph is None:
            return await self.review_output(
                claims=claims,
                evidence=evidence,
                chunks=chunks,
                artifacts=artifacts,
                report=report,
            )
        state = {
            "task": task,
            "claims": claims,
            "evidence": evidence,
            "chunks": chunks,
            "artifacts": artifacts,
            "report": report,
            "review": None,
        }
        result = await self.ooda_graph.ainvoke(state)
        review = result.get("review")
        if not isinstance(review, ReviewResult):
            raise ValueError("审查结果类型不正确")
        return review

    async def run_storm(
        self,
        *,
        task: TaskSpec,
        report_config: ReportConfig,
    ) -> dict[str, object]:
        """运行 STORM 研究流程。"""

        if self.storm_graph is None:
            raise RuntimeError("STORM 图未加载")
        await self.store.create_task(task)
        state = {
            "task": task,
            "report_config": report_config,
            "outline": None,
            "research": None,
            "report": None,
            "report_record": None,
            "evidence": [],
            "chunks": [],
            "artifacts": [],
            "review": None,
        }
        return await self.storm_graph.ainvoke(state)

    async def enforce_export_policy(self, *, task_id: str) -> None:
        """执行导出策略校验。"""

        request = PolicyRequest(
            request_id=str(uuid4()),
            action=ActionType.EXPORT,
            stage=StageType.SYNTHESIS,
            task_id=task_id,
            planned_cost=PlannedCost(token_estimate=0, tool_timeout_ms=0),
            payload=PolicyPayload(),
            runtime=RuntimeBudget(
                token_budget_remaining=0,
                model_calls_remaining=0,
                tool_calls_remaining=0,
                deadline_ms_remaining=0,
            ),
        )
        decision = self.policy_engine.evaluate(request)
        await self.audit_recorder.record_policy_decision(request, decision)
        if decision.hitl.required:
            review = await self.store.create_review_request(
                ReviewCreateRequest(task_id=task_id, reason=decision.hitl.reason)
            )
            raise RuntimeError(f"需要人工复核: {review.review_id}")
        if not decision.allow:
            raise RuntimeError(f"策略拒绝导出: {decision.reason}")

    async def create_review(self, payload: ReviewCreateRequest) -> ReviewRequest:
        """创建 HITL 审查请求。"""

        return await self.store.create_review_request(payload)

    async def get_review(self, review_id: str) -> ReviewRequest:
        """获取 HITL 审查状态。"""

        return await self.store.get_review_request(review_id)

    async def approve_review(
        self, review_id: str, decision: ReviewDecisionInput
    ) -> ReviewRequest:
        """通过审查。"""

        return await self.store.approve_review(review_id)

    async def reject_review(
        self, review_id: str, decision: ReviewDecisionInput
    ) -> ReviewRequest:
        """拒绝审查。"""

        return await self.store.reject_review(review_id, decision.reason)

    async def upload_artifact(
        self,
        *,
        payload_base64: str,
        source_url: str | None,
        mime_type: str,
        fetch_trace_id: str | None,
        license_note: str | None,
    ) -> Artifact:
        """上传 Artifact 并落库。"""

        raw_bytes = base64.b64decode(payload_base64, validate=True)
        content_sha = sha256(raw_bytes).hexdigest()
        artifact_uid = generate_deterministic_uid(
            "art", [source_url or "", content_sha, mime_type]
        )
        storage_ref = f"{artifact_uid}/{content_sha}"
        await self.artifact_store.ensure_bucket()
        await self.artifact_store.put_base64(
            object_name=storage_ref,
            payload_base64=payload_base64,
            content_type=mime_type,
        )
        artifact = Artifact(
            artifact_uid=artifact_uid,
            source_url=source_url,
            fetched_at=datetime.now(UTC),
            content_sha256=content_sha,
            mime_type=mime_type,
            storage_ref=storage_ref,
            origin_tool="upload",
            fetch_trace_id=fetch_trace_id,
            license_note=license_note,
        )
        await self.store.store_artifacts([artifact])
        return artifact

    async def store_entities(self, entities: list[Entity]) -> list[str]:
        """写入实体。"""

        await self.store.store_entities(entities)
        return [entity.entity_uid for entity in entities]

    async def get_entity(self, entity_uid: str) -> Entity | None:
        """读取实体。"""

        return await self.store.get_entity_by_uid(entity_uid)

    async def list_entities(
        self,
        *,
        entity_types: list[EntityType] | None,
        bbox: GeoBBox | None,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        """按条件读取实体列表。"""

        return await self.store.list_entities(
            entity_types=entity_types,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )

    async def store_events(self, events: list[Event]) -> list[str]:
        """写入事件。"""

        await self.store.store_events(events)
        return [event.event_uid for event in events]

    async def get_event(self, event_uid: str) -> Event | None:
        """读取事件。"""

        return await self.store.get_event_by_uid(event_uid)

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
        """按条件读取事件列表。"""

        return await self.store.list_events(
            event_types=event_types,
            time_start=time_start,
            time_end=time_end,
            bbox=bbox,
            limit=limit,
            offset=offset,
        )

    async def ingest_toolchain(
        self,
        *,
        task_id: str,
        query: str,
        max_results: int,
        language: str,
        time_range: str,
        max_depth: int,
        max_pages: int,
        obey_robots_txt: bool,
        timeout_ms: int,
        chunk_size: int,
        chunk_overlap: int,
    ) -> tuple[list[str], list[str], list[str]]:
        """运行 MCP 工具链并写入证据链。"""

        search_payload: dict[str, object] = {
            "query": query,
            "max_results": max_results,
            "language": language,
            "time_range": time_range,
        }
        search_response = await self.tool_runner.run_mcp(
            tool_name="meta_search",
            tool_input=search_payload,
            stage=StageType.OBSERVE,
            task_id=task_id,
        )
        search_output = MetaSearchOutput.model_validate(search_response)
        if len(search_output.results) > max_results:
            raise ValueError("meta_search 返回结果数量超过限制")

        artifacts: list[Artifact] = []
        chunks: list[Chunk] = []
        evidence_items: list[Evidence] = []
        crawl_artifact_uids: set[str] = set()
        for result in search_output.results:
            crawl_payload: dict[str, object] = {
                "url": result.url,
                "max_depth": max_depth,
                "max_pages": max_pages,
                "obey_robots_txt": obey_robots_txt,
                "timeout_ms": timeout_ms,
            }
            crawl_response = await self.tool_runner.run_mcp(
                tool_name="web_crawl",
                tool_input=crawl_payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            crawl_output = WebCrawlOutput.model_validate(crawl_response)
            crawl_output.artifact.origin_tool = "web_crawl"
            artifacts.append(crawl_output.artifact)
            await self.store.store_artifacts([crawl_output.artifact])
            crawl_artifact_uids.add(crawl_output.artifact.artifact_uid)

            archive_payload: dict[str, object] = {"url": result.url}
            archive_response = await self.tool_runner.run_mcp(
                tool_name="archive_url",
                tool_input=archive_payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            archive_output = ArchiveUrlOutput.model_validate(archive_response)
            archive_output.artifact.origin_tool = "archive_url"
            artifacts.append(archive_output.artifact)
            await self.store.store_artifacts([archive_output.artifact])

            parse_payload: dict[str, object] = {
                "artifact_uid": archive_output.artifact.artifact_uid,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }
            parse_response = await self.tool_runner.run_mcp(
                tool_name="doc_parse",
                tool_input=parse_payload,
                stage=StageType.OBSERVE,
                task_id=task_id,
            )
            parse_output = DocParseOutput.model_validate(parse_response)
            for chunk in parse_output.chunks:
                if chunk.artifact_uid != archive_output.artifact.artifact_uid:
                    raise ValueError("解析结果 Artifact 不一致")
            chunks.extend(parse_output.chunks)
            for chunk in parse_output.chunks:
                evidence_items.append(
                    Evidence(
                        chunk_uid=chunk.chunk_uid,
                        source=result.source,
                        uri=result.url,
                        collected_at=archive_output.artifact.fetched_at,
                        base_credibility=result.score,
                        tags=[f"source:{result.source}"],
                        summary=result.title,
                    )
                )

        archive_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.artifact_uid not in crawl_artifact_uids
        ]
        await self.store.store_evidence_chain(
            artifacts=archive_artifacts,
            chunks=chunks,
            evidence_items=evidence_items,
            claims=[],
        )
        return (
            [artifact.artifact_uid for artifact in artifacts],
            [chunk.chunk_uid for chunk in chunks],
            [evidence.evidence_uid for evidence in evidence_items],
        )


class AsyncGraph(Protocol):
    """异步图执行协议。"""

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        """执行图。"""
        ...
