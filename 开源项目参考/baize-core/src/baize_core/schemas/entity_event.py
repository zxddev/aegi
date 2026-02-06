"""实体与事件契约。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from baize_core.schemas.evidence import generate_uid


class EntityType(str, Enum):
    """实体类型。"""

    ACTOR = "Actor"
    ORGANIZATION = "Organization"
    UNIT = "Unit"
    FACILITY = "Facility"
    EQUIPMENT = "Equipment"
    GEOGRAPHY = "Geography"
    LEGAL_INSTRUMENT = "LegalInstrument"
    NARRATIVE = "Narrative"


class EventType(str, Enum):
    """事件类型。"""

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


class GeoPoint(BaseModel):
    """地理点位。"""

    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)


class GeoBBox(BaseModel):
    """地理范围。"""

    min_lon: float = Field(ge=-180.0, le=180.0)
    min_lat: float = Field(ge=-90.0, le=90.0)
    max_lon: float = Field(ge=-180.0, le=180.0)
    max_lat: float = Field(ge=-90.0, le=90.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> GeoBBox:
        """校验范围边界。"""

        if self.max_lon < self.min_lon:
            raise ValueError("max_lon 必须大于等于 min_lon")
        if self.max_lat < self.min_lat:
            raise ValueError("max_lat 必须大于等于 min_lat")
        return self


class Entity(BaseModel):
    """实体记录。"""

    entity_uid: str = Field(default_factory=lambda: generate_uid("ent"))
    entity_type: EntityType
    name: str = Field(min_length=1)
    summary: str | None = None
    aliases: list[str] = Field(default_factory=list)
    attrs: dict[str, object] = Field(default_factory=dict)
    geo_point: GeoPoint | None = None
    geo_bbox: GeoBBox | None = None
    evidence_uids: list[str] = Field(default_factory=list)


class EventParticipant(BaseModel):
    """事件参与方。"""

    entity_uid: str = Field(min_length=1)
    role: str = Field(min_length=1)


class Event(BaseModel):
    """事件记录。"""

    event_uid: str = Field(default_factory=lambda: generate_uid("evt"))
    event_type: EventType
    summary: str = Field(min_length=1)
    time_start: datetime | None = None
    time_end: datetime | None = None
    location_name: str | None = None
    geo_point: GeoPoint | None = None
    geo_bbox: GeoBBox | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    attrs: dict[str, object] = Field(default_factory=dict)
    participants: list[EventParticipant] = Field(default_factory=list)
    evidence_uids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_time_range(self) -> Event:
        """校验时间范围。"""

        if self.time_start and self.time_end and self.time_end < self.time_start:
            raise ValueError("time_end 必须晚于或等于 time_start")
        if not self.evidence_uids:
            raise ValueError("事件必须关联证据")
        return self
