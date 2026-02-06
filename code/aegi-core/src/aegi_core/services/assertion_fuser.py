# Author: msq
"""Assertion fusion service.

Source: openspec/changes/automated-claim-extraction-fusion/tasks.md (2.1–2.3)
Evidence:
  - Assertions MUST be derived from SourceClaims (spec.md).
  - Conflict set MUST be explicit and replayable (spec.md).
  - Fusion MUST output rationale and conflict reason (design.md).
  - Conflicts: value conflict + modality conflict; preserve, never overwrite (design.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.errors import validation_error
from aegi_core.contracts.schemas import AssertionV1, SourceClaimV1


class ConflictRecord:
    """Single conflict between two claims."""

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
    """Detect value conflict: same attributed_to but different quote content."""
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


def _detect_modality_conflict(a: SourceClaimV1, b: SourceClaimV1) -> ConflictRecord | None:
    """Detect modality conflict: e.g. confirmed vs denied on same subject."""
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


def fuse_claims(
    claims: list[SourceClaimV1],
    *,
    case_uid: str,
    trace_id: str | None = None,
) -> tuple[list[AssertionV1], list[dict], ActionV1, ToolTraceV1]:
    """Fuse source claims into assertions, detecting conflicts.

    Args:
        claims: Source claims to fuse.
        case_uid: Owning case.
        trace_id: Distributed trace id.

    Returns:
        Tuple of (assertions, conflict_set, action, tool_trace).
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    if not claims:
        err = validation_error("source_claim_uids must not be empty", field="source_claim_uids")
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
