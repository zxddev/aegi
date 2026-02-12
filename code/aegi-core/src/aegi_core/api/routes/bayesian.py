"""贝叶斯 ACH API 路由 — 6 个概率管理端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_llm_client
from aegi_core.api.errors import AegiHTTPError
from aegi_core.infra.llm_client import LLMClient
from aegi_core.services.bayesian_ach import BayesianACH

router = APIRouter(
    prefix="/cases/{case_uid}/hypotheses",
    tags=["bayesian-ach"],
)


# ── 请求 / 响应 schema ────────────────────────────────────


class InitializePriorsRequest(BaseModel):
    priors: dict[str, float] | None = None


class InitializePriorsResponse(BaseModel):
    priors: dict[str, float]


class BayesianUpdateRequest(BaseModel):
    evidence_uid: str
    evidence_text: str
    evidence_type: str = "assertion"


class BayesianUpdateResponse(BaseModel):
    evidence_uid: str
    prior_distribution: dict[str, float]
    posterior_distribution: dict[str, float]
    likelihoods: dict[str, float]
    diagnosticity: dict[str, float]
    max_change: float
    most_affected_hypothesis_uid: str


class OverrideRequest(BaseModel):
    relation: str
    strength: float


class RecalculateResponse(BaseModel):
    posteriors: dict[str, float]
    evidence_count: int


# ── 端点 ─────────────────────────────────────────────────────


@router.get("/probabilities")
async def get_probabilities(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    engine = BayesianACH(session)
    state = await engine.get_state(case_uid)
    return {
        "case_uid": state.case_uid,
        "hypotheses": state.hypotheses,
        "total_evidence_assessed": state.total_evidence_count,
        "last_updated": state.last_updated.isoformat() if state.last_updated else None,
    }


@router.post("/initialize-priors")
async def initialize_priors(
    case_uid: str,
    body: InitializePriorsRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> InitializePriorsResponse:
    if body and body.priors:
        total = sum(body.priors.values())
        if abs(total - 1.0) > 0.01:
            raise AegiHTTPError(
                status_code=422,
                error_code="invalid_priors",
                message=f"Priors must sum to 1.0, got {total:.4f}",
                details={"sum": total},
            )

    engine = BayesianACH(session)
    priors = body.priors if body else None
    result = await engine.initialize_priors(case_uid, priors=priors)
    await session.commit()
    return InitializePriorsResponse(priors=result)


@router.post("/bayesian-update")
async def bayesian_update(
    case_uid: str,
    body: BayesianUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    llm_client: LLMClient = Depends(get_llm_client),
) -> BayesianUpdateResponse:
    engine = BayesianACH(session, llm_client)
    await engine.assess_evidence(
        case_uid=case_uid,
        evidence_uid=body.evidence_uid,
        evidence_text=body.evidence_text,
        evidence_type=body.evidence_type,
    )
    result = await engine.update(case_uid, body.evidence_uid)
    await session.commit()
    return BayesianUpdateResponse(
        evidence_uid=result.evidence_uid,
        prior_distribution=result.prior_distribution,
        posterior_distribution=result.posterior_distribution,
        likelihoods=result.likelihoods,
        diagnosticity=result.diagnosticity,
        max_change=result.max_change,
        most_affected_hypothesis_uid=result.most_affected_hypothesis_uid,
    )


override_router = APIRouter(
    prefix="/cases/{case_uid}/evidence-assessments",
    tags=["bayesian-ach"],
)


@override_router.put("/{assessment_uid}")
async def override_assessment(
    case_uid: str,
    assessment_uid: str,
    body: OverrideRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    engine = BayesianACH(session)
    ea = await engine.override_assessment(assessment_uid, body.relation, body.strength)
    if ea is None:
        raise AegiHTTPError(
            status_code=404,
            error_code="not_found",
            message=f"EvidenceAssessment {assessment_uid} not found",
            details={},
        )
    await session.commit()
    return {
        "uid": ea.uid,
        "hypothesis_uid": ea.hypothesis_uid,
        "evidence_uid": ea.evidence_uid,
        "relation": ea.relation,
        "strength": ea.strength,
        "likelihood": ea.likelihood,
        "assessed_by": ea.assessed_by,
    }


@router.post("/recalculate")
async def recalculate(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> RecalculateResponse:
    engine = BayesianACH(session)
    posteriors = await engine.recalculate(case_uid)
    import sqlalchemy as sa
    from aegi_core.db.models.evidence_assessment import EvidenceAssessment

    ev_count = (
        await session.execute(
            sa.select(
                sa.func.count(sa.distinct(EvidenceAssessment.evidence_uid))
            ).where(EvidenceAssessment.case_uid == case_uid)
        )
    ).scalar_one()
    await session.commit()
    return RecalculateResponse(posteriors=posteriors, evidence_count=ev_count)


@router.get("/diagnosticity")
async def diagnosticity_ranking(
    case_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    engine = BayesianACH(session)
    rankings = await engine.get_diagnosticity_ranking(case_uid)
    return {"rankings": rankings}
