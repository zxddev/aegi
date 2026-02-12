# Author: msq
"""偏见检测，用于元认知质量评分。

Source: openspec/changes/meta-cognition-quality-scoring/design.md
Evidence:
  - 单源依赖、单立场偏置、确认偏误信号。
  - 每个 bias flag MUST 关联 source_claim_uids 与判断依据。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aegi_core.contracts.schemas import AssertionV1, HypothesisV1, SourceClaimV1


class BiasFlag(BaseModel):
    kind: str
    description: str
    source_claim_uids: list[str] = Field(default_factory=list)
    rationale: str = ""


def _single_source_dependency(
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
) -> list[BiasFlag]:
    """每个 assertion 仅由单一来源支撑 → 单源依赖偏见。"""
    sc_map = {sc.uid: sc for sc in source_claims}
    flags: list[BiasFlag] = []
    for a in assertions:
        if len(a.source_claim_uids) == 1:
            sc_uid = a.source_claim_uids[0]
            sc = sc_map.get(sc_uid)
            attr = sc.attributed_to if sc else "unknown"
            flags.append(
                BiasFlag(
                    kind="single_source_dependency",
                    description=f"Assertion {a.uid} backed by single source ({attr})",
                    source_claim_uids=list(a.source_claim_uids),
                    rationale="Single source cannot be cross-verified",
                )
            )
    return flags


def _single_stance_bias(
    source_claims: list[SourceClaimV1],
) -> list[BiasFlag]:
    """所有 source_claims 来自同一 attributed_to → 单立场偏置。"""
    sources = {sc.attributed_to for sc in source_claims if sc.attributed_to}
    if len(sources) == 1 and len(source_claims) > 1:
        src = next(iter(sources))
        return [
            BiasFlag(
                kind="single_stance_bias",
                description=f"All {len(source_claims)} claims from single source: {src}",
                source_claim_uids=[sc.uid for sc in source_claims],
                rationale="Lack of independent corroboration",
            )
        ]
    return []


def _confirmation_bias(
    hypotheses: list[HypothesisV1],
    assertions: list[AssertionV1],
) -> list[BiasFlag]:
    """假设仅有支持证据、无反驳 → 确认偏误信号。"""
    if not hypotheses or not assertions:
        return []
    assertion_uid_set = {a.uid for a in assertions}
    flags: list[BiasFlag] = []
    for h in hypotheses:
        supporting = [
            uid for uid in h.supporting_assertion_uids if uid in assertion_uid_set
        ]
        if len(supporting) >= 2 and len(supporting) == len(h.supporting_assertion_uids):
            sc_uids: list[str] = []
            for a in assertions:
                if a.uid in supporting:
                    sc_uids.extend(a.source_claim_uids)
            flags.append(
                BiasFlag(
                    kind="confirmation_bias",
                    description=f"Hypothesis {h.uid} has only supporting evidence ({len(supporting)} assertions)",
                    source_claim_uids=sc_uids,
                    rationale="No contradicting evidence found; potential confirmation bias",
                )
            )
    return flags


def _source_diversity_bias(
    source_claims: list[SourceClaimV1],
) -> list[BiasFlag]:
    """来源多样性不足：所有 claims 来自同类型来源或同一地区。"""
    if len(source_claims) < 2:
        return []
    flags: list[BiasFlag] = []
    # 检测来源同质性（所有 attributed_to 含相同前缀/域名模式）
    sources = [sc.attributed_to or "" for sc in source_claims]
    non_empty = [s for s in sources if s]
    if len(non_empty) >= 2:
        # 简单启发：如果所有来源名称共享前 3 个字符（如 "CNN", "BBC"）
        # 更实用的检测：独立来源数 / 总 claims 数
        unique_sources = set(non_empty)
        diversity_ratio = len(unique_sources) / len(non_empty)
        if diversity_ratio < 0.3 and len(non_empty) >= 3:
            flags.append(
                BiasFlag(
                    kind="source_homogeneity",
                    description=(
                        f"Low source diversity: {len(unique_sources)} unique "
                        f"sources across {len(non_empty)} claims "
                        f"(ratio={diversity_ratio:.2f})"
                    ),
                    source_claim_uids=[sc.uid for sc in source_claims],
                    rationale="Insufficient independent corroboration",
                )
            )
    return flags


def detect_biases(
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
    hypotheses: list[HypothesisV1] | None = None,
) -> list[BiasFlag]:
    """运行所有偏见检测器。

    Args:
        assertions: 当前 judgment 的 assertions。
        source_claims: 关联的 source claims。
        hypotheses: 关联的 hypotheses（可选）。

    Returns:
        检测到的 BiasFlag 列表。
    """
    flags: list[BiasFlag] = []
    flags.extend(_single_source_dependency(assertions, source_claims))
    flags.extend(_single_stance_bias(source_claims))
    flags.extend(_source_diversity_bias(source_claims))
    if hypotheses:
        flags.extend(_confirmation_bias(hypotheses, assertions))
    return flags
