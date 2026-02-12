# Author: msq
"""Integration tests for upgraded stub routes (DB + service).

Covers: hypotheses, narratives, kg, forecast, quality, pipelines.
Each route has at least 1 integration test using httpx.AsyncClient + real DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from aegi_core.api.main import create_app
from aegi_core.db.base import Base
from aegi_core.settings import settings
from conftest import requires_llm, requires_postgres

pytestmark = requires_postgres


def _ensure_tables() -> None:
    import aegi_core.db.models  # noqa: F401

    engine = sa.create_engine(settings.postgres_dsn_sync)
    Base.metadata.create_all(engine)


@pytest.fixture(scope="module", autouse=True)
def _tables():
    _ensure_tables()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_case(client: AsyncClient, title: str = "test") -> str:
    resp = await client.post("/cases", json={"title": title})
    assert resp.status_code == 201
    return resp.json()["case_uid"]


# ---------------------------------------------------------------------------
# hypotheses
# ---------------------------------------------------------------------------


class TestHypothesesRoutes:
    async def test_generate_returns_action_uid(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "hyp-gen")
        resp = await client.post(
            f"/cases/{case_uid}/hypotheses/generate",
            json={"assertion_uids": [], "source_claim_uids": []},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert "hypotheses" in data
        assert "trace_id" in data


# ---------------------------------------------------------------------------
# narratives
# ---------------------------------------------------------------------------


class TestNarrativesRoutes:
    async def test_build_returns_action_uid(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "nar-build")
        resp = await client.post(
            f"/cases/{case_uid}/narratives/build",
            json={"source_claims": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert "narratives" in data

    async def test_detect_coordination_returns_action_uid(
        self, client: AsyncClient
    ) -> None:
        case_uid = await _create_case(client, "nar-detect")
        resp = await client.post(
            f"/cases/{case_uid}/narratives/detect_coordination",
            json={"source_claims": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert "signals" in data


# ---------------------------------------------------------------------------
# kg
# ---------------------------------------------------------------------------


@requires_llm
class TestKGRoutes:
    async def test_build_from_assertions_returns_action_uid(
        self, client: AsyncClient
    ) -> None:
        case_uid = await _create_case(client, "kg-build")
        now = datetime.now(timezone.utc).isoformat()
        resp = await client.post(
            f"/cases/{case_uid}/kg/build_from_assertions",
            json={
                "assertions": [
                    {
                        "uid": "a1",
                        "case_uid": case_uid,
                        "kind": "event",
                        "value": {
                            "attributed_to": "Actor-A",
                            "rationale": "deployment test",
                        },
                        "source_claim_uids": [],
                        "created_at": now,
                    }
                ],
                "ontology_version": "1.0.0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "action_uid" in data
        assert data["action_uid"].startswith("act_")


# ---------------------------------------------------------------------------
# forecast
# ---------------------------------------------------------------------------


class TestForecastRoutes:
    async def test_generate_returns_action_uid(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "fc-gen")
        resp = await client.post(
            f"/cases/{case_uid}/forecast/generate",
            json={"hypothesis_uids": [], "assertion_uids": []},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert "scenarios" in data

    async def test_backtest_returns_action_uid(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "fc-bt")
        resp = await client.post(
            f"/cases/{case_uid}/forecast/backtest",
            json={"scenario_id": "s1", "actual_outcomes": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_uid"].startswith("act_")
        assert data["precision"] == 0.0


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------


class TestQualityRoutes:
    async def test_score_judgment_returns_report(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "q-score")
        resp = await client.post(
            f"/cases/{case_uid}/quality/score_judgment",
            json={
                "judgment_uid": "jd_test",
                "title": "Test judgment",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["judgment_uid"] == "jd_test"
        assert "confidence_score" in data
        assert "status" in data

    async def test_get_judgment_quality_after_score(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "q-get")
        # 先 score
        await client.post(
            f"/cases/{case_uid}/quality/score_judgment",
            json={"judgment_uid": "jd_cached", "title": "Cached"},
        )
        # 再 get
        resp = await client.get(
            f"/cases/{case_uid}/quality/judgments/jd_cached",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["judgment_uid"] == "jd_cached"


# ---------------------------------------------------------------------------
# pipelines
# ---------------------------------------------------------------------------


class TestPipelinesRoutes:
    async def test_assertion_fuse_empty(self, client: AsyncClient) -> None:
        case_uid = await _create_case(client, "pipe-fuse")
        resp = await client.post(
            f"/cases/{case_uid}/pipelines/assertion_fuse",
            json={"source_claim_uids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "assertions" in data
        assert "action_uid" in data
