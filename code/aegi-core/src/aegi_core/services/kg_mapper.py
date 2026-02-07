# Author: msq
"""KG mapper service – Assertion -> Graph mapping.

Source: openspec/changes/knowledge-graph-ontology-evolution/tasks.md (2.2)
Evidence:
  - KG 映射必须消费已冻结的 Assertion schema (design.md).
  - KG 构建可回放到 Assertion 与 SourceClaim (spec.md acceptance #1).
  - Schema mismatch blocks graph build (spec.md scenario).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from dataclasses import dataclass, field

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.errors import ProblemDetail
from aegi_core.contracts.schemas import AssertionV1
from aegi_core.services.entity import EntityV1
from aegi_core.services.event import EventV1
from aegi_core.services.relation import RelationV1


@dataclass
class BuildGraphResult:
    """build_graph 的类型安全返回值。"""

    entities: list[EntityV1] = field(default_factory=list)
    events: list[EventV1] = field(default_factory=list)
    relations: list[RelationV1] = field(default_factory=list)
    action: ActionV1 | None = None
    tool_trace: ToolTraceV1 | None = None
    error: ProblemDetail | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


_EVENT_KEYWORDS = frozenset(
    {
        "deployment",
        "attack",
        "meeting",
        "summit",
        "exercise",
        "launch",
        "withdrawal",
        "sanction",
        "agreement",
        "conflict",
        "negotiation",
        "ceasefire",
        "invasion",
        "election",
        "coup",
    }
)

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

REQUIRED_ASSERTION_FIELDS = {
    "uid",
    "case_uid",
    "kind",
    "value",
    "source_claim_uids",
    "created_at",
}


def _validate_assertion_schema(assertion: AssertionV1) -> ProblemDetail | None:
    missing = REQUIRED_ASSERTION_FIELDS - set(assertion.model_dump().keys())
    if missing:
        return ProblemDetail(
            type="urn:aegi:error:schema_mismatch",
            title="Assertion schema mismatch",
            status=422,
            detail=f"Missing required fields: {sorted(missing)}",
            error_code="schema_mismatch",
        )
    return None


def _is_event_assertion(assertion: AssertionV1) -> bool:
    if "event" in assertion.kind.lower():
        return True
    text = " ".join(str(v) for v in assertion.value.values()).lower()
    return bool(_EVENT_KEYWORDS & set(text.split()))


def _extract_timestamp_ref(assertion: AssertionV1) -> str | None:
    text = " ".join(str(v) for v in assertion.value.values())
    match = _DATE_PATTERN.search(text)
    return match.group(0) if match else None


def build_graph(
    assertions: list[AssertionV1],
    *,
    case_uid: str,
    ontology_version: str,
    trace_id: str | None = None,
) -> BuildGraphResult:
    """从 AssertionV1 列表构建知识图谱。"""
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    for a in assertions:
        err = _validate_assertion_schema(a)
        if err:
            action = ActionV1(
                uid=uuid.uuid4().hex,
                case_uid=case_uid,
                action_type="kg_build",
                rationale=f"Schema mismatch: {err.detail}",
                inputs={"assertion_uid": a.uid},
                outputs={"error": err.model_dump()},
                trace_id=_trace_id,
                span_id=_span_id,
                created_at=now,
            )
            tool_trace = ToolTraceV1(
                uid=uuid.uuid4().hex,
                case_uid=case_uid,
                action_uid=action.uid,
                tool_name="kg_mapper",
                request={"assertion_uid": a.uid},
                response={"error": err.model_dump()},
                status="rejected",
                trace_id=_trace_id,
                span_id=_span_id,
                created_at=now,
            )
            return BuildGraphResult(
                action=action,
                tool_trace=tool_trace,
                error=err,
            )

    entities: list[EntityV1] = []
    events: list[EventV1] = []
    relations: list[RelationV1] = []
    entity_by_label: dict[str, EntityV1] = {}

    for a in assertions:
        value = a.value
        attributed_to = value.get("attributed_to")

        if _is_event_assertion(a):
            event = EventV1(
                uid=uuid.uuid4().hex,
                case_uid=case_uid,
                label=value.get("rationale", a.kind),
                event_type=a.kind,
                timestamp_ref=_extract_timestamp_ref(a),
                properties=value,
                source_assertion_uids=[a.uid],
                ontology_version=ontology_version,
                created_at=now,
            )
            events.append(event)

            if attributed_to and attributed_to not in entity_by_label:
                ent = EntityV1(
                    uid=uuid.uuid4().hex,
                    case_uid=case_uid,
                    label=attributed_to,
                    entity_type="actor",
                    properties={},
                    source_assertion_uids=[a.uid],
                    ontology_version=ontology_version,
                    created_at=now,
                )
                entities.append(ent)
                entity_by_label[attributed_to] = ent

            if attributed_to and attributed_to in entity_by_label:
                rel = RelationV1(
                    uid=uuid.uuid4().hex,
                    case_uid=case_uid,
                    source_entity_uid=entity_by_label[attributed_to].uid,
                    target_entity_uid=event.uid,
                    relation_type="participated_in",
                    properties={},
                    source_assertion_uids=[a.uid],
                    ontology_version=ontology_version,
                    created_at=now,
                )
                relations.append(rel)
        else:
            if attributed_to:
                if attributed_to not in entity_by_label:
                    ent = EntityV1(
                        uid=uuid.uuid4().hex,
                        case_uid=case_uid,
                        label=attributed_to,
                        entity_type="actor",
                        properties=value,
                        source_assertion_uids=[a.uid],
                        ontology_version=ontology_version,
                        created_at=now,
                    )
                    entities.append(ent)
                    entity_by_label[attributed_to] = ent
                else:
                    existing = entity_by_label[attributed_to]
                    existing.source_assertion_uids.append(a.uid)

    entity_list = list(entity_by_label.values())
    for i, e1 in enumerate(entity_list):
        for e2 in entity_list[i + 1 :]:
            shared = set(e1.source_assertion_uids) & set(e2.source_assertion_uids)
            if shared:
                rel = RelationV1(
                    uid=uuid.uuid4().hex,
                    case_uid=case_uid,
                    source_entity_uid=e1.uid,
                    target_entity_uid=e2.uid,
                    relation_type="co_mentioned",
                    properties={"shared_assertion_uids": sorted(shared)},
                    source_assertion_uids=sorted(shared),
                    ontology_version=ontology_version,
                    created_at=now,
                )
                relations.append(rel)

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="kg_build",
        rationale=(
            f"Built KG: {len(entities)} entities, {len(events)} events, "
            f"{len(relations)} relations from {len(assertions)} assertions"
        ),
        inputs={"assertion_uids": [a.uid for a in assertions]},
        outputs={
            "entity_uids": [e.uid for e in entities],
            "event_uids": [e.uid for e in events],
            "relation_uids": [r.uid for r in relations],
        },
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="kg_mapper",
        request={
            "assertion_count": len(assertions),
            "ontology_version": ontology_version,
        },
        response={
            "entity_count": len(entities),
            "event_count": len(events),
            "relation_count": len(relations),
        },
        status="ok",
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    return BuildGraphResult(
        entities=entities,
        events=events,
        relations=relations,
        action=action,
        tool_trace=tool_trace,
    )
