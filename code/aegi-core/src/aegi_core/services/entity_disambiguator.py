# Author: msq
"""实体消歧服务 — 识别知识图谱中指向同一现实实体的不同节点。

策略：规则归一化候选 + embedding 语义相似度评分。
原则：低置信度（< UNCERTAINTY_THRESHOLD）标记为 uncertain，不自动合并。
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.services.entity import EntityV1

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient

UNCERTAINTY_THRESHOLD = 0.7
SIMILARITY_THRESHOLD = 0.82

# 已知别名表（可扩展）
_KNOWN_ALIASES: dict[str, str] = {
    "prc": "china",
    "people's republic of china": "china",
    "中华人民共和国": "china",
    "中国": "china",
    "dprk": "north korea",
    "rok": "south korea",
    "usa": "united states",
    "us": "united states",
    "美国": "united states",
    "俄罗斯": "russia",
    "rf": "russia",
    "russian federation": "russia",
    "eu": "european union",
    "nato": "north atlantic treaty organization",
    "un": "united nations",
    "联合国": "united nations",
}


class MergeGroup(BaseModel):
    """一组指向同一现实实体的 KG 节点。"""

    canonical_uid: str
    canonical_label: str
    alias_uids: list[str] = Field(default_factory=list)
    alias_labels: list[str] = Field(default_factory=list)
    confidence: float
    uncertain: bool = False
    explanation: str = ""


class DisambiguationResult(BaseModel):
    """消歧结果。"""

    merge_groups: list[MergeGroup] = Field(default_factory=list)
    unmatched_uids: list[str] = Field(default_factory=list)
    action: ActionV1
    tool_trace: ToolTraceV1


def _normalize_label(text: str) -> str:
    """归一化实体标签：小写、去标点、Unicode NFKC、去多余空格。"""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _alias_canonical(label: str) -> str | None:
    """查已知别名表，返回规范名；未命中返回 None。"""
    return _KNOWN_ALIASES.get(_normalize_label(label))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def disambiguate_entities(
    entities: list[EntityV1],
    *,
    case_uid: str,
    llm: LLMClient | None = None,
    trace_id: str | None = None,
) -> DisambiguationResult:
    """对实体列表执行消歧，返回 merge 建议组。

    步骤：
    1. 规则层：归一化 label + 已知别名表，精确匹配归组
    2. 语义层（需要 llm）：对未归组实体计算 embedding 相似度，高于阈值归组
    3. 低置信度标记 uncertain
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    # ── 第一步：规则归组 ──────────────────────────────────────────
    # key = 规范名, value = 该组实体列表
    rule_groups: dict[str, list[EntityV1]] = {}
    unresolved: list[EntityV1] = []

    for ent in entities:
        canonical = _alias_canonical(ent.label)
        if canonical is None:
            canonical = _normalize_label(ent.label)
        rule_groups.setdefault(canonical, []).append(ent)

    # 规则层产出的 merge groups（组内 >= 2 个实体才算 merge）
    merge_groups: list[MergeGroup] = []
    for _key, group in rule_groups.items():
        if len(group) >= 2:
            primary = group[0]
            merge_groups.append(
                MergeGroup(
                    canonical_uid=primary.uid,
                    canonical_label=primary.label,
                    alias_uids=[e.uid for e in group[1:]],
                    alias_labels=[e.label for e in group[1:]],
                    confidence=0.95,
                    uncertain=False,
                    explanation="规则归一化匹配（别名表或 label 归一化相同）",
                )
            )
        else:
            unresolved.append(group[0])

    # ── 第二步：语义层（embedding 相似度）────────────────────────
    if llm is not None and len(unresolved) >= 2:
        # 批量 embed 所有未归组实体的 label
        embeddings: dict[str, list[float]] = {}
        for ent in unresolved:
            try:
                vec = await llm.embed(ent.label)
                embeddings[ent.uid] = vec
            except Exception:  # noqa: BLE001
                pass  # embedding 失败则跳过该实体

        # 两两比较，贪心归组
        matched_uids: set[str] = set()
        for i, e1 in enumerate(unresolved):
            if e1.uid in matched_uids or e1.uid not in embeddings:
                continue
            group_members: list[EntityV1] = []
            for e2 in unresolved[i + 1 :]:
                if e2.uid in matched_uids or e2.uid not in embeddings:
                    continue
                sim = _cosine_similarity(embeddings[e1.uid], embeddings[e2.uid])
                if sim >= SIMILARITY_THRESHOLD:
                    group_members.append(e2)
                    matched_uids.add(e2.uid)
            if group_members:
                matched_uids.add(e1.uid)
                avg_sim = sum(
                    _cosine_similarity(embeddings[e1.uid], embeddings[m.uid])
                    for m in group_members
                ) / len(group_members)
                merge_groups.append(
                    MergeGroup(
                        canonical_uid=e1.uid,
                        canonical_label=e1.label,
                        alias_uids=[m.uid for m in group_members],
                        alias_labels=[m.label for m in group_members],
                        confidence=round(avg_sim, 3),
                        uncertain=avg_sim < UNCERTAINTY_THRESHOLD,
                        explanation=f"embedding 语义相似度 {avg_sim:.3f}",
                    )
                )

        unresolved = [e for e in unresolved if e.uid not in matched_uids]

    # ── 审计 ──────────────────────────────────────────────────────
    merged_count = sum(len(g.alias_uids) for g in merge_groups)
    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="kg_disambiguate",
        rationale=(
            f"消歧完成：{len(merge_groups)} 组合并，"
            f"涉及 {merged_count + len(merge_groups)} 个实体，"
            f"{len(unresolved)} 个未匹配"
        ),
        inputs={"entity_uids": [e.uid for e in entities]},
        outputs={
            "merge_group_count": len(merge_groups),
            "merged_entity_count": merged_count,
            "unmatched_count": len(unresolved),
        },
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="entity_disambiguator",
        request={"entity_count": len(entities)},
        response={"merge_group_count": len(merge_groups)},
        status="ok",
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return DisambiguationResult(
        merge_groups=merge_groups,
        unmatched_uids=[e.uid for e in unresolved],
        action=action,
        tool_trace=tool_trace,
    )
