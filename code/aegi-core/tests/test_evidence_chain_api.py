# Author: msq
from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from aegi_core.api.main import app
from aegi_core.db.base import Base
from aegi_core.db.models.artifact import ArtifactIdentity, ArtifactVersion
from aegi_core.db.models.assertion import Assertion
from aegi_core.db.models.chunk import Chunk
from aegi_core.db.models.evidence import Evidence
from aegi_core.db.models.judgment import Judgment
from aegi_core.db.models.source_claim import SourceClaim
from aegi_core.settings import settings
from conftest import requires_postgres

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


def test_p0_evidence_chain_navigation_endpoints() -> None:
    _ensure_tables()

    client = TestClient(app)

    created = client.post(
        "/cases",
        json={"title": "Fixture case", "actor_id": "user_1", "rationale": "init"},
    )
    assert created.status_code == 201
    case_uid = created.json()["case_uid"]

    suffix = uuid4().hex
    artifact_identity_uid = f"ai_{suffix}"
    artifact_version_uid = f"av_{suffix}"
    chunk_uid = f"chunk_{suffix}"
    evidence_uid = f"ev_{suffix}"
    source_claim_uid = f"sc_{suffix}"
    assertion_uid = f"as_{suffix}"
    judgment_uid = f"jd_{suffix}"

    engine = sa.create_engine(settings.postgres_dsn_sync)
    with Session(engine) as session:
        session.add(ArtifactIdentity(uid=artifact_identity_uid, kind="html"))
        session.add(
            ArtifactVersion(
                uid=artifact_version_uid,
                artifact_identity_uid=artifact_identity_uid,
                case_uid=case_uid,
                storage_ref="minio://fixtures/defgeo-001/artifact.html",
                content_sha256="sha256_dummy",
                content_type="text/html",
                source_meta={},
            )
        )
        session.add(
            Chunk(
                uid=chunk_uid,
                artifact_version_uid=artifact_version_uid,
                ordinal=0,
                text="Exampleland announced that it will conduct a maritime exercise near the Strait of Example.",
                anchor_set=[
                    {
                        "type": "TextQuoteSelector",
                        "exact": "Exampleland announced that it will conduct a maritime exercise near the Strait of Example.",
                    }
                ],
                anchor_health={},
            )
        )
        session.add(
            Evidence(
                uid=evidence_uid,
                case_uid=case_uid,
                artifact_version_uid=artifact_version_uid,
                chunk_uid=chunk_uid,
                kind="quote",
                license_note=None,
                pii_flags={},
                retention_policy={},
            )
        )
        session.add(
            SourceClaim(
                uid=source_claim_uid,
                case_uid=case_uid,
                artifact_version_uid=artifact_version_uid,
                chunk_uid=chunk_uid,
                evidence_uid=evidence_uid,
                quote="Exampleland announced that it will conduct a maritime exercise near the Strait of Example.",
                selectors=[
                    {
                        "type": "TextQuoteSelector",
                        "exact": "Exampleland announced that it will conduct a maritime exercise near the Strait of Example.",
                    }
                ],
                attributed_to=None,
                modality=None,
            )
        )
        session.add(
            Assertion(
                uid=assertion_uid,
                case_uid=case_uid,
                kind="event",
                value={},
                source_claim_uids=[source_claim_uid],
                confidence=None,
            )
        )
        session.add(
            Judgment(
                uid=judgment_uid,
                case_uid=case_uid,
                title="P0 Judgment",
                assertion_uids=[assertion_uid],
            )
        )
        session.commit()

    artifacts = client.get(f"/cases/{case_uid}/artifacts")
    assert artifacts.status_code == 200
    assert any(
        a["artifact_version_uid"] == artifact_version_uid
        for a in artifacts.json()["items"]
    )

    av = client.get(f"/artifacts/versions/{artifact_version_uid}")
    assert av.status_code == 200
    assert av.json()["artifact_version_uid"] == artifact_version_uid

    ev = client.get(f"/evidence/{evidence_uid}")
    assert ev.status_code == 200
    assert ev.json()["evidence_uid"] == evidence_uid
    assert ev.json()["chunk_uid"] == chunk_uid
    assert ev.json()["artifact_version_uid"] == artifact_version_uid

    sc = client.get(f"/source_claims/{source_claim_uid}")
    assert sc.status_code == 200
    assert sc.json()["source_claim_uid"] == source_claim_uid

    a = client.get(f"/assertions/{assertion_uid}")
    assert a.status_code == 200
    assert source_claim_uid in a.json()["source_claim_uids"]

    j = client.get(f"/judgments/{judgment_uid}")
    assert j.status_code == 200
    assert assertion_uid in j.json()["assertion_uids"]


def test_not_found_uses_unified_error_shape() -> None:
    _ensure_tables()

    client = TestClient(app)
    resp = client.get("/cases/case_does_not_exist")
    assert resp.status_code == 404
    body = resp.json()
    assert "error_code" in body
    assert "message" in body
    assert "details" in body
