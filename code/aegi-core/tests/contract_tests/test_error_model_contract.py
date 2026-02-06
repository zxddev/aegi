# Author: msq
"""Contract tests for unified error model (task 5.2).

Evidence: openspec/changes/foundation-common-contracts/specs/foundation-common/spec.md
  - Shared contract outputs MUST be file-addressable.
Evidence: openspec/changes/foundation-common-contracts/specs/llm-governance/spec.md
  - Budget and failure paths MUST be deterministic.
"""

from aegi_core.contracts.errors import (
    ProblemDetail,
    budget_exceeded,
    model_unavailable,
    not_found,
    validation_error,
)


def test_problem_detail_has_rfc9457_fields():
    pd = ProblemDetail(
        title="test",
        status=400,
        error_code="test_code",
    )
    assert pd.type == "about:blank"
    assert pd.title == "test"
    assert pd.status == 400
    assert pd.error_code == "test_code"


def test_not_found_factory():
    pd = not_found("Case", "c-1")
    assert pd.status == 404
    assert pd.error_code == "not_found"
    assert pd.extensions["uid"] == "c-1"


def test_validation_error_factory():
    pd = validation_error("bad input", field="name")
    assert pd.status == 422
    assert pd.error_code == "validation_error"


def test_budget_exceeded_factory():
    pd = budget_exceeded("gpt-4", 0.0)
    assert pd.status == 429
    assert pd.error_code == "budget_exceeded"
    assert pd.extensions["model_id"] == "gpt-4"


def test_model_unavailable_factory():
    pd = model_unavailable("gpt-4", "timeout")
    assert pd.status == 503
    assert pd.error_code == "model_unavailable"


def test_problem_detail_roundtrip():
    pd = not_found("Artifact", "a-1")
    data = pd.model_dump()
    pd2 = ProblemDetail.model_validate(data)
    assert pd2 == pd
