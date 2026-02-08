# Author: msq
"""Causal reasoner – assertion temporal consistency and causal link scoring.

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

from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, NarrativeV1


@dataclass
class CausalLink:
    """单条因果链接：从 source assertion 到 target assertion。"""

    source_uid: str
    target_uid: str
    strength: float = 0.0
    temporal_consistent: bool = True


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
