# Author: msq

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.settings import settings
from conftest import requires_postgres

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


def test_import_fixture_creates_navigable_evidence_chain() -> None:
    _ensure_tables()

    client = TestClient(app)
    created = client.post(
        "/cases",
        json={"title": "Fixture case", "actor_id": "user_1", "rationale": "init"},
    )
    assert created.status_code == 201
    case_uid = created.json()["case_uid"]

    imported = client.post(
        f"/cases/{case_uid}/fixtures/import",
        json={"fixture_id": "defgeo-001", "actor_id": "user_1", "rationale": "import"},
    )
    assert imported.status_code == 201
    body = imported.json()

    assert body["fixture_id"] == "defgeo-001"
    assert "action_uid" in body
    assert "artifact_version_uid" in body
    assert body["chunk_uids"]
    assert body["evidence_uids"]
    assert body["source_claim_uids"]
    assert body["assertion_uids"]
    assert "judgment_uid" in body

    artifacts = client.get(f"/cases/{case_uid}/artifacts")
    assert artifacts.status_code == 200
    assert any(
        a["artifact_version_uid"] == body["artifact_version_uid"]
        for a in artifacts.json()["items"]
    )

    ev_uid = body["evidence_uids"][0]
    ev = client.get(f"/evidence/{ev_uid}")
    assert ev.status_code == 200
    assert ev.json()["artifact_version_uid"] == body["artifact_version_uid"]

    sc_uid = body["source_claim_uids"][0]
    sc = client.get(f"/source_claims/{sc_uid}")
    assert sc.status_code == 200
    assert sc.json()["evidence_uid"] == ev_uid

    as_uid = body["assertion_uids"][0]
    a = client.get(f"/assertions/{as_uid}")
    assert a.status_code == 200
    assert sc_uid in a.json()["source_claim_uids"]

    jd = client.get(f"/judgments/{body['judgment_uid']}")
    assert jd.status_code == 200
    assert as_uid in jd.json()["assertion_uids"]
