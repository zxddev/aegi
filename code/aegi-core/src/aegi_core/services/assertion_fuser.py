# Author: msq
"""断言融合服务。

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (2.1–2.3)
Evidence:
  - Assertions 必须从 SourceClaims 派生 (spec.md)。
  - 冲突集必须显式且可重放 (spec.md)。
  - 融合必须输出 rationale 和冲突原因 (design.md)。
  - 冲突类型：值冲突 + 模态冲突；保留不覆盖 (design.md)。
"""

from __future__ import annotations

import re

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.errors import validation_error
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


class ConflictRecord:
    """两条 claim 之间的单个冲突记录。"""

    def __init__(
        self,
        conflict_type: str,
        claim_uid_a: str,
        claim_uid_b: str,
        rationale: str,
    ) -> None:
        self.conflict_type = conflict_type
        self.claim_uid_a = claim_uid_a
        self.claim_uid_b = claim_uid_b
        self.rationale = rationale

    def to_dict(self) -> dict:
        return {
            "conflict_type": self.conflict_type,
            "claim_uid_a": self.claim_uid_a,
            "claim_uid_b": self.claim_uid_b,
            "rationale": self.rationale,
        }


def _detect_value_conflict(a: SourceClaimV1, b: SourceClaimV1) -> ConflictRecord | None:
    """检测值冲突：同一 attributed_to 但引用内容不同。"""
    if (
        a.attributed_to
        and b.attributed_to
        and a.attributed_to == b.attributed_to
        and a.quote != b.quote
    ):
        return ConflictRecord(
            conflict_type="value_conflict",
            claim_uid_a=a.uid,
            claim_uid_b=b.uid,
            rationale=(f"Same subject '{a.attributed_to}' with contradicting quotes"),
        )
    return None


def _detect_modality_conflict(
    a: SourceClaimV1, b: SourceClaimV1
) -> ConflictRecord | None:
    """检测模态冲突：同一主体上 confirmed vs denied。"""
    if not (a.attributed_to and b.attributed_to and a.attributed_to == b.attributed_to):
        return None
    quote_a = a.quote.lower()
    quote_b = b.quote.lower()
    confirmed_keywords = {"confirmed", "affirmed", "verified", "acknowledged"}
    denied_keywords = {"denied", "rejected", "refuted", "disputed"}
    a_confirmed = any(k in quote_a for k in confirmed_keywords)
    a_denied = any(k in quote_a for k in denied_keywords)
    b_confirmed = any(k in quote_b for k in confirmed_keywords)
    b_denied = any(k in quote_b for k in denied_keywords)
    if (a_confirmed and b_denied) or (a_denied and b_confirmed):
        return ConflictRecord(
            conflict_type="modality_conflict",
            claim_uid_a=a.uid,
            claim_uid_b=b.uid,
            rationale=f"Modality conflict on subject '{a.attributed_to}': confirmed vs denied",
        )
    return None


# 时间表达提取模式（年月日）
_TIME_PATTERN = re.compile(
    r"(?:(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},?\s*\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})",
    re.IGNORECASE,
)

# 常见地名关键词（可扩展）
_LOCATION_KEYWORDS = {
    "beijing",
    "moscow",
    "washington",
    "london",
    "paris",
    "tokyo",
    "berlin",
    "kyiv",
    "taipei",
    "seoul",
    "tehran",
    "jerusalem",
    "cairo",
    "delhi",
    "shanghai",
    "guangzhou",
    "shenzhen",
    "hong kong",
    "singapore",
    "new york",
    "los angeles",
    "chicago",
}


def _detect_temporal_conflict(
    a: SourceClaimV1, b: SourceClaimV1
) -> ConflictRecord | None:
    """检测时间冲突：同一主体的 claims 中包含不同时间表达。"""
    if not (a.attributed_to and b.attributed_to and a.attributed_to == b.attributed_to):
        return None
    times_a = set(_TIME_PATTERN.findall(a.quote.lower()))
    times_b = set(_TIME_PATTERN.findall(b.quote.lower()))
    if times_a and times_b and times_a.isdisjoint(times_b):
        return ConflictRecord(
            conflict_type="temporal_conflict",
            claim_uid_a=a.uid,
            claim_uid_b=b.uid,
            rationale=(
                f"Temporal conflict on '{a.attributed_to}': {times_a} vs {times_b}"
            ),
        )
    return None


def _detect_geographic_conflict(
    a: SourceClaimV1, b: SourceClaimV1
) -> ConflictRecord | None:
    """检测地理冲突：同一主体同时出现在不同地点。"""
    if not (a.attributed_to and b.attributed_to and a.attributed_to == b.attributed_to):
        return None
    locs_a = {k for k in _LOCATION_KEYWORDS if k in a.quote.lower()}
    locs_b = {k for k in _LOCATION_KEYWORDS if k in b.quote.lower()}
    if locs_a and locs_b and locs_a.isdisjoint(locs_b):
        # 检查时间是否重叠（created_at 在 24h 内视为同时）
        time_diff = abs((a.created_at - b.created_at).total_seconds())
        if time_diff < 86400:
            return ConflictRecord(
                conflict_type="geographic_conflict",
                claim_uid_a=a.uid,
                claim_uid_b=b.uid,
                rationale=(
                    f"Geographic conflict on '{a.attributed_to}': "
                    f"{locs_a} vs {locs_b} within 24h"
                ),
            )
    return None


def fuse_claims(
    claims: list[SourceClaimV1],
    *,
    case_uid: str,
    trace_id: str | None = None,
) -> tuple[list[AssertionV1], list[dict], ActionV1, ToolTraceV1]:
    """将 source claims 融合为 assertions，同时检测冲突。

    Args:
        claims: 待融合的 source claims。
        case_uid: 所属 case。
        trace_id: 分布式追踪 ID。

    Returns:
        (assertions, conflict_set, action, tool_trace) 元组。
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    if not claims:
        err = validation_error(
            "source_claim_uids must not be empty", field="source_claim_uids"
        )
        action = ActionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_type="assertion_fuse",
            rationale="Rejected: empty claims input",
            inputs={"source_claim_uids": []},
            outputs={"error": err.model_dump()},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_uid=action.uid,
            tool_name="assertion_fuse",
            request={"source_claim_uids": []},
            response={"error": err.model_dump()},
            status="rejected",
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        return [], [], action, tool_trace

    # 冲突检测 (task 2.2)
    conflict_set: list[dict] = []
    conflicting_uids: set[str] = set()
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            vc = _detect_value_conflict(a, b)
            if vc:
                conflict_set.append(vc.to_dict())
                conflicting_uids.update({a.uid, b.uid})
            mc = _detect_modality_conflict(a, b)
            if mc:
                conflict_set.append(mc.to_dict())
                conflicting_uids.update({a.uid, b.uid})
            tc = _detect_temporal_conflict(a, b)
            if tc:
                conflict_set.append(tc.to_dict())
                conflicting_uids.update({a.uid, b.uid})
            gc = _detect_geographic_conflict(a, b)
            if gc:
                conflict_set.append(gc.to_dict())
                conflicting_uids.update({a.uid, b.uid})

    # 按 attributed_to 分组生成 assertions
    groups: dict[str, list[SourceClaimV1]] = {}
    for c in claims:
        key = c.attributed_to or "_unattributed_"
        groups.setdefault(key, []).append(c)

    assertions: list[AssertionV1] = []
    for key, group in groups.items():
        group_uids = [c.uid for c in group]
        has_conflict = any(uid in conflicting_uids for uid in group_uids)
        rationale_parts = [f"Fused from {len(group)} claim(s)"]
        if has_conflict:
            rationale_parts.append("contains conflicts – preserved, not overwritten")

        assertion = AssertionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            kind="fused_claim",
            value={
                "attributed_to": key if key != "_unattributed_" else None,
                "rationale": "; ".join(rationale_parts),
                "has_conflict": has_conflict,
            },
            source_claim_uids=group_uids,
            confidence=0.5 if has_conflict else 0.9,
            modality=group[0].modality,
            created_at=now,
        )
        assertions.append(assertion)

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="assertion_fuse",
        rationale=f"Fused {len(claims)} claims into {len(assertions)} assertions, {len(conflict_set)} conflicts",
        inputs={"source_claim_uids": [c.uid for c in claims]},
        outputs={
            "assertion_uids": [a.uid for a in assertions],
            "conflict_count": len(conflict_set),
        },
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="assertion_fuse",
        request={"source_claim_uids": [c.uid for c in claims]},
        response={
            "assertion_count": len(assertions),
            "conflict_count": len(conflict_set),
        },
        status="ok",
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return assertions, conflict_set, action, tool_trace


# ---------------------------------------------------------------------------
# LLM 驱动版本 — 语义立场冲突检测（跨来源）
# ---------------------------------------------------------------------------

_SEMANTIC_CONFLICT_PROMPT = """你是 OSINT 情报分析师。判断以下两条来自不同来源的情报是否存在立场矛盾。

情报 A（来源: {source_a}）：
{quote_a}

情报 B（来源: {source_b}）：
{quote_b}

判断标准：
- 两条情报对同一事件/事实的描述是否存在实质性矛盾（如一方确认、另一方否认或淡化）
- 仅主题相关但不矛盾的不算冲突
- 补充性信息不算冲突

请严格以 JSON 格式输出（不要 markdown 代码块）：
{{"conflict": true或false, "rationale": "简要说明矛盾点或为何不矛盾"}}
"""


def _parse_conflict_json(text: str) -> dict | None:
    """从 LLM 输出中提取冲突判断 JSON。"""
    from aegi_core.infra.llm_client import parse_llm_json

    result = parse_llm_json(text)
    return result if isinstance(result, dict) else None


async def adetect_semantic_conflicts(
    claims: list[SourceClaimV1],
    *,
    llm: "LLMClient | None" = None,
) -> list[dict]:
    """LLM 语义冲突检测：识别不同来源间的立场矛盾。

    无 LLM 时返回空列表（规则引擎已在 fuse_claims 中处理）。
    """
    if llm is None or len(claims) < 2:
        return []

    conflicts: list[dict] = []
    # 只检测不同来源间的 claim 对（同来源已由规则引擎处理）
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            if (
                a.attributed_to
                and b.attributed_to
                and a.attributed_to == b.attributed_to
            ):
                continue  # 同来源，跳过
            try:
                prompt = _SEMANTIC_CONFLICT_PROMPT.format(
                    source_a=a.attributed_to or "unknown",
                    quote_a=a.quote[:300],
                    source_b=b.attributed_to or "unknown",
                    quote_b=b.quote[:300],
                )
                result = await llm.invoke(prompt, max_tokens=256)
                parsed = _parse_conflict_json(result["text"])
                if parsed and parsed.get("conflict") is True:
                    conflicts.append(
                        ConflictRecord(
                            conflict_type="semantic_stance_conflict",
                            claim_uid_a=a.uid,
                            claim_uid_b=b.uid,
                            rationale=parsed.get(
                                "rationale", "LLM detected stance conflict"
                            ),
                        ).to_dict()
                    )
            except Exception:  # noqa: BLE001 — LLM 失败时静默跳过
                pass

    return conflicts
