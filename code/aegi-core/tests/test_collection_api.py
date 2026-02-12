"""OSINT 采集路由 API 集成测试 — 用 mock DB + SearXNG。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.deps import get_db_session, get_searxng_client
from aegi_core.api.main import app


# ---------------------------------------------------------------------------
# Mock 辅助函数
# ---------------------------------------------------------------------------


def _make_fake_job(
    uid: str = "cj_test1",
    case_uid: str = "case_001",
    query: str = "test query",
    status: str = "pending",
) -> MagicMock:
    """创建一个 mock CollectionJob ORM 对象。"""
    job = MagicMock()
    job.uid = uid
    job.case_uid = case_uid
    job.query = query
    job.categories = "general"
    job.language = "zh-CN"
    job.max_results = 10
    job.status = status
    job.error = None
    job.urls_found = 0
    job.urls_ingested = 0
    job.urls_deduped = 0
    job.claims_extracted = 0
    job.result_meta = {}
    job.cron_expression = None
    job.created_at = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
    job.updated_at = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
    return job


# ---------------------------------------------------------------------------
# Fixtures（测试夹具）
# ---------------------------------------------------------------------------


@pytest.fixture()
def _override_deps():
    """设置和清理 FastAPI app 的依赖覆盖。"""
    original_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original_overrides


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_job(_override_deps):
    """POST /cases/{case_uid}/collection/jobs 创建采集任务。"""
    fake_job = _make_fake_job()

    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    # commit 后 refresh 填充 job — 这里用 mock job 模拟
    session.refresh = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    # patch CollectionJob 构造函数返回 fake job，
    # patch _run_collection_job 防止后台任务跑真实 DB/服务调用
    with (
        patch(
            "aegi_core.api.routes.collection.CollectionJob",
            return_value=fake_job,
        ),
        patch(
            "aegi_core.api.routes.collection._run_collection_job",
            new_callable=AsyncMock,
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/cases/case_001/collection/jobs",
                json={"query": "test query"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["case_uid"] == "case_001"
    assert data["query"] == "test query"
    assert data["status"] == "pending"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_jobs(_override_deps):
    """GET /cases/{case_uid}/collection/jobs 返回分页列表。"""
    fake_job = _make_fake_job()

    session = AsyncMock()

    # 第一次 execute: count 查询 -> 返回 1
    # 第二次 execute: rows 查询 -> 返回 job 列表
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [fake_job]

    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/cases/case_001/collection/jobs")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["uid"] == "cj_test1"
    assert data["items"][0]["query"] == "test query"


@pytest.mark.asyncio
async def test_get_job_not_found(_override_deps):
    """GET /cases/{case_uid}/collection/jobs/{uid} 不存在时返回 404。"""
    session = AsyncMock()

    # execute 返回的 result 的 scalar_one_or_none 为 None
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=exec_result)

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/cases/case_001/collection/jobs/nonexistent_uid")

    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "not_found"


@pytest.mark.asyncio
async def test_search_preview(_override_deps):
    """POST /cases/{case_uid}/collection/search_preview 返回可信度信息。"""
    from aegi_core.infra.searxng_client import SearchResult

    fake_searxng = AsyncMock()
    fake_searxng.search = AsyncMock(
        return_value=[
            SearchResult(
                title="Reuters Article",
                url="https://www.reuters.com/world/test",
                snippet="Breaking news about test",
                engine="google",
            ),
            SearchResult(
                title="Unknown Blog",
                url="https://random.xyz/blog",
                snippet="Some blog post",
                engine="bing",
            ),
        ]
    )

    # get_searxng_client 在 endpoint 里直接调用（不是通过 Depends），
    # 所以在导入它的模块级别 patch。
    with patch(
        "aegi_core.api.routes.collection.get_searxng_client",
        return_value=fake_searxng,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/cases/case_001/collection/search_preview",
                json={"query": "test query", "limit": 5},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Reuters -> 高可信度 (多信号加权后 ~0.82)
    assert data[0]["title"] == "Reuters Article"
    assert data[0]["credibility"]["score"] >= 0.75
    assert data[0]["credibility"]["tier"] == "high"

    # Unknown -> 未知等级
    assert data[1]["credibility"]["tier"] in ("unknown", "low")
    assert data[1]["credibility"]["score"] <= 0.55
