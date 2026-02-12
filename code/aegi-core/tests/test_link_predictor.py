# Author: msq
"""PyKEEN link predictor service tests."""

from __future__ import annotations

import random

import pytest

from aegi_core.services.link_predictor import (
    InsufficientTriplesError,
    LinkPredictor,
    ModelNotTrainedError,
)

pytest.importorskip("pykeen")


def _make_test_triples(n: int = 120) -> list[tuple[str, str, str]]:
    """构造测试三元组。"""
    random.seed(42)
    entities = [f"entity_{i}" for i in range(10)]
    relations = ["allies_with", "opposes", "trades_with"]
    triples: set[tuple[str, str, str]] = set()
    while len(triples) < n:
        head = random.choice(entities)
        relation = random.choice(relations)
        tail = random.choice(entities)
        if head != tail:
            triples.add((head, relation, tail))
    return sorted(triples)


class _FakeNeo4j:
    def __init__(self, triples: list[tuple[str, str, str]]) -> None:
        self._triples = triples

    async def get_all_triples(self, case_uid: str) -> list[tuple[str, str, str]]:
        return self._triples

    async def get_entity_names(self, case_uid: str) -> dict[str, str]:
        names: dict[str, str] = {}
        for head, _, tail in self._triples:
            names.setdefault(head, head.replace("_", " ").title())
            names.setdefault(tail, tail.replace("_", " ").title())
        return names


async def test_train_success():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples()))
    result = await predictor.train("case-1", embedding_dim=16, num_epochs=1)
    assert result.model_name == "RotatE"
    assert result.num_triples >= 100
    assert result.mrr > 0


async def test_train_too_few_triples():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples(20)))
    with pytest.raises(InsufficientTriplesError):
        await predictor.train("case-2", embedding_dim=16, num_epochs=1)


async def test_predict_missing_links():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples()))
    await predictor.train("case-3", embedding_dim=16, num_epochs=1)
    predictions = await predictor.predict_missing_links(
        "case-3",
        top_k=5,
        min_score=0.0,
    )
    assert predictions
    assert predictions[0].head_uid
    assert predictions[0].relation
    assert predictions[0].tail_uid
    assert 0.0 <= predictions[0].score <= 1.0


async def test_predict_for_entity():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples()))
    await predictor.train("case-4", embedding_dim=16, num_epochs=1)
    predictions = await predictor.predict_for_entity(
        "case-4",
        "entity_0",
        direction="both",
        top_k=5,
    )
    assert predictions
    assert all(item.head_uid and item.tail_uid for item in predictions)


async def test_detect_anomalies():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples()))
    await predictor.train("case-5", embedding_dim=16, num_epochs=1)
    anomalies = await predictor.detect_anomalous_triples("case-5", threshold=0.99)
    assert isinstance(anomalies, list)
    assert all(0.0 <= item.score <= 1.0 for item in anomalies)


async def test_predict_without_training():
    predictor = LinkPredictor(_FakeNeo4j(_make_test_triples()))
    with pytest.raises(ModelNotTrainedError):
        await predictor.predict_missing_links("case-6")
