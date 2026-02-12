# Author: msq
"""因果推理器 — assertion 时序一致性检查与因果链评分。

Source: openspec/changes/predictive-causal-scenarios/tasks.md (2.1)
        openspec/changes/predictive-causal-scenarios/design.md
Evidence:
  - P1 基于 Assertion 时序字段 + Hypothesis 输出做一致性检查与预警评分
  - 不依赖图查询引擎即可生成最小情景分支
  - 无证据预测禁止输出 probability → grounding_gate(False) 降级
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field as PydanticField

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from typing import TYPE_CHECKING

from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, NarrativeV1

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# LLM 结构化输出的 Pydantic 模型
# ---------------------------------------------------------------------------


class _LLMCausalLinkItem(BaseModel):
    """LLM 输出的单条因果链接。"""

    source_uid: str = ""
    target_uid: str = ""
    counterfactual_score: float = 0.0
    confounders: list[str] = PydanticField(default_factory=list)


class _LLMCausalResponse(BaseModel):
    """LLM 因果分析的结构化输出模型。"""

    links: list[_LLMCausalLinkItem] = PydanticField(default_factory=list)
    consistency_score: float = 0.0


@dataclass
class CausalLink:
    """单条因果链接：从 source assertion 到 target assertion。"""

    source_uid: str
    target_uid: str
    strength: float = 0.0
    temporal_consistent: bool = True
    counterfactual_score: float = 0.0  # 反事实评分：移除该因果链后结论变化程度
    confounders: list[str] = field(default_factory=list)  # 混淆因素


@dataclass
class CausalAnalysis:
    """因果分析结果。"""

    hypothesis_uid: str
    causal_links: list[CausalLink] = field(default_factory=list)
    consistency_score: float = 0.0
    grounding_level: GroundingLevel = GroundingLevel.HYPOTHESIS
    narrative_available: bool = True


def _parse_created_at(raw: datetime | str) -> datetime:
    """安全解析 created_at，兼容 str 和 datetime。"""
    if isinstance(raw, str):
        return datetime.fromisoformat(raw)
    return raw


def analyze_causal_links(
    hypothesis: HypothesisV1,
    assertions: list[AssertionV1],
    narratives: list[NarrativeV1] | None = None,
) -> CausalAnalysis:
    """对假设的支持 assertion 做时序一致性检查，生成因果链接。

    Args:
        hypothesis: 待分析假设。
        assertions: 可用 assertion 列表。
        narratives: 可选叙事列表（soft dep，缺失时降级）。

    Returns:
        CausalAnalysis 包含因果链接与一致性评分。
    """
    narrative_available = narratives is not None and len(narratives) > 0

    # 筛选假设引用的 assertion，按时间排序
    uid_set = set(hypothesis.supporting_assertion_uids)
    relevant = sorted(
        [a for a in assertions if a.uid in uid_set],
        key=lambda a: _parse_created_at(a.created_at),
    )

    if not relevant:
        return CausalAnalysis(
            hypothesis_uid=hypothesis.uid,
            grounding_level=grounding_gate(False),
            narrative_available=narrative_available,
        )

    # 构建相邻时序对的因果链接
    links: list[CausalLink] = []
    consistent_count = 0
    for i in range(len(relevant) - 1):
        src, tgt = relevant[i], relevant[i + 1]
        t_src = _parse_created_at(src.created_at)
        t_tgt = _parse_created_at(tgt.created_at)
        temporal_ok = t_src <= t_tgt
        strength = ((src.confidence or 0.0) + (tgt.confidence or 0.0)) / 2.0
        links.append(
            CausalLink(
                source_uid=src.uid,
                target_uid=tgt.uid,
                strength=strength,
                temporal_consistent=temporal_ok,
            )
        )
        if temporal_ok:
            consistent_count += 1

    # 无因果对时（单 assertion）视为一致（无矛盾证据）
    if not links:
        consistency = 1.0
    else:
        consistency = consistent_count / len(links)

    has_evidence = len(relevant) > 0 and any(a.source_claim_uids for a in relevant)
    grounding = grounding_gate(has_evidence)

    return CausalAnalysis(
        hypothesis_uid=hypothesis.uid,
        causal_links=links,
        consistency_score=consistency,
        grounding_level=grounding,
        narrative_available=narrative_available,
    )


# ---------------------------------------------------------------------------
# LLM 驱动版本 — 反事实推理 + 混淆因素检测
# ---------------------------------------------------------------------------

_CAUSAL_PROMPT = """你是一位因果推理分析师。分析以下假设的因果链条。

假设：{hypothesis_text}

时序证据链（按时间排序）：
{evidence_chain}

请评估：
1. 每对相邻证据之间的因果关系强度
2. 反事实评分：如果移除该因果链，结论会如何变化（0=无影响，1=完全改变）
3. 可能的混淆因素

请严格以 JSON 格式输出（不要 markdown 代码块）：
{{"links": [{{"source_uid": "uid1", "target_uid": "uid2", "counterfactual_score": 0.5, "confounders": ["因素1"]}}], "consistency_score": 0.8}}
"""


async def aanalyze_causal_links(
    hypothesis: HypothesisV1,
    assertions: list[AssertionV1],
    narratives: list[NarrativeV1] | None = None,
    *,
    llm: "LLMClient | None" = None,
) -> CausalAnalysis:
    """LLM 驱动的因果分析。无 LLM 时 fallback 到规则版本。"""
    # 先跑规则版本作为 baseline / fallback
    baseline = analyze_causal_links(hypothesis, assertions, narratives)

    if llm is None or not baseline.causal_links:
        return baseline

    # 构建证据链描述
    uid_set = set(hypothesis.supporting_assertion_uids)
    relevant = sorted(
        [a for a in assertions if a.uid in uid_set],
        key=lambda a: _parse_created_at(a.created_at),
    )
    chain_lines = []
    for i, a in enumerate(relevant):
        t = _parse_created_at(a.created_at).isoformat()
        chain_lines.append(f"{i + 1}. [{a.uid}] {t} conf={a.confidence}")

    prompt = _CAUSAL_PROMPT.format(
        hypothesis_text=hypothesis.label or hypothesis.uid,
        evidence_chain="\n".join(chain_lines) or "无",
    )

    try:
        llm_causal = await llm.invoke_structured(
            prompt,
            response_model=_LLMCausalResponse,
            max_tokens=1024,
        )

        # 用 LLM 结果增强 baseline 的 causal_links
        llm_links = {
            (lk.source_uid, lk.target_uid): lk
            for lk in llm_causal.links
            if lk.source_uid and lk.target_uid
        }
        for link in baseline.causal_links:
            key = (link.source_uid, link.target_uid)
            if key in llm_links:
                ll = llm_links[key]
                link.counterfactual_score = ll.counterfactual_score
                link.confounders = ll.confounders
        if llm_causal.consistency_score:
            baseline.consistency_score = llm_causal.consistency_score
    except Exception:  # noqa: BLE001 — LLM 失败保留规则结果
        import logging

        logging.getLogger(__name__).warning(
            "LLM 因果分析失败，保留规则版本结果",
            exc_info=True,
            extra={"degraded": True, "component": "causal_reasoner"},
        )

    return baseline
