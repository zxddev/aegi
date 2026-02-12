"""流水线进度和聊天的 SSE 流式端点。"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from aegi_core.api.deps import get_db_session, get_llm_client, get_neo4j_store
from aegi_core.services.pipeline_tracker import pipeline_tracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


# ── 请求 schema ───────────────────────────────────────────────


class RunStreamedRequest(BaseModel):
    playbook: str = "default"
    source_claim_uids: list[str] = Field(default_factory=list)


class ChatStreamRequest(BaseModel):
    message: str
    case_uid: str | None = None
    model: str | None = None
    max_tokens: int | None = None


# ── SSE 工具函数 ───────────────────────────────────────────────────


def _sse_event(data: dict, event: str | None = None) -> str:
    """格式化单个 SSE 事件。"""
    parts = []
    if event:
        parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


# ── 流水线 SSE ──────────────────────────────────────────────────


@router.post("/cases/{case_uid}/pipelines/run_streamed")
async def run_streamed(
    case_uid: str,
    body: RunStreamedRequest,
) -> StreamingResponse:
    """运行流水线 playbook 并通过 SSE 推送进度。"""
    run_id = f"run_{uuid4().hex[:12]}"

    async def _generate():
        from aegi_core.contracts.schemas import SourceClaimV1
        from aegi_core.services.pipeline_orchestrator import PipelineOrchestrator
        from aegi_core.services.stages.playbook import get_playbook

        llm = get_llm_client()
        neo4j = get_neo4j_store()
        orch = PipelineOrchestrator(llm=llm, neo4j_store=neo4j)

        pb = get_playbook(body.playbook)
        tracker = pipeline_tracker
        tracker.create_run(run_id, case_uid, body.playbook, pb.stages)

        # 构建 source claims（没提供 UID 就用空列表）
        source_claims: list[SourceClaimV1] = []
        if body.source_claim_uids:
            import sqlalchemy as sa
            from aegi_core.db.session import ENGINE
            from sqlalchemy.ext.asyncio import AsyncSession
            from aegi_core.db.models.source_claim import SourceClaim

            async with AsyncSession(ENGINE, expire_on_commit=False) as session:
                rows = (
                    (
                        await session.execute(
                            sa.select(SourceClaim).where(
                                SourceClaim.uid.in_(body.source_claim_uids)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for r in rows:
                    source_claims.append(
                        SourceClaimV1(
                            uid=r.uid,
                            case_uid=r.case_uid,
                            artifact_version_uid=r.artifact_version_uid,
                            chunk_uid=r.chunk_uid,
                            evidence_uid=r.evidence_uid,
                            quote=r.quote,
                            selectors=r.selectors,
                            attributed_to=r.attributed_to,
                            modality=r.modality,
                            created_at=r.created_at,
                        )
                    )

        completed_stages: list[str] = []

        async def _on_progress(stage: str, status: str, pct: float, msg: str) -> None:
            if status in ("success", "skipped") and stage not in completed_stages:
                completed_stages.append(stage)
            tracker.update(
                run_id,
                current_stage=stage,
                status="running",
                progress_pct=pct,
                message=msg,
                stages_completed=list(completed_stages),
            )
            evt = tracker.subscribe(run_id)
            evt.set()

        # 发送初始事件
        yield _sse_event(
            {
                "run_id": run_id,
                "status": "running",
                "current_stage": "",
                "progress_pct": 0,
                "stages_total": pb.stages,
            }
        )

        tracker.update(run_id, status="running")

        try:
            result = await orch.run_playbook(
                playbook_name=body.playbook,
                case_uid=case_uid,
                source_claims=source_claims,
                on_progress=_on_progress,
            )

            # 发送每个 stage 的结果
            completed = []
            for sr in result.stages:
                if sr.status != "skipped":
                    completed.append(sr.stage)
                pct = (len(completed) / len(pb.stages)) * 100 if pb.stages else 100
                yield _sse_event(
                    {
                        "run_id": run_id,
                        "status": "running",
                        "current_stage": sr.stage,
                        "stage_status": sr.status,
                        "progress_pct": round(pct, 1),
                        "stages_completed": list(completed),
                        "duration_ms": sr.duration_ms,
                    }
                )

            tracker.update(run_id, status="completed", progress_pct=100)
            yield _sse_event(
                {
                    "run_id": run_id,
                    "status": "completed",
                    "progress_pct": 100,
                    "total_duration_ms": result.total_duration_ms,
                },
                event="done",
            )
        except Exception as exc:
            tracker.update(run_id, status="failed", message=str(exc))
            yield _sse_event(
                {"run_id": run_id, "status": "failed", "error": str(exc)},
                event="error",
            )
        finally:
            # 保留状态一会儿给迟到的订阅者，然后清理
            await asyncio.sleep(60)
            tracker.cleanup(run_id)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cases/{case_uid}/pipelines/runs/{run_id}/stream")
async def subscribe_run(case_uid: str, run_id: str) -> StreamingResponse:
    """订阅已有流水线运行的 SSE 进度推送。"""
    state = pipeline_tracker.get(run_id)
    if state is None:
        return StreamingResponse(
            iter([_sse_event({"error": "run not found"}, event="error")]),
            media_type="text/event-stream",
        )

    async def _generate():
        while True:
            s = pipeline_tracker.get(run_id)
            if s is None:
                break
            yield _sse_event(
                {
                    "run_id": s.run_id,
                    "status": s.status,
                    "current_stage": s.current_stage,
                    "progress_pct": round(s.progress_pct, 1),
                    "stages_completed": s.stages_completed,
                    "message": s.message,
                }
            )
            if s.status in ("completed", "failed"):
                yield _sse_event(
                    {
                        "run_id": s.run_id,
                        "status": s.status,
                        "progress_pct": s.progress_pct,
                    },
                    event="done",
                )
                break
            # 等待下次更新
            evt = pipeline_tracker.subscribe(run_id)
            evt.clear()
            try:
                await asyncio.wait_for(evt.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                # 发送心跳
                yield ": keepalive\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 聊天 SSE ──────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(body: ChatStreamRequest) -> StreamingResponse:
    """简单 LLM 流式聊天（SSE）— 不走 OpenClaw Gateway。"""
    llm = get_llm_client()

    async def _generate():
        try:
            async for token in llm.invoke_stream(
                body.message,
                model=body.model,
                max_tokens=body.max_tokens,
            ):
                yield _sse_event({"text": token})
            yield _sse_event({}, event="done")
        except Exception as exc:
            yield _sse_event({"error": str(exc)}, event="error")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
