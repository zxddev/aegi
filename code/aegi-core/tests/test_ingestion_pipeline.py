# Author: msq
"""Ingestion pipeline 测试：doc_parse → Chunk/Evidence 入库。

Source: openspec/changes/ingestion-doc-parse-to-chunk/tasks.md (3.1–3.3)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from conftest import requires_postgres

# ---------------------------------------------------------------------------
# DB table bootstrap
# ---------------------------------------------------------------------------

_tables_created = False


def _ensure_tables() -> None:
    global _tables_created  # noqa: PLW0603
    if _tables_created:
        return
    import sqlalchemy as sa

    import aegi_core.db.models  # noqa: F401
    from aegi_core.db.base import Base
    from aegi_core.settings import settings

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)
    _tables_created = True


@pytest.fixture(scope="module", autouse=True)
def _tables():
    _ensure_tables()


# ---------------------------------------------------------------------------
# Mock doc_parse 返回
# ---------------------------------------------------------------------------

MOCK_CHUNKS = [
    {
        "text": "军事演习在台湾海峡附近展开",
        "type": "NarrativeText",
        "metadata": {
            "page_number": 1,
            "coordinates": {"x": 0, "y": 0},
            "filename": "test_document.pdf",
            "languages": ["zh", "en"],
        },
    },
    {
        "text": "Oil prices surged due to tensions",
        "type": "NarrativeText",
        "metadata": {"page_number": 2},
    },
    {
        "text": "Third paragraph with no metadata",
        "type": "NarrativeText",
        "metadata": {},
    },
]


def _mock_doc_parse_response() -> dict:
    return {"ok": True, "tool": "doc_parse", "chunks": MOCK_CHUNKS}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    from aegi_core.api.main import create_app

    return create_app()


@pytest.fixture
async def client(app):
    # override tool client 依赖，注入 mock
    mock_tool = AsyncMock()
    mock_tool.doc_parse = AsyncMock(return_value=_mock_doc_parse_response())

    from aegi_core.api.deps import get_tool_client

    app.dependency_overrides[get_tool_client] = lambda: mock_tool

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_tool_client, None)


async def _create_case(client: AsyncClient, title: str = "ingest-test") -> str:
    resp = await client.post("/cases", json={"title": title})
    assert resp.status_code == 201
    return resp.json()["case_uid"]


async def _create_artifact(case_uid: str) -> str:
    """直接写 DB 创建 ArtifactIdentity + ArtifactVersion，返回 av_uid。"""
    from uuid import uuid4

    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
    from aegi_core.settings import settings

    suffix = uuid4().hex[:8]
    ai_uid = f"ai_{suffix}"
    av_uid = f"av_{suffix}"

    engine = sa.create_engine(settings.postgres_dsn_sync)
    with Session(engine) as session:
        session.add(ArtifactIdentity(uid=ai_uid, kind="pdf"))
        session.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=ai_uid,
                case_uid=case_uid,
                storage_ref="fixtures://ingest-test",
                content_sha256=f"sha256_{suffix}",
                content_type="application/pdf",
                source_meta={},
            )
        )
        session.commit()
    return av_uid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_postgres
class TestIngestionPipeline:
    """doc_parse → Chunk/Evidence 入库。"""

    async def test_ingest_creates_chunks_and_evidence(
        self, client: AsyncClient
    ) -> None:
        """mock doc_parse → 验证 Chunk/Evidence 入库 + 返回 chunk_uids。"""
        case_uid = await _create_case(client, "ingest-chunks")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert data["tool_trace_uid"].startswith("tt_")
        assert len(data["chunk_uids"]) == len(MOCK_CHUNKS)
        assert len(data["evidence_uids"]) == len(MOCK_CHUNKS)

        # 验证 DB 中 Chunk/Evidence 行存在
        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from aegi_core.db.models.chunk import Chunk
        from aegi_core.db.models.evidence import Evidence
        from aegi_core.settings import settings

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with Session(engine) as session:
            chunks = (
                session.execute(
                    sa.select(Chunk).where(Chunk.uid.in_(data["chunk_uids"]))
                )
                .scalars()
                .all()
            )
            assert len(chunks) == len(MOCK_CHUNKS)
            ordinals = sorted(c.ordinal for c in chunks)
            assert ordinals == list(range(len(MOCK_CHUNKS)))
            texts = {c.text for c in chunks}
            for mc in MOCK_CHUNKS:
                assert mc["text"] in texts

            evidences = (
                session.execute(
                    sa.select(Evidence).where(Evidence.uid.in_(data["evidence_uids"]))
                )
                .scalars()
                .all()
            )
            assert len(evidences) == len(MOCK_CHUNKS)
            for ev in evidences:
                assert ev.kind == "document_chunk"
                assert ev.case_uid == case_uid

    async def test_ingest_empty_chunks(self, app, client: AsyncClient) -> None:
        """doc_parse 返回空 chunks → 正常返回空列表。"""
        from aegi_core.api.deps import get_tool_client

        # 临时替换为空 chunks 的 mock
        empty_mock = AsyncMock()
        empty_mock.doc_parse = AsyncMock(
            return_value={"ok": True, "tool": "doc_parse", "chunks": []}
        )
        app.dependency_overrides[get_tool_client] = lambda: empty_mock

        case_uid = await _create_case(client, "ingest-empty")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/empty.pdf",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_uids"] == []
        assert data["evidence_uids"] == []

    async def test_ingest_anchor_set_mapping(self, client: AsyncClient) -> None:
        """验证 anchor_set 从 unstructured metadata 正确映射。"""
        case_uid = await _create_case(client, "ingest-anchor")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        data = resp.json()

        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from aegi_core.db.models.chunk import Chunk
        from aegi_core.settings import settings

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with Session(engine) as session:
            chunks = (
                session.execute(
                    sa.select(Chunk)
                    .where(Chunk.uid.in_(data["chunk_uids"]))
                    .order_by(Chunk.ordinal)
                )
                .scalars()
                .all()
            )
            # 第一个 chunk：page + coordinates + filename + languages
            assert len(chunks[0].anchor_set) == 4
            types = {a["type"] for a in chunks[0].anchor_set}
            assert "page" in types
            assert "coordinates" in types
            assert "filename" in types
            assert "languages" in types

            # 第二个 chunk：page only
            assert len(chunks[1].anchor_set) == 1
            assert chunks[1].anchor_set[0]["type"] == "page"

            # 第三个 chunk：无 metadata → 空 anchor_set
            assert len(chunks[2].anchor_set) == 0

    async def test_ingest_chunk_uids_work_with_claim_extract(
        self, client: AsyncClient
    ) -> None:
        """验证 ingest 返回的 chunk_uids 可传入 claim_extract（集成路径）。"""
        case_uid = await _create_case(client, "ingest-chain")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        assert resp.status_code == 200
        chunk_uids = resp.json()["chunk_uids"]
        assert len(chunk_uids) > 0

        import sqlalchemy as sa
        from sqlalchemy.orm import Session

        from aegi_core.db.models.chunk import Chunk
        from aegi_core.settings import settings

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with Session(engine) as session:
            chunk = session.get(Chunk, chunk_uids[0])
            assert chunk is not None
            assert len(chunk.text) > 0

    async def test_ingest_error_returns_502(self, app, client: AsyncClient) -> None:
        """验证当 ToolClient.call 抛出异常时，返回 HTTP 502 ProblemDetail。"""
        from aegi_core.api.deps import get_tool_client

        # 创建抛出异常的 mock
        error_mock = AsyncMock()
        error_mock.doc_parse = AsyncMock(side_effect=Exception("Tool call failed"))
        app.dependency_overrides[get_tool_client] = lambda: error_mock

        case_uid = await _create_case(client, "ingest-error")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        assert resp.status_code == 502
        data = resp.json()
        assert data["error_code"] == "gateway_error"
        assert data["status"] == 502

    async def test_ingest_and_extract_happy_path(
        self, app, client: AsyncClient
    ) -> None:
        """mock ToolClient.doc_parse 返回 MOCK_CHUNKS，mock LLMBackend 返回空 claims，验证返回 200 且包含 chunk_uids/evidence_uids/source_claim_uids。"""
        from aegi_core.api.deps import get_llm_client, get_tool_client

        # Mock tool client
        mock_tool = AsyncMock()
        mock_tool.doc_parse = AsyncMock(return_value=_mock_doc_parse_response())

        # Mock LLM client to return empty claims
        mock_llm = AsyncMock()
        app.dependency_overrides[get_tool_client] = lambda: mock_tool
        app.dependency_overrides[get_llm_client] = lambda: mock_llm

        case_uid = await _create_case(client, "ingest-extract-happy")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest_and_extract",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert data["tool_trace_uid"].startswith("tt_")
        assert len(data["chunk_uids"]) == len(MOCK_CHUNKS)
        assert len(data["evidence_uids"]) == len(MOCK_CHUNKS)
        assert "source_claim_uids" in data

        # Clean up overrides
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_ingest_and_extract_error_returns_502(
        self, app, client: AsyncClient
    ) -> None:
        """mock ToolClient.doc_parse 抛出异常，验证返回 502 ProblemDetail。"""
        from aegi_core.api.deps import get_tool_client

        # Mock tool client to raise exception
        error_mock = AsyncMock()
        error_mock.doc_parse = AsyncMock(side_effect=Exception("Tool call failed"))
        app.dependency_overrides[get_tool_client] = lambda: error_mock

        case_uid = await _create_case(client, "ingest-extract-error")
        av_uid = await _create_artifact(case_uid)

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/ingest_and_extract",
            json={
                "artifact_version_uid": av_uid,
                "file_url": "http://minio:9000/test.pdf",
            },
        )

        assert resp.status_code == 502
        data = resp.json()
        assert data["error_code"] == "gateway_error"
        assert "Tool call failed" in data["detail"]

    async def test_archive_and_ingest_happy_path(
        self, app, client: AsyncClient
    ) -> None:
        """archive_url → ArtifactVersion → doc_parse 全链路。"""
        from aegi_core.api.deps import get_tool_client

        mock_tool = AsyncMock()
        # archive_url 返回
        mock_tool.archive_url = AsyncMock(
            return_value={
                "ok": True,
                "tool": "archive_url",
                "url": "http://example.com/report.pdf",
                "archived": True,
                "snapshot": {"archive_path": "/data/archive/abc123"},
            }
        )
        # doc_parse 返回
        mock_tool.doc_parse = AsyncMock(return_value=_mock_doc_parse_response())
        app.dependency_overrides[get_tool_client] = lambda: mock_tool

        case_uid = await _create_case(client, "archive-ingest")

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/archive_and_ingest",
            json={"url": "http://example.com/report.pdf"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["artifact_version_uid"].startswith("av_")
        assert data["archive_action_uid"].startswith("act_")
        assert data["ingest_action_uid"].startswith("act_")
        assert data["tool_trace_uid"].startswith("tt_")
        assert len(data["chunk_uids"]) == len(MOCK_CHUNKS)
        assert len(data["evidence_uids"]) == len(MOCK_CHUNKS)

    async def test_archive_and_ingest_archive_error(
        self, app, client: AsyncClient
    ) -> None:
        """archive_url 失败时返回 502 ProblemDetail。"""
        from aegi_core.api.deps import get_tool_client

        mock_tool = AsyncMock()
        mock_tool.archive_url = AsyncMock(side_effect=Exception("Archive failed"))
        app.dependency_overrides[get_tool_client] = lambda: mock_tool

        case_uid = await _create_case(client, "archive-error")

        resp = await client.post(
            f"/cases/{case_uid}/pipelines/archive_and_ingest",
            json={"url": "http://example.com/bad.pdf"},
        )

        assert resp.status_code == 502
        data = resp.json()
        assert data["error_code"] == "gateway_error"
