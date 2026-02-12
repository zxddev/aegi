# Author: msq
"""本体版本管理服务。

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
from typing import Any

from pydantic import BaseModel, Field, field_validator

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


def _normalize_property_names(value: list[str] | None) -> list[str]:
    if not value:
        return []
    # 保持输入顺序并去重，避免同名属性重复出现。
    return list(dict.fromkeys(v for v in value if v))


class EntityTypeDef(BaseModel):
    name: str
    required_properties: list[str] = Field(default_factory=list)
    optional_properties: list[str] = Field(default_factory=list)
    description: str = ""
    deprecated: bool = False
    deprecated_by: str | None = None

    @field_validator("required_properties", "optional_properties", mode="before")
    @classmethod
    def _normalize_props(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return _normalize_property_names([str(v) for v in value])


class RelationTypeDef(BaseModel):
    name: str
    domain: list[str] = Field(default_factory=list)
    range: list[str] = Field(default_factory=list)
    cardinality: str = "many-to-many"
    properties: list[str] = Field(default_factory=list)
    temporal: bool = False
    description: str = ""
    deprecated: bool = False

    @field_validator("domain", "range", "properties", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return _normalize_property_names([str(v) for v in value])


class EventTypeDef(BaseModel):
    name: str
    participant_roles: list[str] = Field(default_factory=list)
    required_properties: list[str] = Field(default_factory=list)
    description: str = ""
    deprecated: bool = False

    @field_validator("participant_roles", "required_properties", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return _normalize_property_names([str(v) for v in value])


def _to_entity_type_def(raw: str | dict[str, Any] | EntityTypeDef) -> EntityTypeDef:
    if isinstance(raw, EntityTypeDef):
        return raw
    if isinstance(raw, str):
        return EntityTypeDef(name=raw)
    if isinstance(raw, dict):
        return EntityTypeDef.model_validate(raw)
    return EntityTypeDef(name=str(raw))


def _to_relation_type_def(
    raw: str | dict[str, Any] | RelationTypeDef,
) -> RelationTypeDef:
    if isinstance(raw, RelationTypeDef):
        return raw
    if isinstance(raw, str):
        return RelationTypeDef(name=raw)
    if isinstance(raw, dict):
        return RelationTypeDef.model_validate(raw)
    return RelationTypeDef(name=str(raw))


def _to_event_type_def(raw: str | dict[str, Any] | EventTypeDef) -> EventTypeDef:
    if isinstance(raw, EventTypeDef):
        return raw
    if isinstance(raw, str):
        return EventTypeDef(name=raw)
    if isinstance(raw, dict):
        return EventTypeDef.model_validate(raw)
    return EventTypeDef(name=str(raw))


class OntologyVersion(BaseModel):
    version: str
    entity_types: list[EntityTypeDef] = Field(default_factory=list)
    event_types: list[EventTypeDef] = Field(default_factory=list)
    relation_types: list[RelationTypeDef] = Field(default_factory=list)
    created_at: datetime

    @field_validator("entity_types", mode="before")
    @classmethod
    def _normalize_entity_types(cls, value: Any) -> list[EntityTypeDef]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [_to_entity_type_def(v) for v in value]

    @field_validator("event_types", mode="before")
    @classmethod
    def _normalize_event_types(cls, value: Any) -> list[EventTypeDef]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [_to_event_type_def(v) for v in value]

    @field_validator("relation_types", mode="before")
    @classmethod
    def _normalize_relation_types(cls, value: Any) -> list[RelationTypeDef]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [_to_relation_type_def(v) for v in value]

    def entity_types_payload(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.entity_types]

    def event_types_payload(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.event_types]

    def relation_types_payload(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.relation_types]


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


async def get_version_db(
    version: str,
    session: "AsyncSession",  # noqa: F821
) -> OntologyVersion | None:
    """DB-first 读取版本，内存缓存作为快路径。"""
    cached = _registry.get(version)
    if cached is not None:
        return cached
    import sqlalchemy as sa

    from aegi_core.db.models.ontology import OntologyVersionRow

    row = (
        await session.execute(
            sa.select(OntologyVersionRow).where(OntologyVersionRow.version == version)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    obj = OntologyVersion(
        version=row.version,
        entity_types=row.entity_types,
        event_types=row.event_types,
        relation_types=row.relation_types,
        created_at=row.created_at,
    )
    _registry[version] = obj
    return obj


async def get_case_pin_db(
    case_uid: str,
    session: "AsyncSession",  # noqa: F821
) -> str | None:
    """DB-first 读取 case pin，内存缓存作为快路径。"""
    cached = _case_pins.get(case_uid)
    if cached is not None:
        return cached
    import sqlalchemy as sa

    from aegi_core.db.models.ontology import CasePinRow

    row = (
        await session.execute(
            sa.select(CasePinRow).where(CasePinRow.case_uid == case_uid)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    _case_pins[case_uid] = row.ontology_version
    return row.ontology_version


# ── async DB 持久化（内存 + Postgres 双写）──────────────────────


async def register_version_db(
    version: OntologyVersion,
    session: "AsyncSession",  # noqa: F821
) -> None:
    """注册版本到内存 + DB。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from aegi_core.db.models.ontology import OntologyVersionRow

    register_version(version)
    stmt = (
        pg_insert(OntologyVersionRow)
        .values(
            version=version.version,
            entity_types=version.entity_types_payload(),
            event_types=version.event_types_payload(),
            relation_types=version.relation_types_payload(),
            created_at=version.created_at,
        )
        .on_conflict_do_update(
            index_elements=["version"],
            set_={
                "entity_types": version.entity_types_payload(),
                "event_types": version.event_types_payload(),
                "relation_types": version.relation_types_payload(),
            },
        )
    )
    await session.execute(stmt)


async def pin_case_db(
    case_uid: str,
    version: str,
    session: "AsyncSession",  # noqa: F821
) -> None:
    """Pin case 到内存 + DB。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from aegi_core.db.models.ontology import CasePinRow

    pin_case(case_uid, version)
    stmt = (
        pg_insert(CasePinRow)
        .values(
            case_uid=case_uid,
            ontology_version=version,
        )
        .on_conflict_do_update(
            index_elements=["case_uid"],
            set_={"ontology_version": version},
        )
    )
    await session.execute(stmt)


async def load_from_db(session: "AsyncSession") -> None:  # noqa: F821
    """启动时从 DB 加载到内存缓存。"""
    import sqlalchemy as sa

    from aegi_core.db.models.ontology import CasePinRow, OntologyVersionRow

    rows = (await session.execute(sa.select(OntologyVersionRow))).scalars().all()
    for r in rows:
        _registry[r.version] = OntologyVersion(
            version=r.version,
            entity_types=r.entity_types,
            event_types=r.event_types,
            relation_types=r.relation_types,
            created_at=r.created_at,
        )
    pins = (await session.execute(sa.select(CasePinRow))).scalars().all()
    for p in pins:
        _case_pins[p.case_uid] = p.ontology_version


def _compare_name_sets(
    old_names: set[str],
    new_names: set[str],
    field: str,
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    for removed in sorted(old_names - new_names):
        changes.append(
            OntologyChange(
                field=field,
                description=f"Removed: {removed}",
                level=ChangeLevel.BREAKING,
            )
        )
    for added in sorted(new_names - old_names):
        changes.append(
            OntologyChange(
                field=field,
                description=f"Added: {added}",
                level=ChangeLevel.COMPATIBLE,
            )
        )
    return changes


def _as_name_map(items: list[BaseModel]) -> dict[str, BaseModel]:
    return {
        str(getattr(item, "name")): item for item in items if getattr(item, "name", "")
    }


def _compare_property_sets(
    *,
    field: str,
    name: str,
    old_values: list[str],
    new_values: list[str],
    removed_level: ChangeLevel,
    added_level: ChangeLevel,
    label: str,
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    old_set = set(old_values)
    new_set = set(new_values)
    for removed in sorted(old_set - new_set):
        changes.append(
            OntologyChange(
                field=f"{field}.{name}.{label}",
                description=f"Removed {label}: {removed}",
                level=removed_level,
            )
        )
    for added in sorted(new_set - old_set):
        changes.append(
            OntologyChange(
                field=f"{field}.{name}.{label}",
                description=f"Added {label}: {added}",
                level=added_level,
            )
        )
    return changes


def _compare_entity_defs(
    old: EntityTypeDef, new: EntityTypeDef
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    name = old.name
    changes.extend(
        _compare_property_sets(
            field="entity_types",
            name=name,
            old_values=old.required_properties,
            new_values=new.required_properties,
            removed_level=ChangeLevel.COMPATIBLE,
            added_level=ChangeLevel.BREAKING,
            label="required_properties",
        )
    )
    changes.extend(
        _compare_property_sets(
            field="entity_types",
            name=name,
            old_values=old.optional_properties,
            new_values=new.optional_properties,
            removed_level=ChangeLevel.DEPRECATED,
            added_level=ChangeLevel.COMPATIBLE,
            label="optional_properties",
        )
    )
    if not old.deprecated and new.deprecated:
        changes.append(
            OntologyChange(
                field=f"entity_types.{name}.deprecated",
                description=f"Deprecated: {name}",
                level=ChangeLevel.DEPRECATED,
            )
        )
    if old.deprecated_by != new.deprecated_by and new.deprecated_by:
        changes.append(
            OntologyChange(
                field=f"entity_types.{name}.deprecated_by",
                description=f"{name} deprecated by {new.deprecated_by}",
                level=ChangeLevel.DEPRECATED,
            )
        )
    return changes


def _compare_event_defs(old: EventTypeDef, new: EventTypeDef) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    name = old.name
    changes.extend(
        _compare_property_sets(
            field="event_types",
            name=name,
            old_values=old.participant_roles,
            new_values=new.participant_roles,
            removed_level=ChangeLevel.BREAKING,
            added_level=ChangeLevel.COMPATIBLE,
            label="participant_roles",
        )
    )
    changes.extend(
        _compare_property_sets(
            field="event_types",
            name=name,
            old_values=old.required_properties,
            new_values=new.required_properties,
            removed_level=ChangeLevel.COMPATIBLE,
            added_level=ChangeLevel.BREAKING,
            label="required_properties",
        )
    )
    if not old.deprecated and new.deprecated:
        changes.append(
            OntologyChange(
                field=f"event_types.{name}.deprecated",
                description=f"Deprecated: {name}",
                level=ChangeLevel.DEPRECATED,
            )
        )
    return changes


def _compare_constraint_scope(
    *,
    field: str,
    relation_name: str,
    old_values: list[str],
    new_values: list[str],
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    old_set = set(old_values)
    new_set = set(new_values)

    if not old_set and new_set:
        changes.append(
            OntologyChange(
                field=f"relation_types.{relation_name}.{field}",
                description=f"Introduced {field} restriction: {sorted(new_set)}",
                level=ChangeLevel.BREAKING,
            )
        )
        return changes
    if old_set and not new_set:
        changes.append(
            OntologyChange(
                field=f"relation_types.{relation_name}.{field}",
                description=f"Removed {field} restriction (now unconstrained)",
                level=ChangeLevel.COMPATIBLE,
            )
        )
        return changes

    for removed in sorted(old_set - new_set):
        changes.append(
            OntologyChange(
                field=f"relation_types.{relation_name}.{field}",
                description=f"Removed allowed {field} type: {removed}",
                level=ChangeLevel.BREAKING,
            )
        )
    for added in sorted(new_set - old_set):
        changes.append(
            OntologyChange(
                field=f"relation_types.{relation_name}.{field}",
                description=f"Added allowed {field} type: {added}",
                level=ChangeLevel.COMPATIBLE,
            )
        )
    return changes


def _compare_relation_defs(
    old: RelationTypeDef, new: RelationTypeDef
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    name = old.name
    changes.extend(
        _compare_constraint_scope(
            field="domain",
            relation_name=name,
            old_values=old.domain,
            new_values=new.domain,
        )
    )
    changes.extend(
        _compare_constraint_scope(
            field="range",
            relation_name=name,
            old_values=old.range,
            new_values=new.range,
        )
    )
    if old.cardinality != new.cardinality:
        changes.append(
            OntologyChange(
                field=f"relation_types.{name}.cardinality",
                description=f"Cardinality changed: {old.cardinality} -> {new.cardinality}",
                level=ChangeLevel.BREAKING,
            )
        )
    changes.extend(
        _compare_property_sets(
            field="relation_types",
            name=name,
            old_values=old.properties,
            new_values=new.properties,
            removed_level=ChangeLevel.BREAKING,
            added_level=ChangeLevel.COMPATIBLE,
            label="properties",
        )
    )
    if old.temporal and not new.temporal:
        changes.append(
            OntologyChange(
                field=f"relation_types.{name}.temporal",
                description=f"Temporal support removed for {name}",
                level=ChangeLevel.BREAKING,
            )
        )
    elif not old.temporal and new.temporal:
        changes.append(
            OntologyChange(
                field=f"relation_types.{name}.temporal",
                description=f"Temporal support added for {name}",
                level=ChangeLevel.COMPATIBLE,
            )
        )
    if not old.deprecated and new.deprecated:
        changes.append(
            OntologyChange(
                field=f"relation_types.{name}.deprecated",
                description=f"Deprecated: {name}",
                level=ChangeLevel.DEPRECATED,
            )
        )
    return changes


def _compare_typed_defs(
    old_items: list[BaseModel],
    new_items: list[BaseModel],
    field: str,
) -> list[OntologyChange]:
    changes: list[OntologyChange] = []
    old_map = _as_name_map(old_items)
    new_map = _as_name_map(new_items)
    old_names = set(old_map)
    new_names = set(new_map)
    changes.extend(_compare_name_sets(old_names, new_names, field))

    for name in sorted(old_names & new_names):
        old_item = old_map[name]
        new_item = new_map[name]
        if isinstance(old_item, EntityTypeDef) and isinstance(new_item, EntityTypeDef):
            changes.extend(_compare_entity_defs(old_item, new_item))
        elif isinstance(old_item, EventTypeDef) and isinstance(new_item, EventTypeDef):
            changes.extend(_compare_event_defs(old_item, new_item))
        elif isinstance(old_item, RelationTypeDef) and isinstance(
            new_item, RelationTypeDef
        ):
            changes.extend(_compare_relation_defs(old_item, new_item))
    return changes


def _compute_compatibility_from_versions(
    old: OntologyVersion | None,
    new: OntologyVersion | None,
    from_ver: str,
    to_ver: str,
) -> CompatibilityReport | ProblemDetail:
    """内部：基于已加载的版本对象计算兼容性。"""
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
    changes.extend(
        _compare_typed_defs(old.entity_types, new.entity_types, "entity_types")
    )
    changes.extend(_compare_typed_defs(old.event_types, new.event_types, "event_types"))
    changes.extend(
        _compare_typed_defs(old.relation_types, new.relation_types, "relation_types")
    )

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
        breaking_items = [
            c.description for c in changes if c.level == ChangeLevel.BREAKING
        ]
        migration_plan = f"Manual review required for: {'; '.join(breaking_items)}"

    return CompatibilityReport(
        from_version=from_ver,
        to_version=to_ver,
        changes=changes,
        overall_level=overall,
        auto_upgrade_allowed=auto_allowed,
        migration_plan=migration_plan,
    )


def compute_compatibility(
    from_ver: str, to_ver: str
) -> CompatibilityReport | ProblemDetail:
    """内存版兼容性计算（向后兼容）。"""
    return _compute_compatibility_from_versions(
        _registry.get(from_ver), _registry.get(to_ver), from_ver, to_ver
    )


async def compute_compatibility_db(
    from_ver: str,
    to_ver: str,
    session: "AsyncSession",  # noqa: F821
) -> CompatibilityReport | ProblemDetail:
    """DB-first 兼容性计算，多进程安全。"""
    old = await get_version_db(from_ver, session)
    new = await get_version_db(to_ver, session)
    return _compute_compatibility_from_versions(old, new, from_ver, to_ver)


def _to_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        dumped = payload.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _ontology_validation_error(
    *,
    error_code: str,
    detail: str,
    extensions: dict[str, Any] | None = None,
) -> ProblemDetail:
    return ProblemDetail(
        type=f"urn:aegi:error:{error_code}",
        title="Ontology validation failed",
        status=422,
        detail=detail,
        error_code=error_code,
        extensions=extensions or {},
    )


def validate_against_ontology(
    candidate: Any,
    ontology_version: OntologyVersion,
    *,
    source_entity: Any | None = None,
    target_entity: Any | None = None,
) -> ProblemDetail | None:
    """校验 entity/relation 是否符合本体合同约束。

    Args:
        candidate: 待写入对象（EntityV1/RelationV1 或 dict）。
        ontology_version: 目标本体版本对象。
        source_entity: relation 校验时可选的源实体对象。
        target_entity: relation 校验时可选的目标实体对象。

    Returns:
        不符合约束时返回 ProblemDetail；合法时返回 None。
    """
    payload = _to_mapping(candidate)
    if not payload:
        return _ontology_validation_error(
            error_code="ontology_validation_failed",
            detail="Candidate payload is empty",
        )

    entity_type = payload.get("entity_type")
    relation_type = payload.get("relation_type")
    entity_defs = {item.name: item for item in ontology_version.entity_types}
    relation_defs = {item.name: item for item in ontology_version.relation_types}

    if entity_type:
        type_def = entity_defs.get(str(entity_type))
        if type_def is None:
            return _ontology_validation_error(
                error_code="ontology_entity_type_not_allowed",
                detail=f"Entity type '{entity_type}' is not allowed in {ontology_version.version}",
                extensions={"entity_type": entity_type},
            )
        properties = payload.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        missing = sorted(set(type_def.required_properties) - set(properties.keys()))
        if missing:
            return _ontology_validation_error(
                error_code="ontology_entity_missing_properties",
                detail=(
                    f"Entity type '{entity_type}' missing required properties: {', '.join(missing)}"
                ),
                extensions={"missing_properties": missing},
            )
        return None

    if relation_type:
        type_def = relation_defs.get(str(relation_type))
        if type_def is None:
            return _ontology_validation_error(
                error_code="ontology_relation_type_not_allowed",
                detail=(
                    f"Relation type '{relation_type}' is not allowed in "
                    f"{ontology_version.version}"
                ),
                extensions={"relation_type": relation_type},
            )
        properties = payload.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        missing = sorted(set(type_def.properties) - set(properties.keys()))
        if missing:
            return _ontology_validation_error(
                error_code="ontology_relation_missing_properties",
                detail=(
                    f"Relation type '{relation_type}' missing required properties: "
                    f"{', '.join(missing)}"
                ),
                extensions={"missing_properties": missing},
            )

        source_type = _to_mapping(source_entity).get("entity_type")
        if type_def.domain and source_type and source_type not in set(type_def.domain):
            return _ontology_validation_error(
                error_code="ontology_relation_domain_violation",
                detail=(
                    f"Relation '{relation_type}' source entity_type '{source_type}' not in "
                    f"domain {type_def.domain}"
                ),
                extensions={"source_type": source_type, "domain": type_def.domain},
            )

        target_type = _to_mapping(target_entity).get("entity_type")
        if type_def.range and target_type and target_type not in set(type_def.range):
            return _ontology_validation_error(
                error_code="ontology_relation_range_violation",
                detail=(
                    f"Relation '{relation_type}' target entity_type '{target_type}' not in "
                    f"range {type_def.range}"
                ),
                extensions={"target_type": target_type, "range": type_def.range},
            )
        return None

    return _ontology_validation_error(
        error_code="ontology_candidate_shape_invalid",
        detail="Candidate must contain either entity_type or relation_type",
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
            inputs={
                "from_version": from_version,
                "to_version": to_version,
                "approved": False,
            },
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
        inputs={
            "from_version": from_version,
            "to_version": to_version,
            "approved": approved,
        },
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
