# Author: msq
"""Adversarial hypothesis evaluation – Defense/Prosecution/Judge triad.

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (2.2)
        openspec/changes/ach-hypothesis-analysis/design.md (Adversarial Reasoning Flow)
Evidence:
  - Defense Agent：构建支持链（支持证据优先按诊断性排序）
  - Prosecution Agent：构建反证链与漏洞清单
  - Judge Agent：输出平衡裁决（不确定项与证据缺口必须显式）
  - Defense/Prosecution/Judge 的分歧 MUST 被保留，不得被单结果覆盖 (spec.md)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from aegi_core.services.hypothesis_engine import ACHResult


@dataclass
class AgentVerdict:
    """单个 agent（Defense/Prosecution/Judge）的裁决。"""

    role: str
    assertion_uids: list[str] = field(default_factory=list)
    rationale: str = ""
    gaps: list[str] = field(default_factory=list)


@dataclass
class AdversarialResult:
    """三角对抗的完整输出。"""

    defense: AgentVerdict = field(default_factory=lambda: AgentVerdict(role="defense"))
    prosecution: AgentVerdict = field(
        default_factory=lambda: AgentVerdict(role="prosecution")
    )
    judge: AgentVerdict = field(default_factory=lambda: AgentVerdict(role="judge"))
    conflict_summary: str = ""
    grounding_level: GroundingLevel = GroundingLevel.HYPOTHESIS

    def to_dict(self) -> dict:
        return {
            "defense": {
                "role": self.defense.role,
                "assertion_uids": self.defense.assertion_uids,
                "rationale": self.defense.rationale,
                "gaps": self.defense.gaps,
            },
            "prosecution": {
                "role": self.prosecution.role,
                "assertion_uids": self.prosecution.assertion_uids,
                "rationale": self.prosecution.rationale,
                "gaps": self.prosecution.gaps,
            },
            "judge": {
                "role": self.judge.role,
                "assertion_uids": self.judge.assertion_uids,
                "rationale": self.judge.rationale,
                "gaps": self.judge.gaps,
            },
            "conflict_summary": self.conflict_summary,
            "grounding_level": self.grounding_level.value,
        }


def _build_defense(
    ach: ACHResult,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
) -> AgentVerdict:
    """Defense agent：构建支持链，按诊断性排序。"""
    supporting = ach.supporting_assertion_uids
    rationale_parts = []
    for uid in supporting:
        a = next((a for a in assertions if a.uid == uid), None)
        if a:
            rationale_parts.append(f"{uid}: confidence={a.confidence}")

    return AgentVerdict(
        role="defense",
        assertion_uids=supporting,
        rationale=f"Supporting evidence chain: {'; '.join(rationale_parts) or 'none'}",
        gaps=[g for g in ach.gap_list if "not evaluated" in g],
    )


def _build_prosecution(
    ach: ACHResult,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
) -> AgentVerdict:
    """Prosecution agent：构建反证链与漏洞清单。"""
    contradicting = ach.contradicting_assertion_uids
    rationale_parts = []
    for uid in contradicting:
        a = next((a for a in assertions if a.uid == uid), None)
        if a:
            rationale_parts.append(f"{uid}: contradicts hypothesis")

    gaps = list(ach.gap_list)
    if not contradicting and not gaps:
        gaps.append("no contradicting evidence found – potential confirmation bias")

    return AgentVerdict(
        role="prosecution",
        assertion_uids=contradicting,
        rationale=f"Counter-evidence chain: {'; '.join(rationale_parts) or 'none'}",
        gaps=gaps,
    )


def _build_judge(
    defense: AgentVerdict,
    prosecution: AgentVerdict,
    ach: ACHResult,
) -> AgentVerdict:
    """Judge agent：平衡裁决，冲突摘要与裁决依据。"""
    all_uids = list(set(defense.assertion_uids + prosecution.assertion_uids))
    all_gaps = list(set(defense.gaps + prosecution.gaps))

    has_conflict = bool(defense.assertion_uids and prosecution.assertion_uids)
    if has_conflict:
        rationale = (
            f"Conflict: defense cites {len(defense.assertion_uids)} supporting, "
            f"prosecution cites {len(prosecution.assertion_uids)} contradicting. "
            f"Confidence={ach.confidence:.2f}, coverage={ach.coverage_score:.2f}."
        )
    elif defense.assertion_uids:
        rationale = (
            f"No contradiction found. "
            f"Confidence={ach.confidence:.2f}, coverage={ach.coverage_score:.2f}."
        )
    else:
        rationale = (
            f"Insufficient evidence. "
            f"Confidence={ach.confidence:.2f}, coverage={ach.coverage_score:.2f}."
        )

    return AgentVerdict(
        role="judge",
        assertion_uids=all_uids,
        rationale=rationale,
        gaps=all_gaps,
    )


def evaluate_adversarial(
    ach: ACHResult,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
    *,
    case_uid: str,
    trace_id: str | None = None,
) -> tuple[AdversarialResult, ActionV1, ToolTraceV1]:
    """执行 Defense/Prosecution/Judge 三角对抗评估。

    Args:
        ach: 来自 hypothesis_engine 的 ACH 分析结果。
        assertions: 可用 assertion 列表。
        source_claims: 可用 source claim 列表。
        case_uid: 所属 case。
        trace_id: 分布式追踪 ID。

    Returns:
        Tuple of (adversarial_result, action, tool_trace).
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    defense = _build_defense(ach, assertions, source_claims)
    prosecution = _build_prosecution(ach, assertions, source_claims)
    judge = _build_judge(defense, prosecution, ach)

    has_conflict = bool(defense.assertion_uids and prosecution.assertion_uids)
    conflict_summary = ""
    if has_conflict:
        conflict_summary = (
            f"Defense supports with {len(defense.assertion_uids)} assertions; "
            f"Prosecution contradicts with {len(prosecution.assertion_uids)} assertions. "
            f"Judge ruling: {judge.rationale}"
        )

    has_evidence = bool(defense.assertion_uids)
    grounding = grounding_gate(has_evidence)

    result = AdversarialResult(
        defense=defense,
        prosecution=prosecution,
        judge=judge,
        conflict_summary=conflict_summary,
        grounding_level=grounding,
    )

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="ach_adversarial",
        rationale=(
            f"Adversarial evaluation: "
            f"defense={len(defense.assertion_uids)}, "
            f"prosecution={len(prosecution.assertion_uids)}, "
            f"gaps={len(judge.gaps)}"
        ),
        inputs={"hypothesis_text": ach.hypothesis_text},
        outputs=result.to_dict(),
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="ach_adversarial",
        request={"hypothesis_text": ach.hypothesis_text},
        response=result.to_dict(),
        status="ok",
        policy={"prompt_version": "ach_adversarial_v1"},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return result, action, tool_trace
