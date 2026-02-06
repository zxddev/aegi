# Author: msq
"""Ontology versioning service.

Source: openspec/changes/knowledge-graph-ontology-evolution/tasks.md (2.3)
Evidence:
  - 本体变更 MUST 带版本、兼容性报告与审计记录 (spec.md).
  - compatibility_report 必须包含 compatible/deprecated/breaking 分类 (spec.md acceptance #2).
  - case pinning 生效，未经审批不得越版本读取 (spec.md acceptance #3).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from aegi_core.contracts.audit import ActionV1, ToolTraceV1
from aegi_core.contracts.errors import ProblemDetail


class ChangeLevel(str, Enum):
    COMPATIBLE = "compatible"
    DEPRECATED = "deprecated"
    BREAKING = "breaking"


class OntologyChange(BaseModel):
    field: str
    description: str
    level: ChangeLevel


class CompatibilityReport(BaseModel):
    from_version: str
    to_version: str
    changes: list[OntologyChange] = Field(default_factory=list)
    overall_level: ChangeLevel
    auto_upgrade_allowed: bool
    migration_plan: str | None = None


class OntologyVersion(BaseModel):
    version: str
    entity_types: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    created_at: datetime


_registry: dict[str, OntologyVersion] = {}
_case_pins: dict[str, str] = {}


def reset_registry() -> None:
    _registry.clear()
    _case_pins.clear()


def register_version(version: OntologyVersion) -> None:
    _registry[version.version] = version


def get_version(version: str) -> OntologyVersion | None:
    return _registry.get(version)


def pin_case(case_uid: str, version: str) -> None:
    _case_pins[case_uid] = version


def get_case_pin(case_uid: str) -> str | None:
    return _case_pins.get(case_uid)


def _compare_type_lists(
    old: list[str],
    new: list[str],
    field: str,
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    old_set, new_set = set(old), set(new)
    for removed in sorted(old_set - new_set):
        changes.append(
            OntologyChange(
                field=field,
                description=f"Removed: {removed}",
                level=ChangeLevel.BREAKING,
            )
        )
    for added in sorted(new_set - old_set):
        changes.append(
            OntologyChange(
                field=field,
                description=f"Added: {added}",
                level=ChangeLevel.COMPATIBLE,
            )
        )
    return changes


def compute_compatibility(from_ver: str, to_ver: str) -> CompatibilityReport | ProblemDetail:
    old = _registry.get(from_ver)
    new = _registry.get(to_ver)
    if not old:
        return ProblemDetail(
            type="urn:aegi:error:not_found",
            title="Version not found",
            status=404,
            detail=f"Ontology version {from_ver} not found",
            error_code="not_found",
        )
    if not new:
        return ProblemDetail(
            type="urn:aegi:error:not_found",
            title="Version not found",
            status=404,
            detail=f"Ontology version {to_ver} not found",
            error_code="not_found",
        )

    changes: list[OntologyChange] = []
    changes.extend(_compare_type_lists(old.entity_types, new.entity_types, "entity_types"))
    changes.extend(_compare_type_lists(old.event_types, new.event_types, "event_types"))
    changes.extend(_compare_type_lists(old.relation_types, new.relation_types, "relation_types"))

    if not changes:
        overall = ChangeLevel.COMPATIBLE
    elif any(c.level == ChangeLevel.BREAKING for c in changes):
        overall = ChangeLevel.BREAKING
    elif any(c.level == ChangeLevel.DEPRECATED for c in changes):
        overall = ChangeLevel.DEPRECATED
    else:
        overall = ChangeLevel.COMPATIBLE

    auto_allowed = overall != ChangeLevel.BREAKING
    migration_plan = None
    if overall == ChangeLevel.BREAKING:
        breaking_items = [c.description for c in changes if c.level == ChangeLevel.BREAKING]
        migration_plan = f"Manual review required for: {'; '.join(breaking_items)}"

    return CompatibilityReport(
        from_version=from_ver,
        to_version=to_ver,
        changes=changes,
        overall_level=overall,
        auto_upgrade_allowed=auto_allowed,
        migration_plan=migration_plan,
    )


def upgrade_ontology(
    *,
    case_uid: str,
    from_version: str,
    to_version: str,
    approved: bool = False,
    trace_id: str | None = None,
) -> tuple[CompatibilityReport | ProblemDetail, ActionV1, ToolTraceV1]:
    """执行本体升级。

    Args:
        case_uid: 所属 case。
        from_version: 当前版本。
        to_version: 目标版本。
        approved: 是否已审批（breaking 变更需要）。
        trace_id: 分布式追踪 ID。

    Returns:
        (report_or_error, action, tool_trace)
    """
    _trace_id = trace_id or uuid.uuid4().hex
    _span_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc)

    report = compute_compatibility(from_version, to_version)
    if isinstance(report, ProblemDetail):
        action = ActionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_type="ontology_upgrade",
            rationale=report.detail or "Version not found",
            inputs={"from_version": from_version, "to_version": to_version},
            outputs={"error": report.model_dump()},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_uid=action.uid,
            tool_name="ontology_versioning",
            request={"from_version": from_version, "to_version": to_version},
            response={"error": report.model_dump()},
            status="rejected",
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        return report, action, tool_trace

    if report.overall_level == ChangeLevel.BREAKING and not approved:
        deny = ProblemDetail(
            type="urn:aegi:error:upgrade_denied",
            title="Breaking upgrade requires approval",
            status=403,
            detail=f"Upgrade {from_version} -> {to_version} is breaking; approval required",
            error_code="upgrade_denied",
        )
        action = ActionV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_type="ontology_upgrade",
            rationale="Denied: breaking upgrade without approval",
            inputs={"from_version": from_version, "to_version": to_version, "approved": False},
            outputs={"denied": True, "report": report.model_dump()},
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        tool_trace = ToolTraceV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            action_uid=action.uid,
            tool_name="ontology_versioning",
            request={"from_version": from_version, "to_version": to_version},
            response={"denied": True},
            status="denied",
            trace_id=_trace_id,
            span_id=_span_id,
            created_at=now,
        )
        return deny, action, tool_trace

    pin_case(case_uid, to_version)

    action = ActionV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_type="ontology_upgrade",
        rationale=f"Upgraded {from_version} -> {to_version} ({report.overall_level.value})",
        inputs={"from_version": from_version, "to_version": to_version, "approved": approved},
        outputs={"report": report.model_dump()},
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    tool_trace = ToolTraceV1(
        uid=uuid.uuid4().hex,
        case_uid=case_uid,
        action_uid=action.uid,
        tool_name="ontology_versioning",
        request={"from_version": from_version, "to_version": to_version},
        response={"overall_level": report.overall_level.value},
        status="ok",
        trace_id=_trace_id,
        span_id=_span_id,
        created_at=now,
    )
    return report, action, tool_trace
