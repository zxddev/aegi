# Author: msq
"""Investigations API route tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.deps import get_db_session
from aegi_core.api.main import app


def _fake_investigation(uid: str = "inv_001", status: str = "running"):
    now = datetime(2026, 2, 12, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        uid=uid,
        case_uid="case_001",
        trigger_event_type="hypothesis.updated",
        trigger_event_uid="evt_001",
        status=status,
        config={"max_rounds": 1},
        rounds=[{"round_number": 1, "claims_extracted": 2}],
        total_claims_extracted=2,
        gap_resolved=True,
        started_at=now,
        completed_at=now if status != "running" else None,
        cancelled_by="expert_alice" if status == "cancelled" else None,
        created_at=now,
    )


@pytest.fixture()
def _override_deps():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original


@pytest.mark.asyncio
async def test_list_investigations(_override_deps):
    session = AsyncMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [_fake_investigation()]
    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/investigations?case_uid=case_001")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["uid"] == "inv_001"
    assert body["items"][0]["status"] == "running"


@pytest.mark.asyncio
async def test_get_investigation_detail(_override_deps):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _fake_investigation(status="completed")
    session.execute = AsyncMock(return_value=result)

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/investigations/inv_001")

    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == "inv_001"
    assert body["status"] == "completed"
    assert body["rounds"][0]["claims_extracted"] == 2


@pytest.mark.asyncio
async def test_cancel_investigation(_override_deps):
    session = AsyncMock()
    row = _fake_investigation(status="running")
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    with patch(
        "aegi_core.api.routes.investigations.cancel_investigation_run",
        new=AsyncMock(return_value=True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/investigations/inv_001/cancel",
                json={"cancelled_by": "expert_bob"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == "inv_001"
    assert body["status"] == "cancelled"
    assert body["cancel_signal_sent"] is True
    assert row.status == "cancelled"
    assert row.cancelled_by == "expert_bob"
