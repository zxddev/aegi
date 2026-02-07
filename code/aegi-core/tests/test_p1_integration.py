# Author: msq
"""P1 端到端集成测试 — 真实基础设施。

需要运行中的服务：PostgreSQL, LiteLLM, vLLM BGE-M3, Qdrant。
测试内容：
  1. LLMClient.invoke() 真实调用 gpt-5.1
  2. LLMClient.embed() 真实调用 vLLM BGE-M3
  3. QdrantStore upsert + search 语义检索
  4. detect_language() 带 LLM 回退
  5. translate_claims() 真实翻译
  6. align_entities() 带 LLM rerank
  7. Chat API 语义检索端到端
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegi_core.contracts.llm_governance import BudgetContext
from aegi_core.contracts.schemas import SourceClaimV1
from aegi_core.db.base import Base
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.qdrant_store import QdrantStore
from aegi_core.services.entity_alignment import align_entities
from aegi_core.services.multilingual_pipeline import detect_language, translate_claims
from aegi_core.settings import settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_BUDGET = BudgetContext(max_tokens=4096, max_cost_usd=1.0)


def _make_claim(uid: str, quote: str, lang: str | None = None) -> SourceClaimV1:
    return SourceClaimV1(
        uid=uid,
        case_uid="case_integ",
        artifact_version_uid="av_integ",
        chunk_uid=f"chunk_{uid}",
        evidence_uid=f"ev_{uid}",
        quote=quote,
        language=lang,
        created_at=_NOW,
    )


@pytest.fixture
def llm() -> LLMClient:
    return LLMClient(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
    )


@pytest.fixture
def qdrant() -> QdrantStore:
    return QdrantStore(url=settings.qdrant_url)


@pytest.fixture
def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# 1. LLMClient.invoke — 真实 gpt-5.1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_invoke(llm: LLMClient) -> None:
    """LLMClient 能调通 LiteLLM → gpt-5.1。"""
    result = await llm.invoke("Reply with exactly: PONG", max_tokens=10)
    assert "text" in result
    assert len(result["text"]) > 0
    assert result["usage"]["total_tokens"] > 0


# ---------------------------------------------------------------------------
# 2. LLMClient.embed — 真实 vLLM BGE-M3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_embed(llm: LLMClient) -> None:
    """LLMClient.embed 返回 1024 维向量。"""
    vec = await llm.embed("军事演习在海峡附近展开")
    assert isinstance(vec, list)
    assert len(vec) == 1024
    assert all(isinstance(v, float) for v in vec[:5])


# ---------------------------------------------------------------------------
# 3. Qdrant upsert + semantic search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_qdrant_upsert_and_search(llm: LLMClient, qdrant: QdrantStore) -> None:
    """Embed → Qdrant upsert → 语义搜索命中。"""
    await qdrant.connect()

    # 插入两条不同主题的文本（用唯一前缀避免残留数据干扰）
    tag = uuid4().hex[:6]
    mil_id = f"chunk_mil_{tag}"
    eco_id = f"chunk_eco_{tag}"
    texts = {
        mil_id: "中国海军在南海举行大规模军事演习",
        eco_id: "全球石油价格因中东局势持续上涨",
    }
    for cid, text in texts.items():
        vec = await llm.embed(text)
        await qdrant.upsert(cid, vec, text)

    # 搜索军事相关内容
    q_vec = await llm.embed("海军演习")
    hits = await qdrant.search(q_vec, limit=5, score_threshold=0.3)
    assert len(hits) > 0
    hit_ids = [h.chunk_uid for h in hits]
    # 军事 chunk 应在结果中且排在经济 chunk 前面
    assert mil_id in hit_ids
    if eco_id in hit_ids:
        assert hit_ids.index(mil_id) < hit_ids.index(eco_id)


# ---------------------------------------------------------------------------
# 4. detect_language — 带 LLM 回退
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_language_with_llm(llm: LLMClient) -> None:
    """多语言检测：中/英/俄/阿。"""
    claims = [
        _make_claim("dl_zh", "中国海军在南海举行军事演习"),
        _make_claim("dl_en", "The navy conducted exercises in the South China Sea"),
        _make_claim("dl_ru", "Военно-морской флот провёл учения в Южно-Китайском море"),
        _make_claim("dl_ar", "أجرت البحرية تدريبات في بحر الصين الجنوبي"),
    ]
    resp = await detect_language(claims, llm=llm)
    assert len(resp.results) == 4
    assert len(resp.failures) == 0

    by_uid = {r.claim_uid: r for r in resp.results}
    assert by_uid["dl_zh"].language == "zh"
    assert by_uid["dl_en"].language == "en"
    assert by_uid["dl_ru"].language == "ru"
    assert by_uid["dl_ar"].language == "ar"


# ---------------------------------------------------------------------------
# 5. translate_claims — 真实 LLM 翻译
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_claims_with_llm(llm: LLMClient) -> None:
    """中文 claim 翻译成英文，结果不应是占位符。"""
    claims = [
        _make_claim("tr_zh", "中国海军在南海举行大规模军事演习", lang="zh"),
    ]
    resp = await translate_claims(claims, "en", _BUDGET, llm=llm)
    assert len(resp.results) == 1
    t = resp.results[0]
    assert t.claim_uid == "tr_zh"
    # 真实翻译不应包含占位符标记
    assert "[translated:" not in t.translation
    # 应包含英文关键词
    lower = t.translation.lower()
    assert any(kw in lower for kw in ["navy", "military", "exercise", "drill", "south china"])


# ---------------------------------------------------------------------------
# 6. align_entities — 带 LLM rerank
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_align_entities_with_llm(llm: LLMClient) -> None:
    """跨语言实体对齐：同一实体不同语言表述应被关联。"""
    claims = [
        _make_claim("ae_1", "中国海军在南海举行演习", lang="zh"),
        _make_claim("ae_2", "The Chinese Navy held exercises in the South China Sea", lang="en"),
        _make_claim("ae_3", "ВМС Китая провели учения в Южно-Китайском море", lang="ru"),
    ]
    resp = await align_entities(claims, _BUDGET, llm=llm)
    # 应该产生至少一个 entity link
    assert len(resp.links) > 0
    # 检查 link 包含来自不同 claim 的引用
    all_claim_uids = {link.source_claim_uid for link in resp.links}
    assert len(all_claim_uids) >= 2


# ---------------------------------------------------------------------------
# 7. Chat API 端到端 — 语义检索
# ---------------------------------------------------------------------------


def _seed_case_for_semantic_search(
    client: TestClient,
) -> tuple[str, list[tuple[str, str]], str]:
    """创建 case，插入多语言 claims。返回 (case_uid, claims_data, suffix)。"""
    created = client.post(
        "/cases",
        json={"title": "P1 integ test", "actor_id": "test", "rationale": "p1"},
    )
    assert created.status_code == 201
    case_uid = created.json()["case_uid"]

    suffix = uuid4().hex[:8]
    ai_uid = f"ai_{suffix}"
    av_uid = f"av_{suffix}"

    claims_data = [
        ("军事演习在台湾海峡附近展开，引发地区紧张", "zh"),
        ("Oil prices surged due to Middle East tensions", "en"),
        ("Военные учения вблизи Тайваньского пролива", "ru"),
    ]

    engine = sa.create_engine(settings.postgres_dsn_sync)
    with Session(engine) as session:
        session.add(ArtifactIdentity(uid=ai_uid, kind="html"))
        session.add(
            ArtifactVersion(
                uid=av_uid,
                artifact_identity_uid=ai_uid,
                case_uid=case_uid,
                storage_ref="fixtures://p1",
                content_sha256="sha256_p1",
                content_type="text/html",
                source_meta={},
            )
        )

        for i, (quote, lang) in enumerate(claims_data):
            chunk_uid = f"chunk_{suffix}_{i}"
            ev_uid = f"ev_{suffix}_{i}"
            sc_uid = f"sc_{suffix}_{i}"

            session.add(
                Chunk(
                    uid=chunk_uid,
                    artifact_version_uid=av_uid,
                    ordinal=i,
                    text=quote,
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
                    quote=quote,
                    selectors=[],
                    language=lang,
                )
            )
        session.commit()

    return case_uid, claims_data, suffix


def test_chat_semantic_search_e2e(_ensure_tables: None) -> None:
    """Chat API 通过语义检索找到相关 claim 并返回 citations。"""
    import os

    # 强制 NullPool 避免 asyncpg event loop 冲突
    os.environ["AEGI_DB_USE_NULL_POOL"] = "true"

    # 重新导入 app 以使用新的连接池设置
    from importlib import reload

    import aegi_core.db.session as _sess
    import aegi_core.api.deps as _deps

    reload(_sess)
    reload(_deps)

    from aegi_core.api.main import app as _app

    _llm = LLMClient(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
    _qdrant = QdrantStore(url=settings.qdrant_url)

    client = TestClient(_app)
    case_uid, claims_data, suffix = _seed_case_for_semantic_search(client)

    # Embed chunks 到 Qdrant（同步包装）
    async def _setup() -> None:
        await _qdrant.connect()
        for i, (quote, _lang) in enumerate(claims_data):
            cid = f"chunk_{suffix}_{i}"
            vec = await _llm.embed(quote)
            await _qdrant.upsert(cid, vec, quote)

    asyncio.run(_setup())

    # 用中文问军事演习相关问题
    resp = client.post(
        f"/cases/{case_uid}/analysis/chat",
        json={"question": "台湾海峡附近有什么军事活动？"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "trace_id" in data
    assert data["trace_id"].startswith("chat_")

    citations = data.get("evidence_citations", [])
    # 应该至少命中军事演习相关的 claim（中文或俄文）
    assert len(citations) >= 1

    # 验证 trace 持久化
    trace_resp = client.get(f"/cases/{case_uid}/analysis/chat/{data['trace_id']}")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert trace_data["trace_id"] == data["trace_id"]
    assert len(trace_data["citations"]) >= 1
