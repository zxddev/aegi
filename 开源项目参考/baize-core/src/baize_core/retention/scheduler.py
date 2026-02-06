"""内置定时清理任务（不依赖 Airflow）。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from uuid import uuid4

from fastapi import FastAPI

from baize_core.audit.recorder import AuditRecorder
from baize_core.retention.policy import resolve_retention_policy
from baize_core.schemas.audit import ToolTrace
from baize_core.storage.minio_store import MinioArtifactStore
from baize_core.storage.postgres import PostgresStore

logger = logging.getLogger(__name__)


def _read_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false")


def _read_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数") from exc
    if value <= 0:
        raise ValueError(f"环境变量 {name} 必须大于 0")
    return value


def register_retention_cleanup(
    app: FastAPI,
    *,
    store: PostgresStore,
    artifact_store: MinioArtifactStore,
    recorder: AuditRecorder,
) -> None:
    """注册定时清理（startup/shutdown）。"""

    enabled = _read_bool("BAIZE_CORE_RETENTION_CLEANUP_ENABLED", default=False)
    if not enabled:
        return

    interval_seconds = _read_int(
        "BAIZE_CORE_RETENTION_CLEANUP_INTERVAL_SECONDS", default=3600
    )
    batch_size = _read_int("BAIZE_CORE_RETENTION_CLEANUP_BATCH_SIZE", default=200)

    task: asyncio.Task[None] | None = None

    async def _loop() -> None:
        """后台循环。"""

        while True:
            trace_id = f"trace_{uuid4().hex}"
            started_at = time.time()
            deleted_objects = 0
            try:
                policy = resolve_retention_policy()
                marked = await store.mark_expired_unreferenced(batch_size=batch_size)
                hard = await store.hard_delete_soft_deleted_data(
                    grace_days=policy.hard_delete_grace_days,
                    batch_size=batch_size,
                )
                storage_refs = hard.get("storage_refs") or []
                if isinstance(storage_refs, list) and storage_refs:
                    deleted_objects = await artifact_store.delete_many(storage_refs)
                duration_ms = int((time.time() - started_at) * 1000)
                await recorder.record_tool_trace(
                    ToolTrace(
                        trace_id=trace_id,
                        tool_name="scheduled_cleanup",
                        duration_ms=duration_ms,
                        success=True,
                        result_ref=json.dumps(
                            {
                                "marked": marked,
                                "hard_deleted": {
                                    "deleted_evidence": hard.get("deleted_evidence", 0),
                                    "deleted_chunks": hard.get("deleted_chunks", 0),
                                    "deleted_artifacts": hard.get(
                                        "deleted_artifacts", 0
                                    ),
                                    "deleted_objects": deleted_objects,
                                },
                            },
                            ensure_ascii=False,
                        )[:256],
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pylint: disable=broad-exception-caught
                duration_ms = int((time.time() - started_at) * 1000)
                await recorder.record_tool_trace(
                    ToolTrace(
                        trace_id=trace_id,
                        tool_name="scheduled_cleanup",
                        duration_ms=duration_ms,
                        success=False,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                logger.exception("retention scheduled cleanup 失败")
            await asyncio.sleep(interval_seconds)

    @app.on_event("startup")
    async def _start() -> None:
        nonlocal task
        if task is None or task.done():
            task = asyncio.create_task(_loop())

    @app.on_event("shutdown")
    async def _stop() -> None:
        nonlocal task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
