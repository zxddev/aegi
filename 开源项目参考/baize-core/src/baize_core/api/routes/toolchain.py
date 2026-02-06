"""工具链接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from baize_core.api.models import ToolchainIngestRequest, ToolchainIngestResponse


def get_router(orchestrator: Any) -> APIRouter:
    """工具链路由。"""
    router = APIRouter()

    @router.post("/toolchain/ingest", response_model=ToolchainIngestResponse)
    async def ingest_toolchain(
        payload: ToolchainIngestRequest,
    ) -> ToolchainIngestResponse:
        """运行 MCP 工具链并写入证据链。"""
        try:
            (
                artifact_uids,
                chunk_uids,
                evidence_uids,
            ) = await orchestrator.ingest_toolchain(
                task_id=payload.task_id,
                query=payload.query,
                max_results=payload.max_results,
                language=payload.language,
                time_range=payload.time_range,
                max_depth=payload.max_depth,
                max_pages=payload.max_pages,
                obey_robots_txt=payload.obey_robots_txt,
                timeout_ms=payload.timeout_ms,
                chunk_size=payload.chunk_size,
                chunk_overlap=payload.chunk_overlap,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ToolchainIngestResponse(
            artifact_uids=artifact_uids,
            chunk_uids=chunk_uids,
            evidence_uids=evidence_uids,
        )

    return router
