# Author: msq

import pytest
from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app


def _fake_response(status_code: int = 200, **kwargs):
    """构造可调用 raise_for_status 的 httpx.Response。"""
    import httpx

    req = httpx.Request("GET", "http://fake")
    return httpx.Response(status_code, request=req, **kwargs)


def test_tools_meta_search_has_ok_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """mock SearxNG 返回，验证 meta_search 正常响应。"""
    import httpx

    async def _mock_get(self, url, **kwargs):
        return _fake_response(json={"results": [{"title": "t", "url": "http://x"}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    client = TestClient(app)
    resp = client.post("/tools/meta_search", json={"q": "example"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["results"]) == 1


def test_tools_archive_url_has_ok_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "example.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body


def test_tools_archive_url_denied_when_domain_not_in_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEGI_GATEWAY_ALLOW_DOMAINS", "other.com")

    client = TestClient(app)
    resp = client.post("/tools/archive_url", json={"url": "https://example.com"})
    assert resp.status_code == 403
    body = resp.json()
    assert "error_code" in body
    assert "message" in body
    assert "details" in body


def test_tools_doc_parse_requires_file_url() -> None:
    """file_url 缺失时返回 422。"""
    client = TestClient(app)
    resp = client.post("/tools/doc_parse", json={"artifact_version_uid": "av_test"})
    assert resp.status_code == 422


def test_tools_doc_parse_has_ok_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """mock Unstructured 返回，验证 doc_parse 正常响应。"""
    import httpx

    async def _mock_get(self, url, **kwargs):
        return _fake_response(content=b"hello", headers={"content-type": "text/plain"})

    async def _mock_post(self, url, **kwargs):
        return _fake_response(
            json=[{"text": "parsed chunk", "type": "NarrativeText", "metadata": {}}]
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)
    client = TestClient(app)
    resp = client.post(
        "/tools/doc_parse",
        json={"artifact_version_uid": "av_test", "file_url": "http://minio/file.pdf"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["text"] == "parsed chunk"
