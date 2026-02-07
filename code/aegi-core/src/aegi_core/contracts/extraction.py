# Author: msq
"""GraphRAG 抽取输出 Schema。

适配自 baize-core/schemas/extraction.py，保留国防/地缘情报领域类型体系。
用于 LLM structured output 的抽取结果定义。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExtractedEntityType(str, Enum):
    """抽取实体类型（9 种）。"""

    ACTOR = "Actor"
    ORGANIZATION = "Organization"
    UNIT = "Unit"
    FACILITY = "Facility"
    EQUIPMENT = "Equipment"
    GEOGRAPHY = "Geography"
    LEGAL_INSTRUMENT = "LegalInstrument"
    PERSON = "Person"
    OTHER = "Other"


class ExtractedEventType(str, Enum):
    """抽取事件类型（12 种）。"""

    STATEMENT = "Statement"
    DIPLOMATIC = "Diplomatic"
    ECONOMIC = "Economic"
    MILITARY_POSTURE = "MilitaryPosture"
    INCIDENT = "Incident"
    EXERCISE = "Exercise"
    DEPLOYMENT = "Deployment"
    MOVEMENT = "Movement"
    ENGAGEMENT = "Engagement"
    C2_CHANGE = "C2Change"
    SUPPORT_LOGISTICS = "SupportLogistics"
    FACILITY_ACTIVITY = "FacilityActivity"


class ExtractedRelationType(str, Enum):
    """抽取关系类型（10 种）。"""

    BELONGS_TO = "BELONGS_TO"
    LOCATED_AT = "LOCATED_AT"
    OPERATES = "OPERATES"
    ALLIED_WITH = "ALLIED_WITH"
    HOSTILE_TO = "HOSTILE_TO"
    COOPERATES_WITH = "COOPERATES_WITH"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    CAUSED_BY = "CAUSED_BY"
    FOLLOWS = "FOLLOWS"
    RELATED_TO = "RELATED_TO"


class ExtractedEntity(BaseModel):
    """从文本中抽取的实体。"""

    name: str = Field(min_length=1)
    entity_type: ExtractedEntityType
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractedEvent(BaseModel):
    """从文本中抽取的事件。"""

    summary: str = Field(min_length=1)
    event_type: ExtractedEventType
    time_ref: str | None = None
    participants: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractedRelation(BaseModel):
    """从文本中抽取的关系。"""

    source_name: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    relation_type: ExtractedRelationType
    description: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """综合抽取结果（LLM structured output 目标 schema）。"""

    entities: list[ExtractedEntity] = Field(default_factory=list)
    events: list[ExtractedEvent] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)
