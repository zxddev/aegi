"""CrewAI 协作输出契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CrewOrientSummary(BaseModel):
    """Orient 阶段协作摘要。"""

    summary: str = Field(min_length=1)
    conflicts: list[str] = Field(default_factory=list)


class CrewDecideSummary(BaseModel):
    """Decide 阶段协作摘要。"""

    hypotheses: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
