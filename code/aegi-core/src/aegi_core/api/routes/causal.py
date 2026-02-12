# Author: msq
"""Causal inference API endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aegi_core.api.deps import get_causal_inference_engine
from aegi_core.services.causal_inference import (
    CausalInferenceEngine,
    DoWhyUnavailableError,
)

router = APIRouter(prefix="/cases/{case_uid}/causal", tags=["causal-inference"])


class EstimateRequest(BaseModel):
    treatment_entity_uid: str
    outcome_entity_uid: str
    method: str = "backdoor.linear_regression"
    time_window: str | None = None


class BuildGraphRequest(BaseModel):
    treatment_entity_uid: str
    outcome_entity_uid: str


@router.post("/estimate")
async def estimate_causal_effect(
    case_uid: str,
    body: EstimateRequest,
    engine: CausalInferenceEngine = Depends(get_causal_inference_engine),
) -> dict:
    try:
        result = await engine.estimate_effect(
            case_uid,
            body.treatment_entity_uid,
            body.outcome_entity_uid,
            method=body.method,
            time_window=body.time_window,
        )
        return asdict(result)
    except DoWhyUnavailableError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/graph")
async def build_causal_graph(
    case_uid: str,
    body: BuildGraphRequest,
    engine: CausalInferenceEngine = Depends(get_causal_inference_engine),
) -> dict:
    try:
        result = await engine.build_causal_graph(
            case_uid,
            body.treatment_entity_uid,
            body.outcome_entity_uid,
        )
        return asdict(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
