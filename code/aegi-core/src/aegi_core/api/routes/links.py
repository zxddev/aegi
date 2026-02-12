# Author: msq
"""Link prediction API endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from aegi_core.api.deps import get_link_predictor
from aegi_core.services.link_predictor import (
    InsufficientTriplesError,
    LinkPredictor,
    ModelNotTrainedError,
    PyKEENUnavailableError,
)

router = APIRouter(prefix="/cases/{case_uid}/links", tags=["link-prediction"])


class TrainRequest(BaseModel):
    model_name: str | None = None
    embedding_dim: int | None = Field(default=None, ge=1)
    num_epochs: int | None = Field(default=None, ge=1)


@router.post("/train")
async def train_link_predictor(
    case_uid: str,
    body: TrainRequest,
    predictor: LinkPredictor = Depends(get_link_predictor),
) -> dict:
    try:
        result = await predictor.train(
            case_uid,
            model_name=body.model_name,
            embedding_dim=body.embedding_dim,
            num_epochs=body.num_epochs,
        )
        return asdict(result)
    except PyKEENUnavailableError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except InsufficientTriplesError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/predictions")
async def predict_missing_links(
    case_uid: str,
    top_k: int = Query(20, ge=1, le=200),
    min_score: float = Query(0.5, ge=0.0, le=1.0),
    predictor: LinkPredictor = Depends(get_link_predictor),
) -> dict:
    try:
        predictions = await predictor.predict_missing_links(
            case_uid,
            top_k=top_k,
            min_score=min_score,
        )
        return {"predictions": [asdict(item) for item in predictions]}
    except PyKEENUnavailableError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/predictions/{entity_uid}")
async def predict_entity_links(
    case_uid: str,
    entity_uid: str,
    direction: str = Query("both", pattern="^(head|tail|both)$"),
    top_k: int = Query(10, ge=1, le=200),
    predictor: LinkPredictor = Depends(get_link_predictor),
) -> dict:
    try:
        predictions = await predictor.predict_for_entity(
            case_uid,
            entity_uid,
            direction=direction,
            top_k=top_k,
        )
        return {"predictions": [asdict(item) for item in predictions]}
    except PyKEENUnavailableError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/anomalies")
async def detect_anomalous_triples(
    case_uid: str,
    threshold: float = Query(0.1, ge=0.0, le=1.0),
    predictor: LinkPredictor = Depends(get_link_predictor),
) -> dict:
    try:
        anomalies = await predictor.detect_anomalous_triples(
            case_uid,
            threshold=threshold,
        )
        return {"anomalies": [asdict(item) for item in anomalies]}
    except PyKEENUnavailableError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ModelNotTrainedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
