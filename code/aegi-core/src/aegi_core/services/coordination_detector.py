# Author: msq
"""协调传播检测 — 时间爆发 + 相似度分析。

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - 短时间内高相似度批量传播 = 疑似协调行为。
  - 输出必须包含 false_positive_explanation (spec.md)。

升级记录:
  - v0.2: 相似度支持 embedding cosine similarity，通过 embeddings 参数注入；
    未提供时 fallback 到 token-overlap。
"""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from aegi_core.contracts.schemas import SourceClaimV1


class CoordinationSignalV1(BaseModel):
    """协调传播检测输出（本地定义，不在共享合同中）。"""

    group_id: str
    narrative_uid: str
    source_claim_uids: list[str] = Field(default_factory=list)
    similarity_score: float
    time_burst_score: float
    confidence: float
    false_positive_explanation: str


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _token_similarity(a: str, b: str) -> float:
    """Token 重叠相似度（兜底方案）。"""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def _pairwise_similarity(
    claims: list[SourceClaimV1],
    embeddings: dict[str, list[float]] | None = None,
) -> float:
    """平均两两相似度。有 embedding 用 cosine，否则 token-overlap。"""
    if len(claims) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            if embeddings:
                va = embeddings.get(claims[i].uid)
                vb = embeddings.get(claims[j].uid)
                if va and vb:
                    total += _cosine_similarity(va, vb)
                    count += 1
                    continue
            # fallback
            total += _token_similarity(claims[i].quote, claims[j].quote)
            count += 1
    return total / count if count else 0.0


def _time_burst_score(claims: list[SourceClaimV1], burst_window_hours: float) -> float:
    """在 burst 窗口内的 claims 占比。"""
    if len(claims) < 2:
        return 0.0
    sorted_c = sorted(claims, key=lambda c: c.created_at)
    earliest = sorted_c[0].created_at
    window = timedelta(hours=burst_window_hours)
    in_window = sum(1 for c in sorted_c if (c.created_at - earliest) <= window)
    return in_window / len(claims)


def detect_coordination(
    source_claim_uids_map: dict[str, list[str]],
    claims: list[SourceClaimV1],
    *,
    burst_window_hours: float = 1.0,
    similarity_threshold: float = 0.5,
    min_cluster_size: int = 3,
    confidence_threshold: float = 0.6,
    embeddings: dict[str, list[float]] | None = None,
) -> list[CoordinationSignalV1]:
    """检测叙事聚类中的协调传播模式。

    Args:
        source_claim_uids_map: narrative_uid -> source_claim_uids 映射。
        claims: 所有 source claims。
        burst_window_hours: 爆发检测的时间窗口。
        similarity_threshold: 标记协调行为的最低平均相似度。
        min_cluster_size: 纳入考虑的最小聚类大小。
        confidence_threshold: 低于此值标记为 low_confidence。
        embeddings: 可选预计算 embedding {claim_uid: vector}。

    Returns:
        CoordinationSignalV1 信号列表。
    """
    claim_map = {c.uid: c for c in claims}
    signals: list[CoordinationSignalV1] = []

    for nar_uid, sc_uids in source_claim_uids_map.items():
        cluster_claims = [claim_map[uid] for uid in sc_uids if uid in claim_map]
        if len(cluster_claims) < min_cluster_size:
            continue

        sim = _pairwise_similarity(cluster_claims, embeddings)
        burst = _time_burst_score(cluster_claims, burst_window_hours)
        confidence = (sim + burst) / 2.0

        if sim < similarity_threshold:
            continue

        if confidence < confidence_threshold:
            explanation = (
                f"low_confidence: similarity={sim:.2f}, burst={burst:.2f}; "
                "natural propagation cannot be ruled out"
            )
        else:
            explanation = (
                f"high similarity ({sim:.2f}) with time burst ({burst:.2f}) "
                "suggests coordinated dissemination"
            )

        signals.append(
            CoordinationSignalV1(
                group_id=f"coord-{uuid.uuid4().hex[:8]}",
                narrative_uid=nar_uid,
                source_claim_uids=sc_uids,
                similarity_score=round(sim, 4),
                time_burst_score=round(burst, 4),
                confidence=round(confidence, 4),
                false_positive_explanation=explanation,
            )
        )

    return signals
