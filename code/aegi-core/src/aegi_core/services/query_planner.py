# Author: msq
"""查询规划：NL -> QueryPlanV1，含风险标记。

Source: openspec/changes/conversational-analysis-evidence-qa/design.md
Evidence:
  - 中间产物 QueryPlanV1（filters, retrieval_steps, risk_flags）
  - 风险标记：证据不足/时间范围冲突/来源不足
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskFlag(str, Enum):
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    TIME_RANGE_CONFLICT = "time_range_conflict"
    SOURCES_INSUFFICIENT = "sources_insufficient"


class RetrievalStep(BaseModel):
    table: str
    filters: dict = Field(default_factory=dict)
    description: str = ""


class QueryPlanV1(BaseModel):
    question: str
    case_uid: str
    filters: dict = Field(default_factory=dict)
    retrieval_steps: list[RetrievalStep] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    time_range: dict | None = None
    language: str | None = None


def plan_query(
    question: str,
    case_uid: str,
    *,
    time_range: dict | None = None,
    language: str | None = None,
) -> QueryPlanV1:
    """将自然语言问题转换为 QueryPlanV1。

    P1 阶段使用基于规则的简单规划：对 source_claims 和 assertions 做全文检索。
    """
    filters: dict = {"case_uid": case_uid}
    if time_range:
        filters["time_range"] = time_range

    steps = [
        RetrievalStep(
            table="source_claims",
            filters=filters,
            description="检索案例关联的 source claims",
        ),
        RetrievalStep(
            table="assertions",
            filters={"case_uid": case_uid},
            description="检索案例关联的 assertions",
        ),
    ]

    risk_flags: list[RiskFlag] = []
    if time_range:
        start = time_range.get("start")
        end = time_range.get("end")
        if start and end and start > end:
            risk_flags.append(RiskFlag.TIME_RANGE_CONFLICT)

    return QueryPlanV1(
        question=question,
        case_uid=case_uid,
        filters=filters,
        retrieval_steps=steps,
        risk_flags=risk_flags,
        time_range=time_range,
        language=language,
    )
