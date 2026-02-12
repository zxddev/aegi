# Author: msq
"""DoWhy causal inference service tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import pytest

from aegi_core.services.causal_inference import CausalInferenceEngine
from aegi_core.settings import settings

pytest.importorskip("dowhy")


class _FakeNeo4j:
    def __init__(self, *, subgraph: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        self._subgraph = subgraph
        self._rows = rows

    async def get_subgraph(self, case_uid: str, *, limit: int = 5000) -> dict[str, Any]:
        return self._subgraph

    async def run_cypher(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return self._rows


def _make_subgraph() -> dict[str, Any]:
    return {
        "nodes": [
            {"uid": "X", "name": "Treatment X", "props": {}},
            {"uid": "Y", "name": "Outcome Y", "props": {}},
            {"uid": "Z", "name": "Confounder Z", "props": {}},
            {"uid": "M", "name": "Mediator M", "props": {}},
        ],
        "edges": [
            {"source": "X", "target": "M", "type": "CAUSES", "props": {}},
            {"source": "M", "target": "Y", "type": "CAUSES", "props": {}},
            {"source": "Z", "target": "X", "type": "AFFECTS", "props": {}},
            {"source": "Z", "target": "Y", "type": "AFFECTS", "props": {}},
        ],
    }


def _make_graph_rows(n_days: int = 15) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for day in range(n_days):
        created_at = (start + timedelta(days=day)).isoformat()
        rows.extend(
            [
                {
                    "node_uid": "X",
                    "node_created_at": created_at,
                    "neighbor_uid": "M",
                    "relation_created_at": created_at,
                    "node_tone": float(day % 3) / 10.0,
                    "node_goldstein_scale": 1.0,
                },
                {
                    "node_uid": "M",
                    "node_created_at": created_at,
                    "neighbor_uid": "Y",
                    "relation_created_at": created_at,
                    "node_tone": 0.2,
                    "node_goldstein_scale": 2.0,
                },
                {
                    "node_uid": "Z",
                    "node_created_at": created_at,
                    "neighbor_uid": "X",
                    "relation_created_at": created_at,
                    "node_tone": 0.1,
                    "node_goldstein_scale": 0.0,
                },
            ]
        )
    return rows


def _make_causal_data(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 0.5, n)
    y = 2.0 * x + 0.3 * z + rng.normal(0, 0.5, n)
    m = 0.8 * x + rng.normal(0, 0.3, n)
    return pd.DataFrame({"X": x, "Y": y, "Z": z, "M": m})


def _make_non_causal_data(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 0.5, n)
    y = 0.3 * z + rng.normal(0, 0.5, n)
    m = rng.normal(0, 1, n)
    return pd.DataFrame({"X": x, "Y": y, "Z": z, "M": m})


async def test_graph_to_dataframe():
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )
    frame = await engine._graph_to_dataframe(
        "case-1", ["X", "Y", "Z", "M"], window="1d"
    )
    assert frame.shape[0] >= 10
    assert set(frame.columns) == {"X", "Y", "Z", "M"}
    assert frame["X"].max() > 0.0


async def test_build_causal_graph():
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )
    result = await engine.build_causal_graph("case-1", "X", "Y")
    assert "M" in result.mediators
    assert "Z" in result.confounders
    assert result.num_paths >= 1
    assert "graph [" in result.gml_graph


async def test_estimate_effect_significant(monkeypatch: pytest.MonkeyPatch):
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )

    async def _fake_graph_to_dataframe(
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> pd.DataFrame:
        frame = _make_causal_data()
        for uid in entity_uids:
            if uid not in frame.columns:
                frame[uid] = 0.0
        return frame[entity_uids]

    monkeypatch.setattr(engine, "_graph_to_dataframe", _fake_graph_to_dataframe)
    result = await engine.estimate_effect("case-1", "X", "Y")
    assert result.effect_estimate > 0.5
    assert result.is_significant is True
    assert result.num_observations >= settings.causal_min_observations


async def test_estimate_effect_no_effect(monkeypatch: pytest.MonkeyPatch):
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )

    async def _fake_graph_to_dataframe(
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> pd.DataFrame:
        frame = _make_non_causal_data()
        for uid in entity_uids:
            if uid not in frame.columns:
                frame[uid] = 0.0
        return frame[entity_uids]

    monkeypatch.setattr(engine, "_graph_to_dataframe", _fake_graph_to_dataframe)
    result = await engine.estimate_effect("case-1", "X", "Y")
    assert result.is_significant is False


async def test_estimate_effect_too_few_observations(monkeypatch: pytest.MonkeyPatch):
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )

    async def _fake_graph_to_dataframe(
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> pd.DataFrame:
        return _make_causal_data(5)[entity_uids]

    monkeypatch.setattr(engine, "_graph_to_dataframe", _fake_graph_to_dataframe)
    result = await engine.estimate_effect("case-1", "X", "Y")
    assert result.warning is not None
    assert result.num_observations < settings.causal_min_observations
    assert result.is_significant is False


async def test_refutation_results(monkeypatch: pytest.MonkeyPatch):
    engine = CausalInferenceEngine(
        _FakeNeo4j(subgraph=_make_subgraph(), rows=_make_graph_rows())
    )

    async def _fake_graph_to_dataframe(
        case_uid: str,
        entity_uids: list[str],
        *,
        window: str = "1d",
    ) -> pd.DataFrame:
        frame = _make_causal_data()
        for uid in entity_uids:
            if uid not in frame.columns:
                frame[uid] = 0.0
        return frame[entity_uids]

    monkeypatch.setattr(engine, "_graph_to_dataframe", _fake_graph_to_dataframe)
    result = await engine.estimate_effect("case-1", "X", "Y")
    methods = {item.method for item in result.refutation_results}
    assert {"placebo_treatment", "random_common_cause", "data_subset"} <= methods
