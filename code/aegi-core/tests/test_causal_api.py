# Author: msq
"""Causal inference API tests with mocked engine."""

from __future__ import annotations

import importlib.util
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

# `aegi_core.api.deps` imports these modules via llm_client.
if importlib.util.find_spec("instructor") is None and "instructor" not in sys.modules:
    instructor_stub = types.ModuleType("instructor")
    instructor_stub.from_openai = lambda client: client
    sys.modules["instructor"] = instructor_stub

if importlib.util.find_spec("openai") is None and "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _AsyncOpenAI:  # pragma: no cover - stub type only
        def __init__(self, *args, **kwargs) -> None: ...

    openai_stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_stub

from aegi_core.api.deps import get_causal_inference_engine
from aegi_core.api.routes.causal import router
from aegi_core.services.causal_inference import (
    CausalEffectResult,
    CausalGraphResult,
    DoWhyUnavailableError,
    RefutationResult,
)


class _FakeCausalInferenceEngine:
    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
        time_window: str | None = None,
    ) -> CausalEffectResult:
        return CausalEffectResult(
            treatment=treatment_entity_uid,
            treatment_name="Treatment X",
            outcome=outcome_entity_uid,
            outcome_name="Outcome Y",
            effect_estimate=1.9,
            confidence_interval=(1.5, 2.2),
            p_value=0.01,
            method=method,
            confounders=["Z"],
            confounder_names=["Confounder Z"],
            refutation_results=[
                RefutationResult(
                    method="placebo_treatment",
                    estimated_effect=1.9,
                    new_effect=0.02,
                    p_value=0.01,
                    passed=True,
                )
            ],
            is_significant=True,
            num_observations=24,
            warning=None,
        )

    async def build_causal_graph(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
    ) -> CausalGraphResult:
        return CausalGraphResult(
            treatment=treatment_entity_uid,
            outcome=outcome_entity_uid,
            confounders=["Z"],
            mediators=["M"],
            gml_graph='graph [ directed 1 node [ id "X" ] node [ id "Y" ] ]',
            num_paths=1,
            entity_names={"X": "Treatment X", "Y": "Outcome Y", "Z": "Confounder Z"},
        )


class _UnavailableCausalInferenceEngine(_FakeCausalInferenceEngine):
    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
        time_window: str | None = None,
    ) -> CausalEffectResult:
        raise DoWhyUnavailableError("DoWhy not installed")


class _InsufficientDataEngine(_FakeCausalInferenceEngine):
    async def estimate_effect(
        self,
        case_uid: str,
        treatment_entity_uid: str,
        outcome_entity_uid: str,
        *,
        method: str = "backdoor.linear_regression",
        time_window: str | None = None,
    ) -> CausalEffectResult:
        return CausalEffectResult(
            treatment=treatment_entity_uid,
            treatment_name=treatment_entity_uid,
            outcome=outcome_entity_uid,
            outcome_name=outcome_entity_uid,
            effect_estimate=0.0,
            confidence_interval=(0.0, 0.0),
            p_value=None,
            method=method,
            confounders=[],
            confounder_names=[],
            refutation_results=[],
            is_significant=False,
            num_observations=3,
            warning="观测数不足",
        )


def _make_client(engine: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_causal_inference_engine] = lambda: engine
    return TestClient(app)


def test_estimate_endpoint():
    with _make_client(_FakeCausalInferenceEngine()) as client:
        response = client.post(
            "/cases/case-1/causal/estimate",
            json={
                "treatment_entity_uid": "X",
                "outcome_entity_uid": "Y",
                "method": "backdoor.linear_regression",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["effect_estimate"] > 0
        assert payload["is_significant"] is True


def test_graph_endpoint():
    with _make_client(_FakeCausalInferenceEngine()) as client:
        response = client.post(
            "/cases/case-1/causal/graph",
            json={"treatment_entity_uid": "X", "outcome_entity_uid": "Y"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["num_paths"] == 1
        assert payload["mediators"] == ["M"]


def test_dowhy_not_installed():
    with _make_client(_UnavailableCausalInferenceEngine()) as client:
        response = client.post(
            "/cases/case-1/causal/estimate",
            json={"treatment_entity_uid": "X", "outcome_entity_uid": "Y"},
        )
        assert response.status_code == 501


def test_insufficient_data_warning():
    with _make_client(_InsufficientDataEngine()) as client:
        response = client.post(
            "/cases/case-1/causal/estimate",
            json={"treatment_entity_uid": "X", "outcome_entity_uid": "Y"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["warning"] == "观测数不足"
        assert payload["is_significant"] is False
