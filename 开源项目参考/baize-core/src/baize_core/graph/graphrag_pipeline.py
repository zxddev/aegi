"""GraphRAG 轻量管线。

实现从文本抽取实体、事件和关系，并写入图谱。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from baize_core.graph.neo4j_store import Neo4jStore, Relation, RelationType
from baize_core.llm.runner import LlmRunner
from baize_core.schemas.entity_event import (
    Entity,
    EntityType,
    Event,
    EventParticipant,
    EventType,
    GeoPoint,
)
from baize_core.schemas.evidence import Chunk, Evidence
from baize_core.schemas.extraction import (
    ExtractedEntity,
    ExtractedEntityType,
    ExtractedEvent,
    ExtractedEventType,
    ExtractedRelation,
    ExtractedRelationType,
    ExtractionResult,
)
from baize_core.schemas.policy import StageType
from baize_core.storage.postgres import PostgresStore

EXTRACTION_SYSTEM_PROMPT = (
    "你是开源情报研究员，负责从文本中抽取实体、事件和关系。\n"
    "请识别文本中的：\n"
    "1. 实体：国家、组织、部队、设施、装备、地点等\n"
    "2. 事件：军事行动、外交活动、部署变化等\n"
    "3. 关系：实体之间的隶属、位置、同盟、敌对、合作等关系\n"
    "输出必须符合给定 JSON Schema。"
)

RELATION_EXTRACTION_SYSTEM_PROMPT = (
    "你是开源情报研究员，负责识别文本中实体之间的关系。\n"
    "关系类型包括：\n"
    "- BELONGS_TO：隶属关系（如：部队隶属于军区）\n"
    "- LOCATED_AT：位置关系（如：部队驻扎于基地）\n"
    "- OPERATES：运用关系（如：部队装备武器）\n"
    "- ALLIED_WITH：同盟关系（如：国家结盟）\n"
    "- HOSTILE_TO：敌对关系（如：国家对抗）\n"
    "- COOPERATES_WITH：合作关系（如：组织合作）\n"
    "- PARTICIPATES_IN：参与关系（如：实体参与事件）\n"
    "- CAUSED_BY：因果关系（如：事件导致事件）\n"
    "- FOLLOWS：时序关系（如：事件在事件之后）\n"
    "- RELATED_TO：通用关联\n"
    "输出必须符合给定 JSON Schema。"
)


@dataclass
class GraphRagPipeline:
    """GraphRAG 抽取与索引管线。

    实现从文本抽取实体、事件和关系，并写入图谱。
    """

    llm_runner: LlmRunner
    store: PostgresStore
    neo4j_store: Neo4jStore

    async def index_chunks(
        self,
        *,
        task_id: str,
        chunks: Iterable[Chunk],
        evidence: Iterable[Evidence],
    ) -> tuple[list[Entity], list[Event], list[Relation]]:
        """抽取并写入图谱。

        Args:
            task_id: 任务标识
            chunks: 文本块列表
            evidence: 证据列表

        Returns:
            (entities, events, relations) 元组
        """
        evidence_map = {item.chunk_uid: item for item in evidence}
        all_entities: list[Entity] = []
        all_events: list[Event] = []
        all_relations: list[Relation] = []
        entity_name_to_uid: dict[str, str] = {}
        event_name_to_uid: dict[str, str] = {}

        for chunk in chunks:
            prompt = _build_extraction_prompt(chunk.text)
            result = await self.llm_runner.generate_structured(
                system=EXTRACTION_SYSTEM_PROMPT,
                user=prompt,
                schema=ExtractionResult,
                stage=StageType.OBSERVE,
                task_id=task_id,
                max_retries=2,
            )
            extraction = cast(ExtractionResult, result.data)
            chunk_evidence = evidence_map.get(chunk.chunk_uid)
            evidence_uids = [chunk_evidence.evidence_uid] if chunk_evidence else []

            # 抽取实体
            entities = _to_entities(extraction.entities, evidence_uids)
            all_entities.extend(entities)
            # 建立名称到 UID 的映射（用于关系解析）
            for entity in entities:
                entity_name_to_uid[entity.name.lower()] = entity.entity_uid
                for alias in entity.aliases:
                    entity_name_to_uid[alias.lower()] = entity.entity_uid

            # 抽取事件
            events = _to_events(extraction.events, entity_name_to_uid, evidence_uids)
            all_events.extend(events)
            for event in events:
                # 关系抽取可能直接引用事件摘要，因此建立名称映射。
                event_name_to_uid[event.summary.lower()] = event.event_uid

            # 抽取关系
            relations = _to_relations(
                extraction.relations,
                entity_name_to_uid,
                evidence_uids,
                event_name_to_uid=event_name_to_uid,
            )
            all_relations.extend(relations)

        # 写入 PostgreSQL
        if all_entities:
            await self.store.store_entities(all_entities)
        if all_events:
            await self.store.store_events(all_events)

        # 写入 Neo4j
        if all_entities:
            await self.neo4j_store.upsert_entities(all_entities)
        if all_events:
            await self.neo4j_store.upsert_events(all_events)
            await self.neo4j_store.upsert_event_participants(all_events)
        if all_relations:
            await self.neo4j_store.upsert_relations(all_relations)

        return all_entities, all_events, all_relations

    async def extract_relations_only(
        self,
        *,
        task_id: str,
        text: str,
        known_entities: list[Entity],
        evidence_uids: list[str] | None = None,
    ) -> list[Relation]:
        """仅抽取关系（用于增量抽取）。

        Args:
            task_id: 任务标识
            text: 文本内容
            known_entities: 已知实体列表
            evidence_uids: 证据 UID 列表

        Returns:
            关系列表
        """
        # 建立名称到 UID 的映射
        entity_name_to_uid: dict[str, str] = {}
        for entity in known_entities:
            entity_name_to_uid[entity.name.lower()] = entity.entity_uid
            for alias in entity.aliases:
                entity_name_to_uid[alias.lower()] = entity.entity_uid

        # 构建关系抽取提示
        entity_names = [e.name for e in known_entities]
        prompt = _build_relation_extraction_prompt(text, entity_names)

        from baize_core.schemas.extraction import RelationExtractionResult

        result = await self.llm_runner.generate_structured(
            system=RELATION_EXTRACTION_SYSTEM_PROMPT,
            user=prompt,
            schema=RelationExtractionResult,
            stage=StageType.OBSERVE,
            task_id=task_id,
            max_retries=2,
        )

        relations = _to_relations(
            result.data.relations,
            entity_name_to_uid,
            evidence_uids or [],
        )

        if relations:
            await self.neo4j_store.upsert_relations(relations)

        return relations


def _build_extraction_prompt(text: str) -> str:
    """构建抽取提示词。"""

    snippet = text[:2000]
    return (
        "请从以下文本中抽取实体、事件和关系。\n"
        "实体包括：国家、组织、部队、设施、装备、地点、人物等。\n"
        "事件包括：军事行动、外交活动、部署变化、演习、冲突等。\n"
        "关系包括：隶属、位置、同盟、敌对、合作、参与等实体间联系。\n\n"
        f"文本：\n{snippet}"
    )


def _build_relation_extraction_prompt(text: str, entity_names: list[str]) -> str:
    """构建关系抽取提示词。"""

    snippet = text[:2000]
    entities_str = ", ".join(entity_names[:20])  # 限制实体数量
    return (
        f"已知实体：{entities_str}\n\n"
        "请识别以下文本中这些实体之间的关系：\n\n"
        f"文本：\n{snippet}\n\n"
        "请输出实体之间的关系，包括关系类型和描述。"
    )


def _to_entities(
    extracted: Iterable[ExtractedEntity], evidence_uids: list[str]
) -> list[Entity]:
    """将抽取实体转换为存储实体。"""

    result: list[Entity] = []
    for item in extracted:
        entity_type = _map_entity_type(item.entity_type)
        geo_point = None
        geo_bbox = None
        if (
            item.location
            and item.location.latitude is not None
            and item.location.longitude is not None
        ):
            geo_point = GeoPoint(
                lon=item.location.longitude, lat=item.location.latitude
            )
        result.append(
            Entity(
                entity_type=entity_type,
                name=item.name,
                summary=item.description,
                aliases=item.aliases,
                attrs=cast(dict[str, object], item.attributes),
                geo_point=geo_point,
                geo_bbox=geo_bbox,
                evidence_uids=list(evidence_uids),
            )
        )
    return result


def _to_events(
    extracted: Iterable[ExtractedEvent],
    entity_name_to_uid: dict[str, str],
    evidence_uids: list[str],
) -> list[Event]:
    """将抽取事件转换为存储事件。"""

    result: list[Event] = []
    for item in extracted:
        event_type = _map_event_type(item.event_type)
        geo_point = None
        geo_bbox = None
        if (
            item.location
            and item.location.latitude is not None
            and item.location.longitude is not None
        ):
            geo_point = GeoPoint(
                lon=item.location.longitude, lat=item.location.latitude
            )
        participants: list[EventParticipant] = []
        for participant in item.participants:
            resolved_uid = entity_name_to_uid.get(participant.name.lower())
            if resolved_uid is None:
                resolved_uid = _fuzzy_match_entity(participant.name, entity_name_to_uid)
            if resolved_uid is None:
                # 未能解析到实体 UID 时，跳过该参与方，避免写入时触发外键校验失败。
                continue
            role = (participant.role or "participant").strip() or "participant"
            participants.append(EventParticipant(entity_uid=resolved_uid, role=role))
        result.append(
            Event(
                event_type=event_type,
                summary=item.summary,
                time_start=item.time_range.start if item.time_range else None,
                time_end=item.time_range.end if item.time_range else None,
                location_name=item.location.name if item.location else None,
                geo_point=geo_point,
                geo_bbox=geo_bbox,
                confidence=item.confidence,
                tags=item.tags,
                attrs={},
                participants=participants,
                evidence_uids=list(evidence_uids),
            )
        )
    return result


def _map_entity_type(entity_type: ExtractedEntityType) -> EntityType:
    """映射实体类型。"""

    mapping = {
        ExtractedEntityType.ACTOR: EntityType.ACTOR,
        ExtractedEntityType.ORGANIZATION: EntityType.ORGANIZATION,
        ExtractedEntityType.UNIT: EntityType.UNIT,
        ExtractedEntityType.FACILITY: EntityType.FACILITY,
        ExtractedEntityType.EQUIPMENT: EntityType.EQUIPMENT,
        ExtractedEntityType.GEOGRAPHY: EntityType.GEOGRAPHY,
        ExtractedEntityType.LEGAL_INSTRUMENT: EntityType.LEGAL_INSTRUMENT,
        ExtractedEntityType.PERSON: EntityType.ACTOR,
        ExtractedEntityType.OTHER: EntityType.ORGANIZATION,
    }
    return mapping.get(entity_type, EntityType.ORGANIZATION)


def _map_event_type(event_type: ExtractedEventType) -> EventType:
    """映射事件类型。"""

    mapping = {
        ExtractedEventType.STATEMENT: EventType.STATEMENT,
        ExtractedEventType.DIPLOMATIC: EventType.DIPLOMATIC,
        ExtractedEventType.ECONOMIC: EventType.ECONOMIC,
        ExtractedEventType.MILITARY_POSTURE: EventType.MILITARY_POSTURE,
        ExtractedEventType.INCIDENT: EventType.INCIDENT,
        ExtractedEventType.EXERCISE: EventType.EXERCISE,
        ExtractedEventType.DEPLOYMENT: EventType.DEPLOYMENT,
        ExtractedEventType.MOVEMENT: EventType.MOVEMENT,
        ExtractedEventType.ENGAGEMENT: EventType.ENGAGEMENT,
        ExtractedEventType.C2_CHANGE: EventType.C2_CHANGE,
        ExtractedEventType.SUPPORT_LOGISTICS: EventType.SUPPORT_LOGISTICS,
        ExtractedEventType.FACILITY_ACTIVITY: EventType.FACILITY_ACTIVITY,
    }
    return mapping.get(event_type, EventType.INCIDENT)


def _to_relations(
    extracted: Iterable[ExtractedRelation],
    entity_name_to_uid: dict[str, str],
    evidence_uids: list[str],
    *,
    event_name_to_uid: dict[str, str] | None = None,
) -> list[Relation]:
    """将抽取关系转换为存储关系。

    Args:
        extracted: 抽取的关系列表
        entity_name_to_uid: 实体名称到 UID 的映射
        evidence_uids: 证据 UID 列表
        event_name_to_uid: 事件摘要到 UID 的映射（可选）

    Returns:
        转换后的关系列表
    """
    result: list[Relation] = []
    for item in extracted:
        relation_type = _map_relation_type(item.relation_type)

        source_uid: str | None = None
        target_uid: str | None = None

        if relation_type in {RelationType.CAUSED_BY, RelationType.FOLLOWS}:
            if event_name_to_uid is None:
                continue
            source_uid = event_name_to_uid.get(item.source_name.lower())
            if source_uid is None:
                source_uid = _fuzzy_match_event(item.source_name, event_name_to_uid)
            target_uid = event_name_to_uid.get(item.target_name.lower())
            if target_uid is None:
                target_uid = _fuzzy_match_event(item.target_name, event_name_to_uid)
        elif relation_type == RelationType.PARTICIPATES_IN:
            if event_name_to_uid is None:
                continue
            source_uid = entity_name_to_uid.get(item.source_name.lower())
            if source_uid is None:
                source_uid = _fuzzy_match_entity(item.source_name, entity_name_to_uid)
            target_uid = event_name_to_uid.get(item.target_name.lower())
            if target_uid is None:
                target_uid = _fuzzy_match_event(item.target_name, event_name_to_uid)
        else:
            source_uid = entity_name_to_uid.get(item.source_name.lower())
            if source_uid is None:
                source_uid = _fuzzy_match_entity(item.source_name, entity_name_to_uid)
            target_uid = entity_name_to_uid.get(item.target_name.lower())
            if target_uid is None:
                target_uid = _fuzzy_match_entity(item.target_name, entity_name_to_uid)

        if source_uid is None or target_uid is None:
            continue

        # 生成关系 UID
        relation_uid = f"rel_{uuid4().hex[:12]}"

        result.append(
            Relation(
                relation_uid=relation_uid,
                relation_type=relation_type,
                source_uid=source_uid,
                target_uid=target_uid,
                properties={
                    "description": item.description or "",
                    **item.properties,
                },
                confidence=item.confidence,
                evidence_uids=list(evidence_uids),
            )
        )
    return result


def _map_relation_type(relation_type: ExtractedRelationType) -> RelationType:
    """映射关系类型。"""

    mapping = {
        ExtractedRelationType.BELONGS_TO: RelationType.BELONGS_TO,
        ExtractedRelationType.LOCATED_AT: RelationType.LOCATED_AT,
        ExtractedRelationType.OPERATES: RelationType.OPERATES,
        ExtractedRelationType.ALLIED_WITH: RelationType.ALLIED_WITH,
        ExtractedRelationType.HOSTILE_TO: RelationType.HOSTILE_TO,
        ExtractedRelationType.COOPERATES_WITH: RelationType.COOPERATES_WITH,
        ExtractedRelationType.PARTICIPATES_IN: RelationType.PARTICIPATES_IN,
        ExtractedRelationType.CAUSED_BY: RelationType.CAUSED_BY,
        ExtractedRelationType.FOLLOWS: RelationType.FOLLOWS,
        ExtractedRelationType.RELATED_TO: RelationType.RELATED_TO,
    }
    return mapping.get(relation_type, RelationType.RELATED_TO)


def _fuzzy_match_entity(name: str, entity_name_to_uid: dict[str, str]) -> str | None:
    """模糊匹配实体名称。

    尝试通过部分匹配找到实体。
    """
    name_lower = name.lower()
    # 尝试精确匹配
    if name_lower in entity_name_to_uid:
        return entity_name_to_uid[name_lower]

    # 尝试包含匹配
    for entity_name, uid in entity_name_to_uid.items():
        if name_lower in entity_name or entity_name in name_lower:
            return uid

    return None


def _fuzzy_match_event(name: str, event_name_to_uid: dict[str, str]) -> str | None:
    """模糊匹配事件摘要。"""
    name_lower = name.lower()
    if name_lower in event_name_to_uid:
        return event_name_to_uid[name_lower]
    for event_summary, uid in event_name_to_uid.items():
        if name_lower in event_summary or event_summary in name_lower:
            return uid
    return None
