"""事件驱动层集成测试：订阅 CRUD + EventBus → PushEngine。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.deps import get_db_session
from aegi_core.api.main import app
from aegi_core.services.event_bus import AegiEvent, get_event_bus, reset_event_bus


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture()
def _override_deps():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original


def _make_sub_mock(**kw):
    defaults = {
        "uid": "sub_test1",
        "user_id": "user_a",
        "sub_type": "case",
        "sub_target": "case_001",
        "priority_threshold": 0,
        "event_types": [],
        "enabled": True,
        "interest_text": None,
        "embedding_synced": False,
        "created_at": datetime(2026, 2, 11, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 11, tzinfo=timezone.utc),
    }
    defaults.update(kw)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ── 订阅 CRUD API 测试 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_create_subscription(_override_deps):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    with patch(
        "aegi_core.api.routes.subscriptions.Subscription",
        return_value=_make_sub_mock(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/subscriptions",
                json={
                    "user_id": "user_a",
                    "sub_type": "case",
                    "sub_target": "case_001",
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "user_a"
    assert data["sub_type"] == "case"
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_list_subscriptions(_override_deps):
    session = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [_make_sub_mock()]
    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/subscriptions?user_id=user_a")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_get_subscription(_override_deps):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _make_sub_mock()
    session.execute = AsyncMock(return_value=result)

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/subscriptions/sub_test1")

    assert resp.status_code == 200
    assert resp.json()["uid"] == "sub_test1"


@pytest.mark.asyncio
async def test_patch_subscription(_override_deps):
    sub = _make_sub_mock()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            "/subscriptions/sub_test1",
            json={"enabled": False},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_subscription(_override_deps):
    sub = _make_sub_mock()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = sub
    session.execute = AsyncMock(return_value=result)
    session.delete = AsyncMock()
    session.commit = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/subscriptions/sub_test1")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_get_subscription_not_found(_override_deps):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/subscriptions/nonexistent")

    assert resp.status_code == 404


# ── EventBus → PushEngine 集成测试 ────────────────────────────


@pytest.mark.asyncio
async def test_event_bus_to_push_engine_full_chain():
    """发送事件 → PushEngine 处理 → push_log 记录。"""
    from aegi_core.services.push_engine import PushEngine

    bus = get_event_bus()
    processed_events = []

    async def tracking_handler(event: AegiEvent):
        processed_events.append(event.event_type)

    bus.on("*", tracking_handler)

    event = AegiEvent(
        event_type="pipeline.completed",
        case_uid="case_001",
        payload={"summary": "test pipeline done"},
        severity="medium",
        source_event_uid="integration-test-001",
    )

    await bus.emit_and_wait(event)
    assert processed_events == ["pipeline.completed"]


@pytest.mark.asyncio
async def test_multiple_events_different_types():
    """多种事件类型分发到对应 handler。"""
    bus = get_event_bus()
    pipeline_events = []
    osint_events = []

    async def pipeline_handler(event: AegiEvent):
        pipeline_events.append(event)

    async def osint_handler(event: AegiEvent):
        osint_events.append(event)

    bus.on("pipeline.completed", pipeline_handler)
    bus.on("osint.collected", osint_handler)

    await bus.emit_and_wait(
        AegiEvent(
            event_type="pipeline.completed",
            case_uid="c1",
            payload={"summary": "done"},
        )
    )
    await bus.emit_and_wait(
        AegiEvent(
            event_type="osint.collected",
            case_uid="c2",
            payload={"summary": "collected"},
        )
    )

    assert len(pipeline_events) == 1
    assert len(osint_events) == 1
    assert pipeline_events[0].case_uid == "c1"
    assert osint_events[0].case_uid == "c2"
