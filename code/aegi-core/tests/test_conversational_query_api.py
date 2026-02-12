# Author: msq
"""对话式问答 API 测试。

Source: openspec/changes/conversational-analysis-evidence-qa/tasks.md (4.1)
Evidence: POST /cases/{case_uid}/analysis/chat 和 GET trace 端点必须返回 trace_id + citations。
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.settings import settings
from conftest import requires_llm, requires_postgres

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


def _seed_case_with_claims(client: TestClient) -> tuple[str, str]:
    """创建 case 并插入一条 source claim，返回 (case_uid, source_claim_uid)。"""
    created = client.post(
        "/cases",
        json={"title": "Chat test case", "actor_id": "test", "rationale": "chat test"},
    )
    assert created.status_code == 201
    case_uid = created.json()["case_uid"]

    suffix = uuid4().hex
    ai_uid = f"ai_{suffix}"
    av_uid = f"av_{suffix}"
    chunk_uid = f"chunk_{suffix}"
    ev_uid = f"ev_{suffix}"
    sc_uid = f"sc_{suffix}"

    engine = sa.create_engine(settings.postgres_dsn_sync)
    with Session(engine) as session:
        session.add(ArtifactIdentity(uid=ai_uid, kind="html"))
        session.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=ai_uid,
                case_uid=case_uid,
                storage_ref="fixtures://test",
                content_sha256="sha256_test",
                content_type="text/html",
                source_meta={},
            )
        )
        session.add(
            Chunk(
                uid=chunk_uid,
                artifact_version_uid=av_uid,
                ordinal=0,
                text="Exampleland announced a maritime exercise near the Strait.",
                anchor_set=[],
                anchor_health={},
            )
        )
        session.add(
            Evidence(
                uid=ev_uid,
                case_uid=case_uid,
                artifact_version_uid=av_uid,
                chunk_uid=chunk_uid,
                kind="quote",
                pii_flags={},
                retention_policy={},
            )
        )
        session.add(
            SourceClaim(
                uid=sc_uid,
                case_uid=case_uid,
                artifact_version_uid=av_uid,
                chunk_uid=chunk_uid,
                evidence_uid=ev_uid,
                quote="Exampleland announced a maritime exercise near the Strait.",
                selectors=[],
            )
        )
        session.commit()

    return case_uid, sc_uid


@requires_llm
def test_chat_returns_trace_id_and_citations() -> None:
    """POST /analysis/chat 返回 trace_id 和 evidence_citations。"""
    _ensure_tables()
    client = TestClient(app)
    case_uid, sc_uid = _seed_case_with_claims(client)

    resp = client.post(
        f"/cases/{case_uid}/analysis/chat",
        json={"question": "What maritime exercise was announced?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "trace_id" in body
    assert body["trace_id"].startswith("chat_")
    assert "evidence_citations" in body
    assert len(body["evidence_citations"]) > 0
    assert body["evidence_citations"][0]["source_claim_uid"] == sc_uid
    assert body["answer_type"] == "FACT"


@requires_llm
def test_chat_trace_replay() -> None:
    """GET /analysis/chat/{trace_id} 返回 query_plan + citations。"""
    _ensure_tables()
    client = TestClient(app)
    case_uid, _ = _seed_case_with_claims(client)

    chat_resp = client.post(
        f"/cases/{case_uid}/analysis/chat",
        json={"question": "What maritime exercise was announced?"},
    )
    trace_id = chat_resp.json()["trace_id"]

    trace_resp = client.get(f"/cases/{case_uid}/analysis/chat/{trace_id}")
    assert trace_resp.status_code == 200
    trace = trace_resp.json()
    assert "query_plan" in trace
    assert "citations" in trace
    assert trace["trace_id"] == trace_id


def test_chat_case_not_found() -> None:
    _ensure_tables()
    client = TestClient(app)
    resp = client.post(
        "/cases/case_nonexistent/analysis/chat",
        json={"question": "test"},
    )
    assert resp.status_code == 404


def test_chat_trace_not_found() -> None:
    _ensure_tables()
    client = TestClient(app)
    created = client.post(
        "/cases",
        json={"title": "Trace test", "actor_id": "test"},
    )
    case_uid = created.json()["case_uid"]
    resp = client.get(f"/cases/{case_uid}/analysis/chat/chat_nonexistent")
    assert resp.status_code == 404


@requires_llm
def test_chat_with_graph_context() -> None:
    """图谱增强：Neo4j 中有实体时，chat 应将图谱上下文注入 LLM prompt。"""
    _ensure_tables()

    from aegi_core.api.deps import get_neo4j_store

    neo4j = get_neo4j_store()

    client = TestClient(app)
    case_uid, sc_uid = _seed_case_with_claims(client)

    tag = uuid4().hex[:8]
    ent1_uid = f"ent_exampleland_{tag}"
    ent2_uid = f"ent_strait_{tag}"

    # 往 Neo4j 写入与 case 关联的实体（直接调同步方法）
    neo4j._sync_upsert_nodes(
        "Entity",
        [
            {
                "uid": ent1_uid,
                "name": "Exampleland",
                "type": "country",
                "case_uid": case_uid,
            },
            {
                "uid": ent2_uid,
                "name": "Strait",
                "type": "location",
                "case_uid": case_uid,
            },
        ],
    )
    neo4j._sync_upsert_edges(
        "Entity",
        "Entity",
        "CONDUCTED_EXERCISE_NEAR",
        [
            {
                "source_uid": ent1_uid,
                "target_uid": ent2_uid,
                "properties": {"description": "maritime exercise"},
            }
        ],
    )

    # chat 提问，关键词命中 SourceClaim（keyword fallback）+ Neo4j 实体
    resp = client.post(
        f"/cases/{case_uid}/analysis/chat",
        json={
            "question": "What maritime exercise did Exampleland announce near the Strait?"
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "trace_id" in body

    # 验证 trace 持久化且图谱路径未崩溃
    trace_resp = client.get(f"/cases/{case_uid}/analysis/chat/{body['trace_id']}")
    assert trace_resp.status_code == 200
