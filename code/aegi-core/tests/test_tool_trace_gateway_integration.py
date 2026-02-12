# Author: msq

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

import httpx
import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.deps import get_tool_client
from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.settings import settings
from conftest import requires_gateway, requires_postgres

pytestmark = [requires_postgres, requires_gateway]


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


def _import_gateway_app(timeout: int = 5) -> object:
    tests_dir = Path(__file__).resolve().parent
    code_dir = tests_dir.parents[1]
    gateway_src = code_dir / "aegi-mcp-gateway" / "src"
    gateway_src_str = str(gateway_src)
    inserted = False
    if gateway_src_str not in sys.path:
        sys.path.insert(0, gateway_src_str)
        inserted = True

    def _timeout_handler(_signum: int, _frame: object) -> None:
        raise TimeoutError(f"Gateway app import timed out after {timeout}s")

    if hasattr(signal, "SIGALRM"):
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
    else:
        previous_handler = None

    try:
        from aegi_mcp_gateway.api.main import app as gateway_app  # type: ignore

        return gateway_app
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)
        if inserted:
            try:
                sys.path.remove(gateway_src_str)
            except ValueError:
                pass


class _AsgiGatewayToolClient:
    def __init__(self, gateway_app: object) -> None:
        self._gateway_app = gateway_app

    async def archive_url(self, url: str) -> dict:
        transport = httpx.ASGITransport(app=self._gateway_app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(
            transport=transport, base_url="http://gateway"
        ) as client:
            resp = await client.post("/tools/archive_url", json={"url": url})
            resp.raise_for_status()
            return resp.json()


def test_core_tool_trace_policy_from_real_gateway_response(monkeypatch) -> None:
    _ensure_tables()
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")

    gateway_app = _import_gateway_app()
    app.dependency_overrides[get_tool_client] = lambda: _AsgiGatewayToolClient(
        gateway_app
    )
    try:
        client = TestClient(app)
        created = client.post(
            "/cases",
            json={"title": "Trace case", "actor_id": "user_1", "rationale": "init"},
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
        assert called.status_code == 200
        tool_trace_uid = called.json()["tool_trace_uid"]

        fetched = client.get(f"/tool_traces/{tool_trace_uid}")
        assert fetched.status_code == 200
        policy = fetched.json()["policy"]
        assert policy["allowed"] is True
        assert policy["domain"] == "example.com"
    finally:
        app.dependency_overrides.clear()
        os.environ.pop("AEGI_GATEWAY_ALLOW_DOMAINS", None)
