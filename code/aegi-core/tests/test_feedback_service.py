# Author: msq
"""Assertion feedback service and API tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from conftest import requires_postgres

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import AegiHTTPError
from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.assertion_feedback import AssertionFeedback
from aegi_core.db.models.case import Case
from aegi_core.db.session import ENGINE
from aegi_core.services import feedback_service
from aegi_core.settings import settings

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _prepare_schema() -> None:
    _ensure_tables()


@pytest.fixture()
def _override_deps():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original


@pytest.fixture()
def _mock_event_bus(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    bus = AsyncMock()
    monkeypatch.setattr(
        "aegi_core.services.feedback_service.get_event_bus", lambda: bus
    )
    return bus


async def _seed_case_assertion() -> tuple[str, str]:
    token = uuid.uuid4().hex[:10]
    case_uid = f"case_fb_{token}"
    assertion_uid = f"assert_fb_{token}"
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        session.add(Case(uid=case_uid, title="feedback case"))
        await session.flush()
        session.add(
            Assertion(
                uid=assertion_uid,
                case_uid=case_uid,
                kind="fact",
                value={"fact": token},
                source_claim_uids=[],
                confidence=0.8,
            )
        )
        await session.commit()
    return case_uid, assertion_uid


async def _seed_assertion(case_uid: str) -> str:
    token = uuid.uuid4().hex[:10]
    assertion_uid = f"assert_fb_{token}"
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        session.add(
            Assertion(
                uid=assertion_uid,
                case_uid=case_uid,
                kind="fact",
                value={"fact": token},
                source_claim_uids=[],
                confidence=0.7,
            )
        )
        await session.commit()
    return assertion_uid


@pytest.mark.asyncio
async def test_create_feedback(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        row = await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="user_a",
            verdict="agree",
            comment="looks good",
        )

    assert row.assertion_uid == assertion_uid
    assert row.user_id == "user_a"
    assert row.verdict == "agree"


@pytest.mark.asyncio
async def test_create_feedback_assertion_not_found(_mock_event_bus: AsyncMock) -> None:
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        with pytest.raises(AegiHTTPError) as exc_info:
            await feedback_service.create_feedback(
                session,
                assertion_uid="assert_missing",
                user_id="user_a",
                verdict="agree",
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "not_found"


@pytest.mark.asyncio
async def test_upsert_feedback(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        created = await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="user_a",
            verdict="agree",
            comment="v1",
        )
        updated = await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="user_a",
            verdict="disagree",
            comment="v2",
            confidence_override=0.3,
        )

        count = (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(AssertionFeedback)
                .where(
                    AssertionFeedback.assertion_uid == assertion_uid,
                    AssertionFeedback.user_id == "user_a",
                )
            )
        ).scalar_one()

    assert created.uid == updated.uid
    assert count == 1
    assert updated.verdict == "disagree"
    assert updated.comment == "v2"
    assert updated.confidence_override == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_delete_feedback(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        row = await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="user_a",
            verdict="agree",
        )
        await feedback_service.delete_feedback(
            session,
            assertion_uid=assertion_uid,
            feedback_uid=row.uid,
            user_id="user_a",
        )

        after = (
            await session.execute(
                sa.select(AssertionFeedback).where(AssertionFeedback.uid == row.uid)
            )
        ).scalar_one_or_none()

    assert after is None


@pytest.mark.asyncio
async def test_feedback_summary_agreed(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u1", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u2", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u3", verdict="disagree"
        )
        summary = await feedback_service.get_feedback_summary(session, assertion_uid)

    assert summary["consensus"] == "agreed"
    assert summary["agree_count"] == 2


@pytest.mark.asyncio
async def test_feedback_summary_disputed(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u1", verdict="disagree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u2", verdict="disagree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u3", verdict="agree"
        )
        summary = await feedback_service.get_feedback_summary(session, assertion_uid)

    assert summary["consensus"] == "disputed"
    assert summary["disagree_count"] == 2


@pytest.mark.asyncio
async def test_feedback_summary_no_feedback(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        summary = await feedback_service.get_feedback_summary(session, assertion_uid)

    assert summary["total_feedback"] == 0
    assert summary["consensus"] == "no_feedback"


@pytest.mark.asyncio
async def test_feedback_summary_mixed(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u1", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u2", verdict="disagree"
        )
        await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="u3",
            verdict="partially_agree",
        )
        summary = await feedback_service.get_feedback_summary(session, assertion_uid)

    assert summary["consensus"] == "mixed"


@pytest.mark.asyncio
async def test_avg_confidence_override(_mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="u1",
            verdict="agree",
            confidence_override=0.6,
        )
        await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="u2",
            verdict="agree",
            confidence_override=0.8,
        )
        await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="u3",
            verdict="disagree",
        )
        summary = await feedback_service.get_feedback_summary(session, assertion_uid)

    assert summary["avg_confidence_override"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_case_feedback_stats(_mock_event_bus: AsyncMock) -> None:
    case_uid, assertion_1 = await _seed_case_assertion()
    assertion_2 = await _seed_assertion(case_uid)
    _ = await _seed_assertion(case_uid)

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_1, user_id="u1", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_1, user_id="u2", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_2, user_id="u3", verdict="disagree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_2, user_id="u4", verdict="disagree"
        )
        stats = await feedback_service.get_case_feedback_stats(session, case_uid)

    assert stats["total_assertions"] == 3
    assert stats["assertions_with_feedback"] == 2
    assert stats["feedback_coverage"] == pytest.approx(2 / 3)
    assert stats["overall_agreement_rate"] == pytest.approx(0.5)
    assert assertion_2 in stats["disputed_assertions"]


@pytest.mark.asyncio
async def test_case_feedback_coverage(_mock_event_bus: AsyncMock) -> None:
    case_uid, assertion_1 = await _seed_case_assertion()
    _ = await _seed_assertion(case_uid)

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_1, user_id="u1", verdict="agree"
        )
        stats = await feedback_service.get_case_feedback_stats(session, case_uid)

    assert stats["feedback_coverage"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_feedback_emits_event(_mock_event_bus: AsyncMock) -> None:
    case_uid, assertion_uid = await _seed_case_assertion()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session,
            assertion_uid=assertion_uid,
            user_id="user_a",
            verdict="agree",
            confidence_override=0.9,
        )

    _mock_event_bus.emit.assert_awaited_once()
    event = _mock_event_bus.emit.await_args.args[0]
    assert event.event_type == "assertion.feedback_received"
    assert event.case_uid == case_uid
    assert event.payload["assertion_uid"] == assertion_uid
    assert event.payload["verdict"] == "agree"


@pytest.mark.asyncio
async def test_api_create_feedback(_override_deps, _mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/assertions/{assertion_uid}/feedback",
            json={
                "user_id": "api_user",
                "verdict": "agree",
                "confidence_override": 0.85,
                "comment": "looks good",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["assertion_uid"] == assertion_uid
    assert body["user_id"] == "api_user"
    assert body["verdict"] == "agree"


@pytest.mark.asyncio
async def test_api_get_feedback_summary(
    _override_deps, _mock_event_bus: AsyncMock
) -> None:
    _, assertion_uid = await _seed_case_assertion()
    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u1", verdict="agree"
        )
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u2", verdict="disagree"
        )

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/assertions/{assertion_uid}/feedback/summary")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_feedback"] == 2
    assert body["consensus"] == "mixed"


@pytest.mark.asyncio
async def test_api_case_feedback_stats(
    _override_deps, _mock_event_bus: AsyncMock
) -> None:
    case_uid, assertion_uid = await _seed_case_assertion()
    _ = await _seed_assertion(case_uid)

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="u1", verdict="agree"
        )

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/cases/{case_uid}/feedback/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["case_uid"] == case_uid
    assert body["total_assertions"] == 2
    assert body["assertions_with_feedback"] == 1
    assert body["feedback_coverage"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_api_delete_feedback_owner_only(
    _override_deps, _mock_event_bus: AsyncMock
) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async with AsyncSession(ENGINE, expire_on_commit=False) as session:
        row = await feedback_service.create_feedback(
            session, assertion_uid=assertion_uid, user_id="owner", verdict="agree"
        )

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        forbidden_resp = await client.delete(
            f"/assertions/{assertion_uid}/feedback/{row.uid}",
            params={"user_id": "not_owner"},
        )
        deleted_resp = await client.delete(
            f"/assertions/{assertion_uid}/feedback/{row.uid}",
            params={"user_id": "owner"},
        )

    assert forbidden_resp.status_code == 403
    assert deleted_resp.status_code == 200
    assert deleted_resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_api_validation(_override_deps, _mock_event_bus: AsyncMock) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/assertions/{assertion_uid}/feedback",
            json={"user_id": "api_user", "verdict": "wrong_value"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_confidence_override_range(
    _override_deps,
    _mock_event_bus: AsyncMock,
) -> None:
    _, assertion_uid = await _seed_case_assertion()

    async def _db_override():
        async with AsyncSession(ENGINE, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = _db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/assertions/{assertion_uid}/feedback",
            json={
                "user_id": "api_user",
                "verdict": "agree",
                "confidence_override": 1.5,
            },
        )

    assert resp.status_code == 422
