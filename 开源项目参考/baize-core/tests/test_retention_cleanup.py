"""Retention cleanup 集成测试。

说明：不使用 mock/stub；如未配置 POSTGRES_DSN，将自动跳过。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from baize_core.schemas.evidence import (
    AnchorType,
    Artifact,
    Chunk,
    ChunkAnchor,
    Evidence,
    Report,
    ReportReference,
)
from baize_core.schemas.task import TaskSpec
from baize_core.storage.database import create_session_factory
from baize_core.storage.models import Base
from baize_core.storage.postgres import PostgresStore


async def _build_store() -> PostgresStore:
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        pytest.skip("未配置 POSTGRES_DSN")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await connection.execute(text("CREATE SCHEMA IF NOT EXISTS baize_core"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    return PostgresStore(session_factory)


@pytest.mark.asyncio
async def test_soft_delete_respects_shared_references_and_hard_delete() -> None:
    store = await _build_store()

    task_id_1 = f"task_{uuid4().hex}"
    task_id_2 = f"task_{uuid4().hex}"
    await store.create_task(TaskSpec(task_id=task_id_1, objective="t1"))
    await store.create_task(TaskSpec(task_id=task_id_2, objective="t2"))

    old = datetime.now(UTC) - timedelta(days=365)
    artifact = Artifact(
        source_url="https://example.com",
        fetched_at=old,
        content_sha256="sha256:" + ("0" * 64),
        mime_type="text/html",
        storage_ref="obj/example",
    )
    anchor = ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0:10")
    chunk = Chunk(
        artifact_uid=artifact.artifact_uid,
        anchor=anchor,
        text="hello",
        text_sha256="sha256:" + ("1" * 64),
    )
    evidence = Evidence(
        chunk_uid=chunk.chunk_uid,
        source="example",
        uri="https://example.com",
        collected_at=old,
        base_credibility=0.5,
        summary="s",
    )

    await store.store_evidence_chain(
        artifacts=[artifact],
        chunks=[chunk],
        evidence_items=[evidence],
        claims=[],
    )

    ref = ReportReference(
        citation=1,
        evidence_uid=evidence.evidence_uid,
        chunk_uid=chunk.chunk_uid,
        artifact_uid=artifact.artifact_uid,
        source_url=artifact.source_url,
        anchor=anchor,
    )
    await store.store_report(
        Report(task_id=task_id_1, content_ref="minio://r1", references=[ref])
    )
    await store.store_report(
        Report(task_id=task_id_2, content_ref="minio://r2", references=[ref])
    )

    # 删除 task1 数据：由于 task2 仍引用同一 evidence/chain，不应被软删除
    result1 = await store.soft_delete_task_data(task_id_1)
    assert result1["deleted_evidence"] == 0
    assert result1["deleted_chunks"] == 0
    assert result1["deleted_artifacts"] == 0

    # 删除 task2 数据：此时不再被引用，应被软删除
    result2 = await store.soft_delete_task_data(task_id_2)
    assert result2["deleted_evidence"] >= 1
    assert result2["deleted_chunks"] >= 1
    assert result2["deleted_artifacts"] >= 1

    # 把 deleted_at 调整到宽限期前，触发硬删
    threshold = datetime.now(UTC) - timedelta(days=8)
    async with store.session_factory() as session:
        await session.execute(
            text(
                "UPDATE baize_core.evidence SET deleted_at=:ts WHERE evidence_uid=:uid"
            ),
            {"ts": threshold, "uid": evidence.evidence_uid},
        )
        await session.execute(
            text("UPDATE baize_core.chunks SET deleted_at=:ts WHERE chunk_uid=:uid"),
            {"ts": threshold, "uid": chunk.chunk_uid},
        )
        await session.execute(
            text(
                "UPDATE baize_core.artifacts SET deleted_at=:ts, reference_count=0 WHERE artifact_uid=:uid"
            ),
            {"ts": threshold, "uid": artifact.artifact_uid},
        )
        await session.commit()

    hard = await store.hard_delete_soft_deleted_data(grace_days=7, batch_size=1000)
    assert hard["deleted_evidence"] >= 1
    assert hard["deleted_chunks"] >= 1
    assert hard["deleted_artifacts"] >= 1
    assert "obj/example" in hard["storage_refs"]
