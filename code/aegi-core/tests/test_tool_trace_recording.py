# Author: msq

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.deps import get_tool_client
from aegi_core.api.errors import AegiHTTPError
from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.settings import settings
from conftest import requires_postgres

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


class _FakeToolClient:
    async def archive_url(self, url: str) -> dict:
        return {
            "ok": False,
            "tool": "archive_url",
            "error_code": "not_implemented",
            "url": url,
            "policy": {
                "allowed": True,
                "reason": "allowed",
                "domain": "example.com",
                "robots": {
                    "checked": False,
                    "allowed": None,
                    "reason": "p0_fixtures_only",
                },
            },
        }


class _FakeDeniedToolClient:
    async def archive_url(self, url: str) -> dict:
        raise AegiHTTPError(
            403,
            "policy_denied",
            "Policy denied request",
            {"url": url, "domain": "example.com", "reason": "domain_not_allowed"},
        )


class _FakeRateLimitedToolClient:
    async def archive_url(self, url: str) -> dict:
        raise AegiHTTPError(
            429,
            "rate_limited",
            "Rate limited",
            {"url": url, "domain": "example.com", "reason": "min_interval_not_elapsed"},
        )


class _FakeGatewayErrorToolClient:
    async def archive_url(self, url: str) -> dict:
        raise AegiHTTPError(
            502,
            "gateway_error",
            "Gateway error",
            {"body": {"upstream": "unavailable"}},
        )


def test_core_records_tool_trace_for_gateway_call() -> None:
    _ensure_tables()

    app.dependency_overrides[get_tool_client] = lambda: _FakeToolClient()
    try:
        client = TestClient(app)

        created = client.post(
            "/cases",
            json={"title": "Trace case", "actor_id": "user_1", "rationale": "init"},
        )
        assert created.status_code == 201
        case_uid = created.json()["case_uid"]

        called = client.post(
            f"/cases/{case_uid}/tools/archive_url",
            json={
                "url": "https://example.com/x",
                "actor_id": "user_1",
                "rationale": "call",
            },
        )
        assert called.status_code == 200
        body = called.json()
        assert "action_uid" in body
        assert "tool_trace_uid" in body

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with engine.begin() as conn:
            row = (
                conn.execute(
                    sa.text(
                        "select uid, tool_name, status from tool_traces where uid = :uid"
                    ),
                    {"uid": body["tool_trace_uid"]},
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["tool_name"] == "archive_url"
    finally:
        app.dependency_overrides.clear()


def test_core_records_tool_trace_when_gateway_denies() -> None:
    _ensure_tables()

    app.dependency_overrides[get_tool_client] = lambda: _FakeDeniedToolClient()
    try:
        client = TestClient(app)

        created = client.post(
            "/cases",
            json={
                "title": "Trace case denied",
                "actor_id": "user_1",
                "rationale": "init",
            },
        )
        assert created.status_code == 201
        case_uid = created.json()["case_uid"]

        called = client.post(
            f"/cases/{case_uid}/tools/archive_url",
            json={
                "url": "https://example.com/x",
                "actor_id": "user_1",
                "rationale": "call",
            },
        )
        assert called.status_code == 403
        body = called.json()
        assert body["error_code"] == "policy_denied"

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with engine.begin() as conn:
            row = (
                conn.execute(
                    sa.text(
                        "select uid, tool_name, status, error from tool_traces "
                        "where case_uid = :case_uid order by created_at desc limit 1"
                    ),
                    {"case_uid": case_uid},
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["tool_name"] == "archive_url"
        assert row["status"] == "denied"
        assert row["error"] == "policy_denied"
    finally:
        app.dependency_overrides.clear()


def test_core_records_tool_trace_when_rate_limited() -> None:
    _ensure_tables()

    app.dependency_overrides[get_tool_client] = lambda: _FakeRateLimitedToolClient()
    try:
        client = TestClient(app)
        created = client.post(
            "/cases",
            json={
                "title": "Trace case rate limit",
                "actor_id": "user_1",
                "rationale": "init",
            },
        )
        case_uid = created.json()["case_uid"]

        called = client.post(
            f"/cases/{case_uid}/tools/archive_url",
            json={
                "url": "https://example.com/x",
                "actor_id": "user_1",
                "rationale": "call",
            },
        )
        assert called.status_code == 429
        assert called.json()["error_code"] == "rate_limited"

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with engine.begin() as conn:
            row = (
                conn.execute(
                    sa.text(
                        "select status, error from tool_traces "
                        "where case_uid = :case_uid order by created_at desc limit 1"
                    ),
                    {"case_uid": case_uid},
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["status"] == "denied"
        assert row["error"] == "rate_limited"
    finally:
        app.dependency_overrides.clear()


def test_core_records_tool_trace_when_gateway_errors() -> None:
    _ensure_tables()

    app.dependency_overrides[get_tool_client] = lambda: _FakeGatewayErrorToolClient()
    try:
        client = TestClient(app)
        created = client.post(
            "/cases",
            json={
                "title": "Trace case error",
                "actor_id": "user_1",
                "rationale": "init",
            },
        )
        case_uid = created.json()["case_uid"]

        called = client.post(
            f"/cases/{case_uid}/tools/archive_url",
            json={
                "url": "https://example.com/x",
                "actor_id": "user_1",
                "rationale": "call",
            },
        )
        assert called.status_code == 502
        assert called.json()["error_code"] == "gateway_error"

        engine = sa.create_engine(settings.postgres_dsn_sync)
        with engine.begin() as conn:
            row = (
                conn.execute(
                    sa.text(
                        "select status, error from tool_traces "
                        "where case_uid = :case_uid order by created_at desc limit 1"
                    ),
                    {"case_uid": case_uid},
                )
                .mappings()
                .first()
            )
        assert row is not None
        assert row["status"] == "error"
        assert row["error"] == "gateway_error"
    finally:
        app.dependency_overrides.clear()
