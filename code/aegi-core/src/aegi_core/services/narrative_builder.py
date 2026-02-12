# Author: msq
"""叙事构建器 — 聚类 + 来源溯源。

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence:
  - 聚类：语义相似度 + 时间窗口约束。
  - 溯源：最早 created_at = 源头节点。
  - 冲突叙事必须共存 (spec.md)。

升级记录:
  - v0.2: 相似度计算从 SequenceMatcher 升级为 embedding cosine similarity，
    通过 embeddings 参数注入预计算向量；未提供时 fallback 到 token-overlap。
    参考: ADR-001 P1 设计参考 baize-core + storm。
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher

from aegi_core.contracts.schemas import AssertionV1, NarrativeV1, SourceClaimV1


def _token_similarity(a: str, b: str) -> float:
    """Token-overlap 相似度（fallback）。"""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# 保持向后兼容的别名
_similarity = _token_similarity


def build_narratives(
    claims: list[SourceClaimV1],
    *,
    assertions: list[AssertionV1] | None = None,
    time_window_hours: float = 168.0,
    similarity_threshold: float = 0.35,
    embeddings: dict[str, list[float]] | None = None,
) -> list[NarrativeV1]:
    """把 source claims 聚类成叙事。

    委托给 build_narratives_with_uids，丢弃 uid_map。
    """
    narratives, _ = build_narratives_with_uids(
        claims,
        assertions=assertions,
        time_window_hours=time_window_hours,
        similarity_threshold=similarity_threshold,
        embeddings=embeddings,
    )
    return narratives


def trace_narrative(
    narrative_uid: str,
    narratives: list[NarrativeV1],
    claims: list[SourceClaimV1],
    source_claim_uids_map: dict[str, list[str]],
) -> list[dict]:
    """返回叙事的时间排序传播链。

    Args:
        narrative_uid: 要溯源的叙事 UID。
        narratives: 所有已构建的叙事。
        claims: 所有 source claims。
        source_claim_uids_map: narrative_uid -> source_claim_uids 的映射。

    Returns:
        按时间排序的 dict 列表，含 uid, quote, attributed_to, created_at。
    """
    sc_uids = source_claim_uids_map.get(narrative_uid, [])
    claim_map = {c.uid: c for c in claims}
    chain = []
    for uid in sc_uids:
        c = claim_map.get(uid)
        if c:
            chain.append(
                {
                    "uid": c.uid,
                    "quote": c.quote,
                    "attributed_to": c.attributed_to,
                    "created_at": c.created_at.isoformat(),
                }
            )
    chain.sort(key=lambda x: x["created_at"])
    return chain


def build_narratives_with_uids(
    claims: list[SourceClaimV1],
    *,
    assertions: list[AssertionV1] | None = None,
    time_window_hours: float = 168.0,
    similarity_threshold: float = 0.35,
    embeddings: dict[str, list[float]] | None = None,
) -> tuple[list[NarrativeV1], dict[str, list[str]]]:
    """构建叙事并返回 (narratives, {narrative_uid: [source_claim_uids]})。

    Args:
        claims: 待聚类的 source claims。
        assertions: 可选的 assertion 列表，用于反向索引。
        time_window_hours: 时间窗口（小时），超出则不聚类。
        similarity_threshold: 相似度阈值。
        embeddings: 可选的预计算 embedding 字典 {claim_uid: vector}。
            提供时使用 cosine similarity，否则 fallback 到 token-overlap。
    """
    if not claims:
        return [], {}

    # 选择相似度函数：有 embedding 则用 cosine，否则 token-overlap
    use_embeddings = embeddings is not None
    # cosine similarity 数值普遍高于 token-overlap，需要更高阈值
    effective_threshold = (
        max(similarity_threshold, 0.6) if use_embeddings else similarity_threshold
    )

    def _sim(claim_a: SourceClaimV1, claim_b: SourceClaimV1) -> float:
        if use_embeddings:
            vec_a = embeddings.get(claim_a.uid)  # type: ignore[union-attr]
            vec_b = embeddings.get(claim_b.uid)  # type: ignore[union-attr]
            if vec_a and vec_b:
                return _cosine_similarity(vec_a, vec_b)
        # fallback 到 token-overlap
        return _token_similarity(claim_a.quote, claim_b.quote)

    # source_claim_uid → assertion_uid 反向索引
    sc_to_assertions: dict[str, list[str]] = {}
    for a in assertions or []:
        for sc_uid in a.source_claim_uids:
            sc_to_assertions.setdefault(sc_uid, []).append(a.uid)

    sorted_claims = sorted(claims, key=lambda c: c.created_at)
    clusters: list[list[SourceClaimV1]] = []

    for claim in sorted_claims:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            time_diff = abs(
                (claim.created_at - representative.created_at).total_seconds()
            )
            if time_diff > time_window_hours * 3600:
                continue
            if _sim(claim, representative) >= effective_threshold:
                cluster.append(claim)
                placed = True
                break
        if not placed:
            clusters.append([claim])

    now = datetime.now(timezone.utc)
    narratives: list[NarrativeV1] = []
    uid_map: dict[str, list[str]] = {}
    for cluster in clusters:
        sc_uids = [c.uid for c in cluster]
        nar_uid = f"nar-{uuid.uuid4().hex[:12]}"
        # 通过 source_claim → assertion 反向索引解析关联 assertion
        linked: list[str] = []
        for sc_uid in sc_uids:
            linked.extend(sc_to_assertions.get(sc_uid, []))
        narratives.append(
            NarrativeV1(
                uid=nar_uid,
                case_uid=cluster[0].case_uid,
                title=cluster[0].quote[:120],
                assertion_uids=list(dict.fromkeys(linked)),
                hypothesis_uids=[],
                created_at=now,
            )
        )
        uid_map[nar_uid] = sc_uids
    return narratives, uid_map


async def abuild_narratives_with_uids(
    claims: list[SourceClaimV1],
    *,
    embed_fn: object = None,
    assertions: list[AssertionV1] | None = None,
    time_window_hours: float = 168.0,
    similarity_threshold: float = 0.35,
) -> tuple[list[NarrativeV1], dict[str, list[str]]]:
    """Async 版本：自动调用 embed_fn 获取 embedding 后委托给同步版本。

    Args:
        embed_fn: async callable(text: str) -> list[float]，
            通常传 LLMClient.embed。为 None 时 fallback 到 token-overlap。
    """
    embeddings: dict[str, list[float]] | None = None
    if embed_fn is not None and claims:
        import asyncio

        # 批量获取所有 claim 的 embedding
        tasks = [embed_fn(c.quote) for c in claims]  # type: ignore[operator]
        vectors = await asyncio.gather(*tasks)
        embeddings = {c.uid: v for c, v in zip(claims, vectors)}

    return build_narratives_with_uids(
        claims,
        assertions=assertions,
        time_window_hours=time_window_hours,
        similarity_threshold=similarity_threshold,
        embeddings=embeddings,
    )
