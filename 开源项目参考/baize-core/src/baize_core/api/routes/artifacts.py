"""Artifact 接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from baize_core.api.models import ArtifactUploadRequest


def get_router(orchestrator: Any) -> APIRouter:
    """Artifact 路由。"""
    router = APIRouter()

    @router.post("/artifacts", response_model=dict[str, str])
    async def upload_artifact(payload: ArtifactUploadRequest) -> dict[str, str]:
        """上传 Artifact 并写入存储。"""
        artifact = await orchestrator.upload_artifact(
            payload_base64=payload.payload_base64,
            source_url=payload.source_url,
            mime_type=payload.mime_type,
            fetch_trace_id=payload.fetch_trace_id,
            license_note=payload.license_note,
        )
        return {
            "artifact_uid": artifact.artifact_uid,
            "storage_ref": artifact.storage_ref,
        }

    return router
