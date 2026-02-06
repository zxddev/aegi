"""存储与 HITL/MCP 集成测试。"""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from baize_core.schemas.entity_event import (
    Entity,
    EntityType,
    Event,
    EventParticipant,
    EventType,
    GeoPoint,
)
from baize_core.schemas.evidence import (
    AnchorType,
    Artifact,
    Chunk,
    ChunkAnchor,
    Claim,
    Evidence,
    EvidenceScore,
    Report,
    ReportReference,
)
from baize_core.schemas.policy import SensitivityLevel
from baize_core.schemas.review_request import ReviewCreateRequest, ReviewStatus
from baize_core.schemas.task import TaskSpec
from baize_core.storage.database import create_session_factory
from baize_core.storage.minio_store import MinioArtifactStore
from baize_core.storage.models import Base
from baize_core.storage.postgres import PostgresStore
from baize_core.tools.mcp_client import McpClient


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
async def test_review_flow() -> None:
    store = await _build_store()
    task_id = f"task_{uuid4().hex}"
    task = TaskSpec(
        task_id=task_id,
        objective="验证审查流程",
        constraints=["必须可回放"],
        sensitivity=SensitivityLevel.INTERNAL,
    )
    await store.create_task(task)
    review = await store.create_review_request(
        ReviewCreateRequest(task_id=task_id, reason="需要人工复核")
    )
    assert review.status == ReviewStatus.PENDING
    approved = await store.approve_review(review.review_id)
    assert approved.status == ReviewStatus.APPROVED


@pytest.mark.asyncio
async def test_store_evidence_chain_and_report() -> None:
    store = await _build_store()
    task_id = f"task_{uuid4().hex}"
    await store.create_task(
        TaskSpec(
            task_id=task_id,
            objective="验证证据链落库",
            constraints=[],
            sensitivity=SensitivityLevel.INTERNAL,
        )
    )

    minio_endpoint = os.getenv("MINIO_ENDPOINT")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY")
    minio_bucket = os.getenv("MINIO_BUCKET")
    minio_secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    if (
        not minio_endpoint
        or not minio_access_key
        or not minio_secret_key
        or not minio_bucket
    ):
        pytest.skip("未配置 MinIO")

    minio_client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=minio_secure,
    )
    artifact_store = MinioArtifactStore(client=minio_client, bucket=minio_bucket)
    await artifact_store.ensure_bucket()

    payload = b"artifact payload for test"
    payload_b64 = base64.b64encode(payload).decode("utf-8")
    content_sha = sha256(payload).hexdigest()
    artifact_uid = f"art_{uuid4().hex}"
    storage_ref = f"{artifact_uid}/{content_sha}"
    await artifact_store.put_base64(
        object_name=storage_ref,
        payload_base64=payload_b64,
        content_type="text/plain",
    )

    artifact = Artifact(
        artifact_uid=artifact_uid,
        source_url="https://example.com",
        fetched_at=datetime.now(UTC),
        content_sha256=content_sha,
        mime_type="text/plain",
        storage_ref=storage_ref,
        fetch_trace_id="trace_test",
        license_note="test",
    )
    chunk_text = "sample snippet"
    chunk = Chunk(
        chunk_uid=f"chk_{uuid4().hex}",
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text=chunk_text,
        text_sha256=sha256(chunk_text.encode("utf-8")).hexdigest(),
    )
    evidence = Evidence(
        evidence_uid=f"evi_{uuid4().hex}",
        chunk_uid=chunk.chunk_uid,
        source="test_source",
        uri="https://example.com",
        collected_at=datetime.now(UTC),
        base_credibility=0.8,
        score=EvidenceScore(authority=0.8, timeliness=0.9, consistency=0.7, total=0.8),
        tags=["test"],
        summary="evidence summary",
    )
    claim = Claim(
        claim_uid=f"clm_{uuid4().hex}",
        statement="sample claim",
        confidence=0.6,
        evidence_uids=[evidence.evidence_uid],
        contradictions=[],
    )

    await store.store_evidence_chain(
        artifacts=[artifact],
        chunks=[chunk],
        evidence_items=[evidence],
        claims=[claim],
    )

    report = Report(
        report_uid=f"rpt_{uuid4().hex}",
        task_id=task_id,
        content_ref="s3://reports/test",
        references=[
            ReportReference(
                citation=1,
                evidence_uid=evidence.evidence_uid,
                chunk_uid=chunk.chunk_uid,
                artifact_uid=artifact.artifact_uid,
                source_url=artifact.source_url,
                anchor=chunk.anchor,
            )
        ],
    )
    await store.store_report(report)


@pytest.mark.asyncio
async def test_store_entity_event() -> None:
    store = await _build_store()
    artifact = Artifact(
        artifact_uid=f"art_{uuid4().hex}",
        source_url="https://example.com",
        fetched_at=datetime.now(UTC),
        content_sha256=sha256(b"entity_event").hexdigest(),
        mime_type="text/plain",
        storage_ref="test/entity_event",
    )
    chunk = Chunk(
        chunk_uid=f"chk_{uuid4().hex}",
        artifact_uid=artifact.artifact_uid,
        anchor=ChunkAnchor(type=AnchorType.TEXT_OFFSET, ref="0-10"),
        text="entity event",
        text_sha256=sha256(b"entity event").hexdigest(),
    )
    evidence = Evidence(
        evidence_uid=f"evi_{uuid4().hex}",
        chunk_uid=chunk.chunk_uid,
        source="test_source",
        uri="https://example.com",
        collected_at=datetime.now(UTC),
        base_credibility=0.7,
        score=EvidenceScore(authority=0.7, timeliness=0.7, consistency=0.7, total=0.7),
        tags=["test"],
        summary="evidence summary",
    )
    await store.store_evidence_chain(
        artifacts=[artifact],
        chunks=[chunk],
        evidence_items=[evidence],
        claims=[],
    )

    entity = Entity(
        entity_type=EntityType.ACTOR,
        name="测试参与方",
        aliases=["测试国家"],
        evidence_uids=[evidence.evidence_uid],
        geo_point=GeoPoint(lon=120.0, lat=30.0),
    )
    await store.store_entities([entity])
    fetched_entity = await store.get_entity_by_uid(entity.entity_uid)
    assert fetched_entity is not None
    assert fetched_entity.entity_uid == entity.entity_uid

    event = Event(
        event_type=EventType.INCIDENT,
        summary="测试事件",
        time_start=datetime.now(UTC),
        location_name="测试区域",
        participants=[EventParticipant(entity_uid=entity.entity_uid, role="actor")],
        evidence_uids=[evidence.evidence_uid],
        tags=["test"],
    )
    await store.store_events([event])
    fetched_event = await store.get_event_by_uid(event.event_uid)
    assert fetched_event is not None
    assert fetched_event.event_uid == event.event_uid

    entities = await store.list_entities(
        entity_types=[EntityType.ACTOR],
        bbox=None,
        limit=10,
        offset=0,
    )
    assert any(item.entity_uid == entity.entity_uid for item in entities)

    events = await store.list_events(
        event_types=[EventType.INCIDENT],
        time_start=event.time_start,
        time_end=event.time_start,
        bbox=None,
        limit=10,
        offset=0,
    )
    assert any(item.event_uid == event.event_uid for item in events)


@pytest.mark.asyncio
async def test_mcp_invoke() -> None:
    base_url = os.getenv("MCP_BASE_URL")
    api_key = os.getenv("MCP_API_KEY")
    tool_name = os.getenv("MCP_TEST_TOOL")
    payload_raw = os.getenv("MCP_TEST_PAYLOAD", "{}")
    if not base_url or not api_key or not tool_name:
        pytest.skip("未配置 MCP_BASE_URL/MCP_API_KEY/MCP_TEST_TOOL")
    payload = json.loads(payload_raw)
    client = McpClient(base_url=base_url, api_key=api_key)
    result = await client.invoke(tool_name=tool_name, payload=payload)
    assert isinstance(result, dict)
