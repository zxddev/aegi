"""审查结果契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    """审查结果。"""

    ok: bool
    insufficient_evidence: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
