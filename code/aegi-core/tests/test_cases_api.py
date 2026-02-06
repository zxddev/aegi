import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.settings import settings


def _ensure_tables() -> None:
    # Minimal integration setup for P0.
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


def test_create_case_returns_case_uid_and_action_uid() -> None:
    _ensure_tables()

    client = TestClient(app)
    resp = client.post(
        "/cases",
        json={"title": "Example case", "actor_id": "user_1", "rationale": "init"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Example case"
    assert "case_uid" in body
    assert "action_uid" in body


def test_get_case_by_uid() -> None:
    _ensure_tables()

    client = TestClient(app)
    created = client.post(
        "/cases",
        json={"title": "Case A", "actor_id": "user_1", "rationale": "init"},
    )
    assert created.status_code == 201
    case_uid = created.json()["case_uid"]

    fetched = client.get(f"/cases/{case_uid}")
    assert fetched.status_code == 200
    assert fetched.json()["case_uid"] == case_uid
