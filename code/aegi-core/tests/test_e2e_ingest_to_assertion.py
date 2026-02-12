# Author: msq
"""端到端集成测试：ingest → claim_extract → assertion_fuse 全链路。

使用真实 Gateway app（ASGI 内嵌），mock 外部 HTTP 调用（Unstructured API）和 LLM。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import ASGITransport, AsyncClient

from conftest import requires_postgres

pytestmark = requires_postgres

# ── mock 数据 ──────────────────────────────────────────────────

MOCK_UNSTRUCTURED_ELEMENTS = [
    {
        "text": "军事演习在台湾海峡附近展开",
        "type": "NarrativeText",
        "metadata": {"page_number": 1, "filename": "report.pdf"},
    },
    {
        "text": "Oil prices surged due to geopolitical tensions",
        "type": "NarrativeText",
        "metadata": {"page_number": 2},
    },
]

MOCK_LLM_CLAIMS = [
    {
        "quote": "军事演习在台湾海峡附近展开",
        "selectors": [
            {"type": "TextQuoteSelector", "exact": "军事演习在台湾海峡附近展开"}
        ],
        "attributed_to": "官方声明",
    },
    {
        "quote": "Oil prices surged due to geopolitical tensions",
        "selectors": [{"type": "TextQuoteSelector", "exact": "Oil prices surged"}],
        "attributed_to": None,
    },
]


# ── Gateway ASGI ToolClient ────────────────────────────────────


def _import_gateway_app():
    """导入 Gateway app，添加 src 到 sys.path。"""
    gateway_src = Path(__file__).resolve().parents[2] / "aegi-mcp-gateway" / "src"
    if str(gateway_src) not in sys.path:
        sys.path.insert(0, str(gateway_src))
    from aegi_mcp_gateway.api.main import app as gateway_app

    return gateway_app


# 保存真实 AsyncClient 引用，避免被 patch 覆盖
_RealAsyncClient = httpx.AsyncClient


class _AsgiGatewayToolClient:
    """通过 ASGI transport 调用真实 Gateway app 的 ToolClient。"""

    def __init__(self, gateway_app: object) -> None:
        self._transport = httpx.ASGITransport(app=gateway_app)

    async def doc_parse(
        self, artifact_version_uid: str, *, file_url: str | None = None
    ) -> dict:
        payload: dict = {"artifact_version_uid": artifact_version_uid}
        if file_url:
            payload["file_url"] = file_url
        async with _RealAsyncClient(
            transport=self._transport, base_url="http://gateway"
        ) as client:
            resp = await client.post("/tools/doc_parse", json=payload)
            resp.raise_for_status()
            return resp.json()


# ── mock httpx（Gateway 内部 HTTP 调用）──────────────────────


def _make_mock_httpx_client():
    """创建 mock httpx.AsyncClient，拦截文件下载和 Unstructured API 调用。"""

    async def mock_get(url: str, **kwargs):
        """mock 文件下载。"""
        resp = AsyncMock()
        resp.content = b"%PDF-1.4 fake pdf content"
        resp.headers = httpx.Headers({"content-type": "application/pdf"})
        resp.raise_for_status = lambda: None
        return resp

    async def mock_post(url: str, **kwargs):
        """mock Unstructured API 调用。"""
        resp = AsyncMock()
        resp.json = lambda: MOCK_UNSTRUCTURED_ELEMENTS
        resp.raise_for_status = lambda: None
        return resp

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ── 测试 ──────────────────────────────────────────────────────


@requires_postgres
class TestE2EIngestToAssertion:
    """端到端：ingest → claim_extract → assertion_fuse。"""

    @pytest.fixture
    def app(self):
        from aegi_core.api.main import create_app

        return create_app()

    @pytest.fixture
    async def client(self, app):
        from aegi_core.api.deps import get_llm_client, get_tool_client

        gateway_app = _import_gateway_app()
        gateway_tool = _AsgiGatewayToolClient(gateway_app)
        app.dependency_overrides[get_tool_client] = lambda: gateway_tool

        # mock LLM：返回预设 claims
        mock_llm = AsyncMock()
        mock_llm.invoke = AsyncMock(return_value=MOCK_LLM_CLAIMS)
        app.dependency_overrides[get_llm_client] = lambda: mock_llm

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()

    async def _create_case(self, client: AsyncClient) -> str:
        resp = await client.post(
            "/cases",
            json={"title": "E2E test", "actor_id": "test", "rationale": "e2e"},
        )
        assert resp.status_code == 201
        return resp.json()["case_uid"]

    def _create_artifact(self, case_uid: str) -> str:
        """直接写 DB 创建 ArtifactIdentity + ArtifactVersion。"""
        from uuid import uuid4

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
                    storage_ref="fixtures://e2e-test",
                    content_sha256=f"sha256_{suffix}",
                    content_type="application/pdf",
                    source_meta={},
                )
            )
            session.commit()
        return av_uid

    async def test_full_pipeline_ingest_to_assertion(self, client: AsyncClient) -> None:
        """验证 ingest → claim_extract → assertion_fuse 全链路数据流。"""
        case_uid = await self._create_case(client)
        av_uid = self._create_artifact(case_uid)

        # Step 1: ingest（mock Gateway 内部 httpx 调用）
        mock_httpx = _make_mock_httpx_client()
        with patch(
            "aegi_mcp_gateway.api.routes.tools.httpx.AsyncClient",
            return_value=mock_httpx,
        ):
            resp = await client.post(
                f"/cases/{case_uid}/pipelines/ingest",
                json={
                    "artifact_version_uid": av_uid,
                    "file_url": "http://minio:9000/test-bucket/report.pdf",
                },
            )

        assert resp.status_code == 200, f"ingest 失败: {resp.text}"
        ingest_data = resp.json()
        chunk_uids = ingest_data["chunk_uids"]
        assert len(chunk_uids) == len(MOCK_UNSTRUCTURED_ELEMENTS)

        # Step 2: claim_extract（对每个 chunk，需要从 DB 读取 chunk_text）
        from aegi_core.db.models.chunk import Chunk as ChunkModel
        from aegi_core.db.session import ENGINE

        all_claim_uids: list[str] = []
        for chunk_uid in chunk_uids:
            async with AsyncSession(ENGINE, expire_on_commit=False) as db:
                row = (
                    await db.execute(
                        sa.select(ChunkModel).where(ChunkModel.uid == chunk_uid)
                    )
                ).scalar_one()
                chunk_text = row.text

            resp = await client.post(
                f"/cases/{case_uid}/pipelines/claim_extract",
                json={"chunk_uid": chunk_uid, "chunk_text": chunk_text},
            )
            assert resp.status_code == 200, f"claim_extract 失败: {resp.text}"
            claim_data = resp.json()
            all_claim_uids.extend(c["uid"] for c in claim_data.get("claims", []))

        assert len(all_claim_uids) > 0, "应该提取到至少一个 SourceClaim"

        # Step 3: assertion_fuse
        resp = await client.post(
            f"/cases/{case_uid}/pipelines/assertion_fuse",
            json={"source_claim_uids": all_claim_uids},
        )
        assert resp.status_code == 200, f"assertion_fuse 失败: {resp.text}"
        fuse_data = resp.json()
        assertion_uids = [a["uid"] for a in fuse_data.get("assertions", [])]
        assert len(assertion_uids) > 0, "应该融合出至少一个 Assertion"

        # 验证数据库中有完整的数据链
        from aegi_core.db.models.assertion import Assertion
        from aegi_core.db.models.source_claim import SourceClaim

        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            # 验证 Chunk
            chunks = (
                (
                    await session.execute(
                        sa.select(ChunkModel).where(ChunkModel.uid.in_(chunk_uids))
                    )
                )
                .scalars()
                .all()
            )
            assert len(chunks) == len(MOCK_UNSTRUCTURED_ELEMENTS)
            chunk_texts = {c.text for c in chunks}
            for el in MOCK_UNSTRUCTURED_ELEMENTS:
                assert el["text"] in chunk_texts

            # 验证 SourceClaim
            claims = (
                (
                    await session.execute(
                        sa.select(SourceClaim).where(
                            SourceClaim.uid.in_(all_claim_uids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(claims) == len(all_claim_uids)

            # 验证 Assertion
            assertions = (
                (
                    await session.execute(
                        sa.select(Assertion).where(Assertion.uid.in_(assertion_uids))
                    )
                )
                .scalars()
                .all()
            )
            assert len(assertions) == len(assertion_uids)
