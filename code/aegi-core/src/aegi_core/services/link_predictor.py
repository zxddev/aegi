# Author: msq
"""PyKEEN knowledge-graph link prediction service."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import logging
import math
from typing import Any

import anyio
import numpy as np

from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services.event_bus import AegiEvent, get_event_bus
from aegi_core.settings import settings

logger = logging.getLogger(__name__)


class LinkPredictorError(RuntimeError):
    """Base error for link prediction service."""


class PyKEENUnavailableError(LinkPredictorError):
    """PyKEEN is not installed."""


class ModelNotTrainedError(LinkPredictorError):
    """Model has not been trained for this case."""


class InsufficientTriplesError(LinkPredictorError):
    """Not enough triples to train a model."""

    def __init__(self, *, actual: int, minimum: int) -> None:
        super().__init__(
            f"Not enough triples for training: got {actual}, need at least {minimum}."
        )
        self.actual = actual
        self.minimum = minimum


@dataclass(frozen=True)
class TrainResult:
    model_name: str
    num_triples: int
    num_entities: int
    num_relations: int
    mrr: float
    hits_at_1: float
    hits_at_10: float
    training_time_seconds: float


@dataclass(frozen=True)
class PredictedLink:
    head_uid: str
    head_name: str
    relation: str
    tail_uid: str
    tail_name: str
    score: float
    confidence: str


@dataclass(frozen=True)
class AnomalousTriple:
    head_uid: str
    relation: str
    tail_uid: str
    score: float
    existing: bool
    reason: str


@dataclass
class _CachedModel:
    pipeline_result: Any
    existing_triples: set[tuple[str, str, str]]


def _ensure_pykeen() -> None:
    try:
        import pykeen  # noqa: F401
    except ImportError as exc:
        raise PyKEENUnavailableError(
            "PyKEEN not installed. Run: pip install 'aegi-core[analytics]'"
        ) from exc


def _normalize_score(raw_score: float) -> float:
    # Numerically stable sigmoid normalization to [0, 1]
    if raw_score >= 0:
        z = math.exp(-raw_score)
        return 1.0 / (1.0 + z)
    z = math.exp(raw_score)
    return z / (1.0 + z)


def _confidence_bucket(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


class LinkPredictor:
    """PyKEEN-based knowledge graph link prediction engine."""

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j
        self._models: dict[str, _CachedModel] = {}

    async def _run_blocking(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))

    @staticmethod
    def _metric_or_zero(metric_results: Any, key: str) -> float:
        try:
            return float(metric_results.get_metric(key))
        except Exception:
            try:
                return float(metric_results.to_flat_dict().get(key, 0.0))
            except Exception:
                return 0.0

    def _require_model(self, case_uid: str) -> _CachedModel:
        model = self._models.get(case_uid)
        if model is None:
            raise ModelNotTrainedError(
                "No trained model for this case. Call /links/train first."
            )
        return model

    @staticmethod
    def _train_sync(
        triples: list[tuple[str, str, str]],
        *,
        model_name: str,
        embedding_dim: int,
        num_epochs: int,
    ) -> Any:
        _ensure_pykeen()
        from pykeen.pipeline import pipeline
        from pykeen.triples import TriplesFactory

        triples_array = np.asarray(triples, dtype=str)
        tf = TriplesFactory.from_labeled_triples(triples_array)
        training, testing = tf.split([0.8, 0.2], random_state=42)

        kwargs: dict[str, Any] = {
            "training": training,
            "testing": testing,
            "model": model_name,
            "training_kwargs": {"num_epochs": num_epochs},
            "random_seed": 42,
        }
        if embedding_dim > 0:
            kwargs["model_kwargs"] = {"embedding_dim": embedding_dim}
        try:
            return pipeline(**kwargs)
        except TypeError:
            kwargs.pop("model_kwargs", None)
            return pipeline(**kwargs)

    @staticmethod
    def _predict_missing_links_sync(
        cached: _CachedModel,
        *,
        top_k: int,
    ) -> list[tuple[str, str, str, float]]:
        _ensure_pykeen()
        from pykeen.predict import predict_all

        model = cached.pipeline_result.model
        tf = cached.pipeline_result.training
        num_entities = len(tf.entity_to_id)
        top_candidates = max(top_k * 50, 1000)
        if num_entities > 500:
            logger.warning(
                "Large KG detected (%s entities). Restricting prediction candidates.",
                num_entities,
            )
            top_candidates = max(top_candidates, 3000)

        df = predict_all(model=model, k=top_candidates).process(factory=tf).df
        records = sorted(
            df.to_dict(orient="records"),
            key=lambda row: float(row["score"]),
            reverse=True,
        )

        predicted: list[tuple[str, str, str, float]] = []
        for row in records:
            head = str(row.get("head_label") or row.get("head_id") or "")
            relation = str(row.get("relation_label") or row.get("relation_id") or "")
            tail = str(row.get("tail_label") or row.get("tail_id") or "")
            if not head or not relation or not tail:
                continue
            triple = (head, relation, tail)
            if triple in cached.existing_triples:
                continue
            predicted.append((head, relation, tail, float(row["score"])))
            if len(predicted) >= top_k * 20:
                break
        return predicted

    @staticmethod
    def _predict_for_entity_sync(
        cached: _CachedModel,
        *,
        entity_uid: str,
        direction: str,
        top_k: int,
    ) -> list[tuple[str, str, str, float]]:
        _ensure_pykeen()
        from pykeen.predict import predict_target

        tf = cached.pipeline_result.training
        model = cached.pipeline_result.model

        if entity_uid not in tf.entity_to_id:
            return []

        relation_labels = sorted(tf.relation_to_id.keys())
        per_relation_limit = max(top_k, 10)
        rows: list[tuple[str, str, str, float]] = []

        if direction in {"head", "both"}:
            for relation in relation_labels:
                result = predict_target(
                    model=model,
                    head=entity_uid,
                    relation=relation,
                    triples_factory=tf,
                )
                for record in result.df.head(per_relation_limit).to_dict(
                    orient="records"
                ):
                    tail = str(record.get("tail_label") or record.get("tail_id") or "")
                    if not tail:
                        continue
                    triple = (entity_uid, relation, tail)
                    if triple in cached.existing_triples:
                        continue
                    rows.append((entity_uid, relation, tail, float(record["score"])))

        if direction in {"tail", "both"}:
            for relation in relation_labels:
                result = predict_target(
                    model=model,
                    relation=relation,
                    tail=entity_uid,
                    triples_factory=tf,
                )
                for record in result.df.head(per_relation_limit).to_dict(
                    orient="records"
                ):
                    head = str(record.get("head_label") or record.get("head_id") or "")
                    if not head:
                        continue
                    triple = (head, relation, entity_uid)
                    if triple in cached.existing_triples:
                        continue
                    rows.append((head, relation, entity_uid, float(record["score"])))

        best_by_triple: dict[tuple[str, str, str], float] = {}
        for head, relation, tail, score in rows:
            triple = (head, relation, tail)
            best_by_triple[triple] = max(
                best_by_triple.get(triple, float("-inf")),
                score,
            )

        sorted_rows = sorted(
            ((*triple, score) for triple, score in best_by_triple.items()),
            key=lambda item: item[3],
            reverse=True,
        )
        return sorted_rows[: top_k * 10]

    @staticmethod
    def _score_existing_triples_sync(
        cached: _CachedModel,
    ) -> list[tuple[str, str, str, float]]:
        _ensure_pykeen()
        from pykeen.predict import predict_triples

        triples = sorted(cached.existing_triples)
        if not triples:
            return []

        tf = cached.pipeline_result.training
        model = cached.pipeline_result.model
        df = predict_triples(
            model=model,
            triples=triples,
            triples_factory=tf,
        ).process(factory=tf).df
        records = sorted(
            df.to_dict(orient="records"),
            key=lambda row: float(row["score"]),
        )

        scored: list[tuple[str, str, str, float]] = []
        for row in records:
            head = str(row.get("head_label") or row.get("head_id") or "")
            relation = str(row.get("relation_label") or row.get("relation_id") or "")
            tail = str(row.get("tail_label") or row.get("tail_id") or "")
            if not head or not relation or not tail:
                continue
            scored.append((head, relation, tail, float(row["score"])))
        return scored

    async def train(
        self,
        case_uid: str,
        *,
        model_name: str | None = None,
        embedding_dim: int | None = None,
        num_epochs: int | None = None,
    ) -> TrainResult:
        _ensure_pykeen()

        triples = sorted(set(await self._neo4j.get_all_triples(case_uid)))
        minimum = settings.pykeen_min_triples
        if len(triples) < minimum:
            raise InsufficientTriplesError(actual=len(triples), minimum=minimum)

        final_model = model_name or settings.pykeen_default_model
        final_dim = embedding_dim or settings.pykeen_embedding_dim
        final_epochs = num_epochs or settings.pykeen_num_epochs

        start = anyio.current_time()
        pipeline_result = await self._run_blocking(
            self._train_sync,
            triples,
            model_name=final_model,
            embedding_dim=final_dim,
            num_epochs=final_epochs,
        )
        elapsed = anyio.current_time() - start

        metrics = pipeline_result.metric_results
        train_result = TrainResult(
            model_name=final_model,
            num_triples=len(triples),
            num_entities=int(pipeline_result.training.num_entities),
            num_relations=int(pipeline_result.training.num_relations),
            mrr=self._metric_or_zero(
                metrics,
                "both.realistic.inverse_harmonic_mean_rank",
            ),
            hits_at_1=self._metric_or_zero(metrics, "both.realistic.hits_at_1"),
            hits_at_10=self._metric_or_zero(metrics, "both.realistic.hits_at_10"),
            training_time_seconds=round(float(elapsed), 3),
        )

        self._models[case_uid] = _CachedModel(
            pipeline_result=pipeline_result,
            existing_triples=set(triples),
        )

        try:
            top_predictions = await self.predict_missing_links(
                case_uid,
                top_k=5,
                min_score=0.8,
            )
            if top_predictions:
                bus = get_event_bus()
                await bus.emit(
                    AegiEvent(
                        event_type="link.predicted",
                        case_uid=case_uid,
                        payload={
                            "summary": f"发现 {len(top_predictions)} 条高置信度潜在关联",
                            "predictions": [
                                {
                                    "head": p.head_name,
                                    "relation": p.relation,
                                    "tail": p.tail_name,
                                    "score": p.score,
                                }
                                for p in top_predictions
                            ],
                        },
                        severity="medium",
                        source_event_uid=f"pykeen:{case_uid}:train",
                    )
                )
        except Exception:
            logger.exception(
                "Failed to emit link.predicted event for case %s",
                case_uid,
            )

        return train_result

    async def predict_missing_links(
        self,
        case_uid: str,
        *,
        top_k: int = 20,
        min_score: float = 0.5,
    ) -> list[PredictedLink]:
        _ensure_pykeen()
        cached = self._require_model(case_uid)
        entity_names = await self._neo4j.get_entity_names(case_uid)
        raw_predictions = await self._run_blocking(
            self._predict_missing_links_sync,
            cached,
            top_k=top_k,
        )

        predictions: list[PredictedLink] = []
        for head, relation, tail, raw_score in raw_predictions:
            score = _normalize_score(raw_score)
            if score < min_score:
                continue
            predictions.append(
                PredictedLink(
                    head_uid=head,
                    head_name=entity_names.get(head, head),
                    relation=relation,
                    tail_uid=tail,
                    tail_name=entity_names.get(tail, tail),
                    score=round(score, 6),
                    confidence=_confidence_bucket(score),
                )
            )
            if len(predictions) >= top_k:
                break
        return predictions

    async def predict_for_entity(
        self,
        case_uid: str,
        entity_uid: str,
        *,
        direction: str = "both",
        top_k: int = 10,
    ) -> list[PredictedLink]:
        _ensure_pykeen()
        if direction not in {"head", "tail", "both"}:
            raise ValueError("direction must be one of: head, tail, both")

        cached = self._require_model(case_uid)
        entity_names = await self._neo4j.get_entity_names(case_uid)
        raw_predictions = await self._run_blocking(
            self._predict_for_entity_sync,
            cached,
            entity_uid=entity_uid,
            direction=direction,
            top_k=top_k,
        )

        predictions: list[PredictedLink] = []
        for head, relation, tail, raw_score in raw_predictions[:top_k]:
            score = _normalize_score(raw_score)
            predictions.append(
                PredictedLink(
                    head_uid=head,
                    head_name=entity_names.get(head, head),
                    relation=relation,
                    tail_uid=tail,
                    tail_name=entity_names.get(tail, tail),
                    score=round(score, 6),
                    confidence=_confidence_bucket(score),
                )
            )
        return predictions

    async def detect_anomalous_triples(
        self,
        case_uid: str,
        *,
        threshold: float = 0.1,
    ) -> list[AnomalousTriple]:
        _ensure_pykeen()
        cached = self._require_model(case_uid)
        scored_triples = await self._run_blocking(
            self._score_existing_triples_sync,
            cached,
        )

        anomalies: list[AnomalousTriple] = []
        for head, relation, tail, raw_score in scored_triples:
            score = _normalize_score(raw_score)
            if score >= threshold:
                continue
            anomalies.append(
                AnomalousTriple(
                    head_uid=head,
                    relation=relation,
                    tail_uid=tail,
                    score=round(score, 6),
                    existing=True,
                    reason="不符合图结构模式",
                )
            )

        anomalies.sort(key=lambda item: item.score)
        return anomalies
