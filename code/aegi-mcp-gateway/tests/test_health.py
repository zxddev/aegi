from fastapi.testclient import TestClient

from aegi_mcp_gateway.api.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
