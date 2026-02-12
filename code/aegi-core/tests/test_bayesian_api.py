"""贝叶斯 ACH API 端点测试 — 8 个测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.api.main import app
from aegi_core.services.bayesian_ach import (
    EvidenceAssessmentRequest,
    EvidenceJudgment,
)
from aegi_core.services.event_bus import reset_event_bus


@pytest.fixture(autouse=True)
def _reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture()
def _override_deps():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides = original


# ── 辅助函数 ───────────────────────────────────────────────────────


def _fake_hyp(uid, case_uid, label, prior=None, posterior=None):
    m = MagicMock()
    m.uid = uid
    m.case_uid = case_uid
    m.label = label
    m.prior_probability = prior
    m.posterior_probability = posterior
    m.supporting_assertion_uids = []
    m.contradicting_assertion_uids = []
    m.coverage_score = 0.0
    m.confidence = 0.0
    m.gap_list = []
    m.adversarial_result = {}
    m.trace_id = None
    m.prompt_version = None
    m.modality = None
    m.segment_ref = None
    m.media_time_range = None
    m.created_at = None
    return m


# ── 测试 ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_probabilities_empty(_override_deps):
    """没有假设 → 返回空列表。"""
    session = AsyncMock()
    # get_state 查询：假设（空）
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/cases/case_x/hypotheses/probabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hypotheses"] == []


@pytest.mark.asyncio
async def test_get_probabilities_after_update(_override_deps):
    """更新后返回正确的后验概率。"""
    from aegi_core.services.bayesian_ach import BayesianState

    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.get_state.return_value = BayesianState(
            case_uid="case_1",
            hypotheses=[
                {
                    "uid": "h1",
                    "label": "H1",
                    "prior": 0.5,
                    "posterior": 0.7,
                    "history": [],
                },
                {
                    "uid": "h2",
                    "label": "H2",
                    "prior": 0.5,
                    "posterior": 0.3,
                    "history": [],
                },
            ],
            total_evidence_count=1,
            last_updated=None,
        )
        MockEngine.return_value = instance

        session = AsyncMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/cases/case_1/hypotheses/probabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["hypotheses"]) == 2
        assert data["hypotheses"][0]["posterior"] == 0.7


@pytest.mark.asyncio
async def test_initialize_priors_uniform(_override_deps):
    """不传 priors → 均匀分布。"""
    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.initialize_priors.return_value = {"h1": 0.5, "h2": 0.5}
        MockEngine.return_value = instance

        session = AsyncMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/cases/c1/hypotheses/initialize-priors", json={})
        assert resp.status_code == 200
        assert resp.json()["priors"] == {"h1": 0.5, "h2": 0.5}


@pytest.mark.asyncio
async def test_initialize_priors_custom(_override_deps):
    """自定义 priors 总和为 1.0 → 接受。"""
    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.initialize_priors.return_value = {"h1": 0.6, "h2": 0.4}
        MockEngine.return_value = instance

        session = AsyncMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/cases/c1/hypotheses/initialize-priors",
                json={"priors": {"h1": 0.6, "h2": 0.4}},
            )
        assert resp.status_code == 200
        assert resp.json()["priors"]["h1"] == 0.6


@pytest.mark.asyncio
async def test_initialize_priors_invalid_sum(_override_deps):
    """Priors 总和 ≠ 1.0 → 422。"""
    session = AsyncMock()

    async def _fake_db():
        yield session

    app.dependency_overrides[get_db_session] = _fake_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/cases/c1/hypotheses/initialize-priors",
            json={"priors": {"h1": 0.5, "h2": 0.3}},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_manual_bayesian_update(_override_deps):
    """POST bayesian-update 返回正确的先验/后验。"""
    from aegi_core.services.bayesian_ach import BayesianUpdateResult

    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.assess_evidence.return_value = []
        instance.update.return_value = BayesianUpdateResult(
            evidence_uid="ev1",
            prior_distribution={"h1": 0.5, "h2": 0.5},
            posterior_distribution={"h1": 0.7, "h2": 0.3},
            likelihoods={"h1": 0.85, "h2": 0.3},
            diagnosticity={"h1": 2.83, "h2": 0.35},
            max_change=0.2,
            most_affected_hypothesis_uid="h1",
        )
        MockEngine.return_value = instance

        session = AsyncMock()
        mock_llm = MagicMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db
        app.dependency_overrides[get_llm_client] = lambda: mock_llm

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/cases/c1/hypotheses/bayesian-update",
                json={"evidence_uid": "ev1", "evidence_text": "some text"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_change"] == 0.2
        assert data["posterior_distribution"]["h1"] == 0.7


@pytest.mark.asyncio
async def test_expert_override(_override_deps):
    """PUT assessment → 返回更新后的评估。"""
    mock_ea = MagicMock()
    mock_ea.uid = "ea_1"
    mock_ea.hypothesis_uid = "h1"
    mock_ea.evidence_uid = "ev1"
    mock_ea.relation = "support"
    mock_ea.strength = 0.9
    mock_ea.likelihood = 0.91
    mock_ea.assessed_by = "expert"

    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.override_assessment.return_value = mock_ea
        MockEngine.return_value = instance

        session = AsyncMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(
                "/cases/c1/evidence-assessments/ea_1",
                json={"relation": "support", "strength": 0.9},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["assessed_by"] == "expert"
        assert data["likelihood"] == 0.91


@pytest.mark.asyncio
async def test_diagnosticity_ranking(_override_deps):
    """GET diagnosticity 返回排序列表。"""
    with patch("aegi_core.api.routes.bayesian.BayesianACH") as MockEngine:
        instance = AsyncMock()
        instance.get_diagnosticity_ranking.return_value = [
            {
                "evidence_uid": "ev1",
                "diagnosticity": 4.5,
                "most_discriminated": ["h1", "h2"],
            },
            {
                "evidence_uid": "ev2",
                "diagnosticity": 2.0,
                "most_discriminated": ["h1", "h3"],
            },
        ]
        MockEngine.return_value = instance

        session = AsyncMock()

        async def _fake_db():
            yield session

        app.dependency_overrides[get_db_session] = _fake_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/cases/c1/hypotheses/diagnosticity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["rankings"]) == 2
        assert data["rankings"][0]["diagnosticity"] == 4.5
