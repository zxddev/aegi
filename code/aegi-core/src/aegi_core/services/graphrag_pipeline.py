# Author: msq
"""GraphRAG pipeline — LLM 结构化抽取实体/事件/关系。

适配自 baize-core/graph/graphrag_pipeline.py。
"""

from __future__ import annotations

import json as _json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from typing import Any

from aegi_core.contracts.extraction import ExtractionResult
from aegi_core.contracts.schemas import AssertionV1
from aegi_core.infra.llm_client import LLMClient
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services.entity import EntityV1
from aegi_core.services.event import EventV1
from aegi_core.services.kg_mapper import BuildGraphResult
from aegi_core.services import ontology_versioning
from aegi_core.services.ontology_versioning import (
    EntityTypeDef,
    EventTypeDef,
    OntologyVersion,
    RelationTypeDef,
)
from aegi_core.services.relation_fact_service import (
    RelationFactCreate,
    RelationFactService,
)
from aegi_core.services.relation import RelationV1

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EXTRACTION_SYSTEM_PROMPT = (
    "你是开源情报研究员，负责从文本中抽取实体、事件和关系。\n"
    "请识别文本中的：\n"
    "1. 实体：国家、组织、部队、设施、装备、地点、人物等\n"
    "2. 事件：军事行动、外交活动、部署变化、演习、冲突等\n"
    "3. 关系：实体之间的隶属、位置、同盟、敌对、合作等关系\n"
    "输出必须是严格 JSON，符合以下 schema：\n"
)


def _build_prompt(text: str) -> str:
    """构建抽取 prompt，包含 JSON schema。"""
    schema = ExtractionResult.model_json_schema()
    return (
        f"{EXTRACTION_SYSTEM_PROMPT}"
        f"{_json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"文本：\n{text[:3000]}\n\n"
        "请输出 JSON："
    )


def _parse_extraction(text: str) -> ExtractionResult:
    """从 LLM 输出中解析 ExtractionResult。"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    if "```" in text:
        for block in text.split("```"):
            block = block.strip().removeprefix("json").strip()
            if block.startswith("{"):
                text = block
                break
    return ExtractionResult.model_validate_json(text)


def _fuzzy_match(name: str, name_map: dict[str, str]) -> str | None:
    """模糊匹配名称（参考 baize-core）。"""
    low = name.lower()
    if low in name_map:
        return name_map[low]
    for k, v in name_map.items():
        if low in k or k in low:
            return v
    return None


def _build_fallback_ontology(
    extraction: ExtractionResult,
    *,
    version: str,
    created_at: datetime,
) -> OntologyVersion:
    """兼容模式：当版本仓库中缺失时，按本次抽取结果构造最小合同。"""
    return OntologyVersion(
        version=version,
        entity_types=[
            EntityTypeDef(name=t)
            for t in sorted(
                {entity.entity_type.value for entity in extraction.entities}
            )
        ],
        event_types=[
            EventTypeDef(name=t)
            for t in sorted({event.event_type.value for event in extraction.events})
        ],
        relation_types=[
            RelationTypeDef(name=t)
            for t in sorted({rel.relation_type.value for rel in extraction.relations})
        ],
        created_at=created_at,
    )


async def extract_and_index(
    assertions: list[AssertionV1],
    *,
    case_uid: str,
    ontology_version: str,
    llm: LLMClient,
    neo4j: Neo4jStore,
    session: AsyncSession | None = None,
    trace_id: str | None = None,
) -> BuildGraphResult:
    """从 assertions 的文本中抽取实体/事件/关系，写入 Neo4j。"""
    now = datetime.now(timezone.utc)

    # 收集文本：assertion value 中的 rationale + attributed_to，
    # 以及 value 的所有字符串值
    text_parts: list[str] = []
    for a in assertions:
        for v in a.value.values():
            if isinstance(v, str) and v:
                text_parts.append(v)
    combined_text = "\n".join(text_parts)

    if not combined_text.strip():
        return BuildGraphResult(error=_make_error("抽取文本为空，无法构建图谱"))

    # 调用 LLM 抽取（结构化输出，自动重试验证）
    prompt = _build_prompt(combined_text)
    extraction = await llm.invoke_structured(
        prompt,
        ExtractionResult,
        max_tokens=4096,
    )
    ontology = ontology_versioning.get_version(ontology_version)
    if ontology is None and session is not None:
        ontology = await ontology_versioning.get_version_db(ontology_version, session)
    if ontology is None:
        ontology = _build_fallback_ontology(
            extraction, version=ontology_version, created_at=now
        )
        ontology_versioning.register_version(ontology)

    # 转换为 aegi 领域对象
    entities: list[EntityV1] = []
    events: list[EventV1] = []
    relations: list[RelationV1] = []
    entity_name_to_uid: dict[str, str] = {}
    entity_uid_map: dict[str, EntityV1] = {}
    event_name_to_uid: dict[str, str] = {}
    assertion_uids = [a.uid for a in assertions]
    source_claim_uids = sorted(
        {
            claim_uid
            for assertion in assertions
            for claim_uid in assertion.source_claim_uids
            if claim_uid
        }
    )

    for e in extraction.entities:
        uid = uuid.uuid4().hex
        entity_obj = EntityV1(
            uid=uid,
            case_uid=case_uid,
            label=e.name,
            entity_type=e.entity_type.value,
            properties={"description": e.description or "", "aliases": e.aliases},
            source_assertion_uids=assertion_uids,
            ontology_version=ontology_version,
            created_at=now,
        )
        validation_error = ontology_versioning.validate_against_ontology(
            entity_obj, ontology
        )
        if validation_error is not None:
            return BuildGraphResult(error=validation_error)
        entities.append(entity_obj)
        entity_uid_map[uid] = entity_obj
        entity_name_to_uid[e.name.lower()] = uid
        for alias in e.aliases:
            entity_name_to_uid[alias.lower()] = uid

    for ev in extraction.events:
        uid = uuid.uuid4().hex
        events.append(
            EventV1(
                uid=uid,
                case_uid=case_uid,
                label=ev.summary,
                event_type=ev.event_type.value,
                timestamp_ref=ev.time_ref,
                properties={"participants": ev.participants},
                source_assertion_uids=assertion_uids,
                ontology_version=ontology_version,
                created_at=now,
            )
        )
        event_name_to_uid[ev.summary.lower()] = uid

    for r in extraction.relations:
        src_uid = _fuzzy_match(r.source_name, entity_name_to_uid)
        tgt_uid = _fuzzy_match(r.target_name, entity_name_to_uid)
        # 也尝试匹配事件
        if src_uid is None:
            src_uid = _fuzzy_match(r.source_name, event_name_to_uid)
        if tgt_uid is None:
            tgt_uid = _fuzzy_match(r.target_name, event_name_to_uid)
        if src_uid is None or tgt_uid is None:
            continue
        relation_obj = RelationV1(
            uid=uuid.uuid4().hex,
            case_uid=case_uid,
            source_entity_uid=src_uid,
            target_entity_uid=tgt_uid,
            relation_type=r.relation_type.value,
            properties={"description": r.description or ""},
            source_assertion_uids=assertion_uids,
            ontology_version=ontology_version,
            created_at=now,
        )
        validation_error = ontology_versioning.validate_against_ontology(
            relation_obj,
            ontology,
            source_entity=entity_uid_map.get(src_uid),
            target_entity=entity_uid_map.get(tgt_uid),
        )
        if validation_error is not None:
            return BuildGraphResult(error=validation_error)
        relations.append(relation_obj)

    # 先写 RelationFact 权威层，再投影到 Neo4j。
    if session is not None and relations:
        relation_service = RelationFactService(session)
        for relation in relations:
            source_entity = entity_uid_map.get(relation.source_entity_uid)
            target_entity = entity_uid_map.get(relation.target_entity_uid)
            try:
                fact = await relation_service.create(
                    RelationFactCreate(
                        case_uid=case_uid,
                        source_entity_uid=relation.source_entity_uid,
                        target_entity_uid=relation.target_entity_uid,
                        relation_type=relation.relation_type,
                        ontology_version=ontology_version,
                        source_entity_type=(
                            source_entity.entity_type
                            if source_entity is not None
                            else None
                        ),
                        target_entity_type=(
                            target_entity.entity_type
                            if target_entity is not None
                            else None
                        ),
                        supporting_source_claim_uids=source_claim_uids,
                        assessed_by="llm",
                        confidence=0.7,
                        properties=relation.properties,
                    )
                )
            except ValueError as exc:
                return BuildGraphResult(error=_make_error(str(exc)))
            relation.properties["relation_fact_uid"] = fact.uid

    # 写入 Neo4j
    await neo4j.upsert_nodes(
        "Entity",
        [
            {
                "uid": e.uid,
                "name": e.label,
                "type": e.entity_type,
                "case_uid": e.case_uid,
            }
            for e in entities
        ],
    )
    await neo4j.upsert_nodes(
        "Event",
        [
            {
                "uid": e.uid,
                "label": e.label,
                "type": e.event_type,
                "case_uid": e.case_uid,
                "timestamp_ref": e.timestamp_ref,
            }
            for e in events
        ],
    )
    for r in relations:
        src_is_entity = any(e.uid == r.source_entity_uid for e in entities)
        tgt_is_entity = any(e.uid == r.target_entity_uid for e in entities)
        await neo4j.upsert_edges(
            "Entity" if src_is_entity else "Event",
            "Entity" if tgt_is_entity else "Event",
            r.relation_type,
            [
                {
                    "source_uid": r.source_entity_uid,
                    "target_uid": r.target_entity_uid,
                    "properties": r.properties,
                }
            ],
        )

    return BuildGraphResult(
        entities=entities,
        events=events,
        relations=relations,
    )


def _make_error(detail: str) -> Any:
    from aegi_core.contracts.errors import ProblemDetail

    return ProblemDetail(
        type="urn:aegi:error:graphrag_extraction",
        title="GraphRAG extraction failed",
        status=422,
        detail=detail,
        error_code="graphrag_extraction_failed",
    )
