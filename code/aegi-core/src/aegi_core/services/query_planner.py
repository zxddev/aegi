# Author: msq
"""查询规划：NL -> QueryPlanV1，含风险标记。

Source: openspec/changes/conversational-analysis-evidence-qa/design.md
Evidence:
  - 中间产物 QueryPlanV1（filters, retrieval_steps, risk_flags）
  - 风险标记：证据不足/时间范围冲突/来源不足
"""

from __future__ import annotations

from enum import Enum

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


class RiskFlag(str, Enum):
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    TIME_RANGE_CONFLICT = "time_range_conflict"
    SOURCES_INSUFFICIENT = "sources_insufficient"


class RetrievalStep(BaseModel):
    table: str
    filters: dict = Field(default_factory=dict)
    description: str = ""


class _LLMQueryPlanResponse(BaseModel):
    """LLM 查询规划的 Pydantic 模型（structured output）。"""

    retrieval_steps: list[RetrievalStep] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class QueryPlanV1(BaseModel):
    question: str
    case_uid: str
    filters: dict = Field(default_factory=dict)
    retrieval_steps: list[RetrievalStep] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    time_range: dict | None = None
    language: str | None = None


_KG_KEYWORDS = {
    "关系",
    "路径",
    "连接",
    "网络",
    "核心",
    "社区",
    "图谱",
    "实体",
    "relationship",
    "path",
    "connected",
    "network",
    "central",
    "community",
    "graph",
    "entity",
    "link",
}


def _is_kg_query(question: str) -> bool:
    return bool(set(question.lower().split()) & _KG_KEYWORDS)


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

    if _is_kg_query(question):
        steps.append(
            RetrievalStep(
                table="kg_graph",
                filters={"case_uid": case_uid},
                description="检索知识图谱中的实体关系和路径",
            )
        )

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


# ---------------------------------------------------------------------------
# LLM 驱动版本 — 智能查询规划
# ---------------------------------------------------------------------------

_QUERY_PLAN_PROMPT = """你是 OSINT 情报检索规划师。根据用户问题生成多步检索计划。

用户问题：{question}
案例 ID：{case_uid}
时间范围：{time_range}
语言：{language}

可用数据表及用途：
- source_claims: 原始情报引用（按来源、时间、关键词过滤）
- assertions: 融合后的断言（按 kind、confidence、attributed_to 过滤）
- hypotheses: 竞争性假设（按 confidence 排序）
- evidence: 证据链（按 evidence_uid 关联）
- narratives: 叙事聚类（按主题检索）
- kg_graph: 知识图谱查询（按实体关系、路径、社区过滤）

要求（必须严格遵守）：
1. 分析问题涉及的实体、时间、地点、事件类型
2. 必须生成恰好 4-6 个检索步骤，不能少于 4 个
3. 步骤必须从宽到窄：
   - 第 1-2 步：从 source_claims 检索直接相关的原始情报（按关键词、来源类型分别检索）
   - 第 3 步：从 assertions 检索融合后的高置信度断言进行交叉验证
   - 第 4 步：从 hypotheses 检索竞争性假设评估争议点
   - 第 5-6 步（可选）：从 narratives 获取宏观叙事上下文，或按时间线排序的 source_claims
4. 每步的 description 必须说明该步骤的具体目的和预期收获
5. filters 必须包含具体的过滤条件（关键词、来源类型、时间范围等），不能为空

请严格以 JSON 格式输出（不要 markdown 代码块，不要任何解释文字）：
{{"retrieval_steps": [{{"table": "表名", "filters": {{"key": "value"}}, "description": "步骤描述"}}], "risk_flags": ["flag"]}}

risk_flags 可选值：evidence_insufficient, time_range_conflict, sources_insufficient
"""


async def aplan_query(
    question: str,
    case_uid: str,
    *,
    time_range: dict | None = None,
    language: str | None = None,
    llm: "LLMClient | None" = None,
) -> QueryPlanV1:
    """LLM 驱动的查询规划。无 LLM 时 fallback 到规则版本。"""
    baseline = plan_query(question, case_uid, time_range=time_range, language=language)

    if llm is None:
        return baseline

    prompt = _QUERY_PLAN_PROMPT.format(
        question=question,
        case_uid=case_uid,
        time_range=time_range or "无",
        language=language or "auto",
    )

    try:
        llm_plan = await llm.invoke_structured(
            prompt,
            response_model=_LLMQueryPlanResponse,
            max_tokens=1024,
            max_retries=2,
        )

        steps = llm_plan.retrieval_steps
        flags: list[RiskFlag] = []
        for rf in llm_plan.risk_flags:
            try:
                flags.append(RiskFlag(rf))
            except ValueError:
                pass
        # 保留 baseline 的时间范围冲突检测
        flags.extend(baseline.risk_flags)
        flags = list(set(flags))

        return QueryPlanV1(
            question=question,
            case_uid=case_uid,
            filters={"case_uid": case_uid},
            retrieval_steps=steps,
            risk_flags=flags,
            time_range=time_range,
            language=language,
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning(
            "LLM 查询规划失败，回退到规则版本",
            exc_info=True,
            extra={"degraded": True, "component": "query_planner"},
        )

    return baseline
