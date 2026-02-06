# Author: msq

import pytest
from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app


def test_tools_meta_search_has_ok_field() -> None:
    client = TestClient(app)
    resp = client.post("/tools/meta_search", json={"q": "example"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body


def test_tools_archive_url_has_ok_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body


def test_tools_archive_url_denied_without_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEGI_GATEWAY_ALLOW_DOMAINS", raising=False)

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com"})
    assert resp.status_code == 403
    body = resp.json()
    assert "error_code" in body
    assert "message" in body
    assert "details" in body


def test_tools_doc_parse_has_ok_field() -> None:
    client = TestClient(app)
    resp = client.post("/tools/doc_parse", json={"artifact_version_uid": "av_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
