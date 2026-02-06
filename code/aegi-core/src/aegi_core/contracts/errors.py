# Author: msq
"""Unified error model with Problem Details (RFC 9457) (Gate-0).

Source: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
Evidence: Shared contract outputs MUST be file-addressable.
"""

from __future__ import annotations


from pydantic import BaseModel, Field


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details envelope."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    error_code: str
    extensions: dict = Field(default_factory=dict)


# -- Factory helpers -----------------------------------------------------------


def not_found(resource: str, uid: str) -> ProblemDetail:
    return ProblemDetail(
        type="urn:aegi:error:not_found",
        title=f"{resource} not found",
        status=404,
        detail=f"{resource} with uid={uid} does not exist",
        error_code="not_found",
        extensions={"resource": resource, "uid": uid},
    )


def validation_error(detail: str, *, field: str = "") -> ProblemDetail:
    return ProblemDetail(
        type="urn:aegi:error:validation",
        title="Validation error",
        status=422,
        detail=detail,
        error_code="validation_error",
        extensions={"field": field} if field else {},
    )


def budget_exceeded(model_id: str, budget_remaining: float) -> ProblemDetail:
    return ProblemDetail(
        type="urn:aegi:error:budget_exceeded",
        title="LLM budget exceeded",
        status=429,
        detail=f"Budget exhausted for model {model_id}",
        error_code="budget_exceeded",
        extensions={"model_id": model_id, "budget_remaining": budget_remaining},
    )


def model_unavailable(model_id: str, reason: str) -> ProblemDetail:
    return ProblemDetail(
        type="urn:aegi:error:model_unavailable",
        title="Model unavailable",
        status=503,
        detail=reason,
        error_code="model_unavailable",
        extensions={"model_id": model_id},
    )
