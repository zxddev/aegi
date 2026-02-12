# Author: msq
"""对抗性假设评估 — Defense/Prosecution/Judge 三角辩论。

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

from pydantic import BaseModel, Field as PydanticField

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.llm_governance import GroundingLevel, grounding_gate
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1
from typing import TYPE_CHECKING

from aegi_core.services.hypothesis_engine import ACHResult

if TYPE_CHECKING:
    from aegi_core.infra.llm_client import LLMClient


# ---------------------------------------------------------------------------
# LLM 结构化输出的 Pydantic 模型（按角色）
# ---------------------------------------------------------------------------


class _LLMRoleVerdict(BaseModel):
    """单个对抗角色的 LLM 输出模型。"""

    argument: str = ""
    evidence_refs: list[str] = PydanticField(default_factory=list)
    confidence: float = 0.5


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


# ---------------------------------------------------------------------------
# LLM 驱动版本 — 三角色辩论（defense / prosecution / judge）
# ---------------------------------------------------------------------------

_ROLE_PROMPT_TMPL = """你是一位{role_desc}。
分析以下假设及其证据，从你的角色视角给出论证。

假设：{hypothesis_text}
置信度：{confidence:.2f}
覆盖度：{coverage:.2f}

支持证据 UIDs：{supporting}
反对证据 UIDs：{contradicting}
证据缺口：{gaps}

{evidence_context}

请严格以 JSON 格式输出（不要 markdown 代码块）：
{{"argument": "你的论证", "evidence_refs": ["引用的证据UID"], "confidence": 0.0到1.0}}
"""

_PROSECUTION_EXTRA = """重要指令：你必须主动从证据中寻找可以反驳假设的论点。即使没有直接标记为"反对"的证据，你也应该：
1. 检查支持证据中是否存在可被重新解读为不支持假设的内容
2. 指出证据链中的逻辑跳跃和未验证假设
3. 提出替代解释（如果证据同样支持其他假设）
绝对不要说"无反证"——总有可以质疑的角度。"""

_ROLE_DESCS = {
    "defense": "辩护律师，负责构建支持假设的最强论证链",
    "prosecution": "检察官，负责寻找假设的漏洞和反证",
    "judge": "法官，综合控辩双方意见做出平衡裁决",
}


def _parse_role_json(text: str) -> dict | None:
    """从 LLM 输出中提取 JSON。（旧版 — 仅保留做参考。）"""
    from aegi_core.infra.llm_client import parse_llm_json

    result = parse_llm_json(text)
    return result if isinstance(result, dict) else None


def _verdict_from_model(role: str, data: _LLMRoleVerdict) -> AgentVerdict:
    """将 LLM Pydantic 输出转为 AgentVerdict。"""
    return AgentVerdict(
        role=role,
        assertion_uids=data.evidence_refs,
        rationale=data.argument,
        gaps=[],
    )


def _json_to_verdict(role: str, data: dict) -> AgentVerdict:
    """将 LLM JSON 输出转为 AgentVerdict。"""
    return AgentVerdict(
        role=role,
        assertion_uids=data.get("evidence_refs", []),
        rationale=data.get("argument", ""),
        gaps=[],
    )


async def aevaluate_adversarial(
    ach: ACHResult,
    assertions: list[AssertionV1],
    source_claims: list[SourceClaimV1],
    *,
    case_uid: str,
    trace_id: str | None = None,
    llm: "LLMClient | None" = None,
) -> tuple[AdversarialResult, ActionV1, ToolTraceV1]:
    """LLM 驱动的三角对抗评估。无 LLM 时 fallback 到规则版本。"""
    if llm is None:
        return evaluate_adversarial(
            ach,
            assertions,
            source_claims,
            case_uid=case_uid,
            trace_id=trace_id,
        )

    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    # 构建证据摘要供 LLM 参考
    _evidence_lines = []
    for sc in source_claims[:15]:
        _evidence_lines.append(f"- [{sc.attributed_to or 'unknown'}] {sc.quote[:150]}")
    _evidence_text = "\n".join(_evidence_lines) if _evidence_lines else "无"

    prompt_ctx = {
        "hypothesis_text": ach.hypothesis_text,
        "confidence": ach.confidence,
        "coverage": ach.coverage_score,
        "supporting": ", ".join(ach.supporting_assertion_uids) or "无",
        "contradicting": ", ".join(ach.contradicting_assertion_uids) or "无",
        "gaps": "; ".join(ach.gap_list) or "无",
    }

    # 三角色各一次 LLM 调用，失败时 fallback 到规则版本
    defense = _build_defense(ach, assertions, source_claims)
    prosecution = _build_prosecution(ach, assertions, source_claims)

    for role, fallback in [("defense", defense), ("prosecution", prosecution)]:
        try:
            extra = _PROSECUTION_EXTRA if role == "prosecution" else ""
            prompt = _ROLE_PROMPT_TMPL.format(
                role_desc=_ROLE_DESCS[role],
                evidence_context=f"原始情报摘要：\n{_evidence_text}\n\n{extra}",
                **prompt_ctx,
            )
            verdict_model = await llm.invoke_structured(
                prompt,
                response_model=_LLMRoleVerdict,
                max_tokens=512,
            )
            verdict = _verdict_from_model(role, verdict_model)
            if role == "defense":
                defense = verdict
            else:
                prosecution = verdict
        except Exception:  # noqa: BLE001 — LLM 失败时保留规则结果
            pass

    # judge 综合控辩结果
    judge = _build_judge(defense, prosecution, ach)
    try:
        judge_prompt = _ROLE_PROMPT_TMPL.format(
            role_desc=(
                f"{_ROLE_DESCS['judge']}\n\n"
                f"辩护方论证：{defense.rationale}\n"
                f"检察方论证：{prosecution.rationale}"
            ),
            evidence_context=f"原始情报摘要：\n{_evidence_text}",
            **prompt_ctx,
        )
        judge_model = await llm.invoke_structured(
            judge_prompt,
            response_model=_LLMRoleVerdict,
            max_tokens=512,
        )
        judge = _verdict_from_model("judge", judge_model)
        judge.gaps = list(set(defense.gaps + prosecution.gaps))
    except Exception:  # noqa: BLE001
        pass

    has_conflict = bool(defense.assertion_uids and prosecution.assertion_uids)
    conflict_summary = ""
    if has_conflict:
        conflict_summary = (
            f"Defense: {defense.rationale[:100]}; "
            f"Prosecution: {prosecution.rationale[:100]}; "
            f"Judge: {judge.rationale[:100]}"
        )

    has_evidence = bool(defense.assertion_uids)
    grounding = grounding_gate(has_evidence)

    adv_result = AdversarialResult(
        defense=defense,
        prosecution=prosecution,
        judge=judge,
        conflict_summary=conflict_summary,
        grounding_level=grounding,
    )

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="ach_adversarial_llm",
        rationale=(
            f"LLM adversarial: defense={len(defense.assertion_uids)}, "
            f"prosecution={len(prosecution.assertion_uids)}"
        ),
        inputs={"hypothesis_text": ach.hypothesis_text},
        outputs=adv_result.to_dict(),
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="ach_adversarial_llm",
        request={"hypothesis_text": ach.hypothesis_text},
        response=adv_result.to_dict(),
        status="ok",
        policy={"prompt_version": "ach_adversarial_llm_v1"},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )

    return adv_result, action, tool_trace
