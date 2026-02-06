# Author: msq

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.deps import get_tool_client
from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.settings import settings


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
                "robots": {"checked": False, "allowed": None, "reason": "p0_fixtures_only"},
            },
        }


def test_get_tool_trace_by_uid_returns_structured_fields() -> None:
    _ensure_tables()

    app.dependency_overrides[get_tool_client] = lambda: _FakeToolClient()
    try:
        client = TestClient(app)
        created = client.post(
            "/cases",
            json={"title": "Trace case", "actor_id": "user_1", "rationale": "init"},
        )
        case_uid = created.json()["case_uid"]

        called = client.post(
            f"/cases/{case_uid}/tools/archive_url",
            json={"url": "https://example.com/x", "actor_id": "user_1", "rationale": "call"},
        )
        tool_trace_uid = called.json()["tool_trace_uid"]

        fetched = client.get(f"/tool_traces/{tool_trace_uid}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["tool_trace_uid"] == tool_trace_uid
        assert body["case_uid"] == case_uid
        assert body["tool_name"] == "archive_url"
        assert "request" in body
        assert "response" in body
        assert "policy" in body
        assert "action_uid" in body
    finally:
        app.dependency_overrides.clear()
