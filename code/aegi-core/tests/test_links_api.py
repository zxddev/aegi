# Author: msq
"""Link prediction API tests with mocked LinkPredictor."""

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

from aegi_core.api.deps import get_link_predictor
from aegi_core.api.routes.links import router
from aegi_core.services.link_predictor import (
    AnomalousTriple,
    PredictedLink,
    PyKEENUnavailableError,
    TrainResult,
)


class _FakeLinkPredictor:
    async def train(self, case_uid: str, **kwargs) -> TrainResult:
        return TrainResult(
            model_name="RotatE",
            num_triples=120,
            num_entities=10,
            num_relations=3,
            mrr=0.42,
            hits_at_1=0.2,
            hits_at_10=0.7,
            training_time_seconds=1.234,
        )

    async def predict_missing_links(
        self,
        case_uid: str,
        **kwargs,
    ) -> list[PredictedLink]:
        return [
            PredictedLink(
                head_uid="entity_1",
                head_name="Entity 1",
                relation="allies_with",
                tail_uid="entity_2",
                tail_name="Entity 2",
                score=0.88,
                confidence="high",
            )
        ]

    async def predict_for_entity(
        self, case_uid: str, entity_uid: str, **kwargs
    ) -> list[PredictedLink]:
        return [
            PredictedLink(
                head_uid=entity_uid,
                head_name=entity_uid,
                relation="trades_with",
                tail_uid="entity_3",
                tail_name="Entity 3",
                score=0.63,
                confidence="medium",
            )
        ]

    async def detect_anomalous_triples(
        self, case_uid: str, **kwargs
    ) -> list[AnomalousTriple]:
        return [
            AnomalousTriple(
                head_uid="entity_4",
                relation="opposes",
                tail_uid="entity_5",
                score=0.04,
                existing=True,
                reason="不符合图结构模式",
            )
        ]


class _UnavailablePredictor(_FakeLinkPredictor):
    async def train(self, case_uid: str, **kwargs) -> TrainResult:
        raise PyKEENUnavailableError("PyKEEN not installed")


def _make_client(predictor: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_link_predictor] = lambda: predictor
    return TestClient(app)


def test_train_endpoint():
    with _make_client(_FakeLinkPredictor()) as client:
        resp = client.post("/cases/case-1/links/train", json={"num_epochs": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_name"] == "RotatE"
        assert data["mrr"] > 0


def test_predictions_endpoint():
    with _make_client(_FakeLinkPredictor()) as client:
        resp = client.get("/cases/case-1/links/predictions?top_k=5&min_score=0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["predictions"]) == 1
        assert data["predictions"][0]["relation"] == "allies_with"


def test_entity_predictions_endpoint():
    with _make_client(_FakeLinkPredictor()) as client:
        resp = client.get(
            "/cases/case-1/links/predictions/entity_0?direction=both&top_k=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["predictions"]) == 1
        assert data["predictions"][0]["head_uid"] == "entity_0"


def test_anomalies_endpoint():
    with _make_client(_FakeLinkPredictor()) as client:
        resp = client.get("/cases/case-1/links/anomalies?threshold=0.2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["score"] < 0.1


def test_pykeen_not_installed():
    with _make_client(_UnavailablePredictor()) as client:
        resp = client.post("/cases/case-1/links/train", json={})
        assert resp.status_code == 501
