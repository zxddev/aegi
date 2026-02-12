# Author: msq
"""GDELT API 路由测试（mock deps）。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _fake_event(uid: str = "ge_001", status: str = "new") -> SimpleNamespace:
    return SimpleNamespace(
        uid=uid,
        gdelt_id="abc123",
        case_uid=None,
        title="Test GDELT Event",
        url="https://example.com/article",
        source_domain="example.com",
        language="English",
        published_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
        cameo_code=None,
        goldstein_scale=None,
        actor1=None,
        actor2=None,
        geo_country="US",
        geo_name=None,
        tone=-1.5,
        status=status,
        matched_subscription_uids=["sub_1"],
        created_at=datetime(2026, 2, 11, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_manual_poll(client: AsyncClient, app) -> None:
    """POST /gdelt/monitor/poll → 调用 monitor.poll()。"""
    fake_ev = _fake_event()

    async def fake_get_db():
        yield AsyncMock()

    with patch("aegi_core.api.routes.gdelt.get_gdelt_client") as mock_gc:
        mock_gc.return_value = AsyncMock()
        with patch(
            "aegi_core.services.gdelt_monitor.GDELTMonitor.poll",
            new_callable=AsyncMock,
            return_value=[fake_ev],
        ):
            from aegi_core.api.deps import get_db_session

            app.dependency_overrides[get_db_session] = fake_get_db
            resp = await client.post("/gdelt/monitor/poll")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_events"] == 1
    assert len(data["events"]) == 1


@pytest.mark.asyncio
async def test_list_events(client: AsyncClient, app) -> None:
    """GET /gdelt/events → 分页列表。"""
    fake_ev = _fake_event()

    mock_session = AsyncMock()
    total_result = MagicMock()
    total_result.scalar.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [fake_ev]

    mock_session.execute = AsyncMock(side_effect=[total_result, rows_result])

    async def fake_get_db():
        yield mock_session

    from aegi_core.api.deps import get_db_session

    app.dependency_overrides[get_db_session] = fake_get_db
    resp = await client.get("/gdelt/events")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["uid"] == "ge_001"


@pytest.mark.asyncio
async def test_get_event_detail(client: AsyncClient, app) -> None:
    """GET /gdelt/events/{uid} → 单个事件。"""
    fake_ev = _fake_event()

    mock_session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = fake_ev
    mock_session.execute = AsyncMock(return_value=result)

    async def fake_get_db():
        yield mock_session

    from aegi_core.api.deps import get_db_session

    app.dependency_overrides[get_db_session] = fake_get_db
    resp = await client.get("/gdelt/events/ge_001")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["uid"] == "ge_001"


@pytest.mark.asyncio
async def test_ingest_event(client: AsyncClient, app) -> None:
    """POST /gdelt/events/{uid}/ingest → 调用 monitor.ingest_event()。"""
    fake_ev = _fake_event()

    mock_session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = fake_ev
    mock_session.execute = AsyncMock(return_value=result)

    async def fake_get_db():
        yield mock_session

    from aegi_core.api.deps import get_db_session

    app.dependency_overrides[get_db_session] = fake_get_db

    with patch("aegi_core.api.routes.gdelt.get_gdelt_client") as mock_gc:
        mock_gc.return_value = AsyncMock()
        with patch(
            "aegi_core.services.gdelt_monitor.GDELTMonitor.ingest_event",
            new_callable=AsyncMock,
        ):
            resp = await client.post(
                "/gdelt/events/ge_001/ingest",
                json={"case_uid": "case_1"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ingested"


@pytest.mark.asyncio
async def test_stats(client: AsyncClient, app) -> None:
    """GET /gdelt/stats → 统计数据。"""
    mock_session = AsyncMock()

    total_result = MagicMock()
    total_result.scalar.return_value = 42

    status_result = MagicMock()
    status_result.all.return_value = [("new", 30), ("ingested", 12)]

    country_result = MagicMock()
    country_result.all.return_value = [("US", 20), ("CN", 10)]

    day_result = MagicMock()
    day_result.all.return_value = [(datetime(2026, 2, 11, tzinfo=timezone.utc), 5)]

    mock_session.execute = AsyncMock(
        side_effect=[total_result, status_result, country_result, day_result]
    )

    async def fake_get_db():
        yield mock_session

    from aegi_core.api.deps import get_db_session

    app.dependency_overrides[get_db_session] = fake_get_db
    resp = await client.get("/gdelt/stats")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 42
    assert data["by_status"]["new"] == 30
    assert len(data["top_countries"]) == 2
    assert data["by_day"][0]["day"] == "2026-02-11"
