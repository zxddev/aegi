from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from baize_core.schemas.entity_event import (
    Entity,
    EntityType,
    Event,
    EventParticipant,
    EventType,
    GeoBBox,
    GeoPoint,
)
from baize_core.schemas.evidence import generate_uid


def test_geo_bbox_validation() -> None:
    with pytest.raises(ValueError, match="max_lon"):
        GeoBBox(min_lon=10.0, min_lat=0.0, max_lon=5.0, max_lat=2.0)


def test_event_requires_evidence() -> None:
    with pytest.raises(ValueError, match="证据"):
        Event(event_type=EventType.EXERCISE, summary="演习事件")


def test_event_time_range_validation() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="time_end"):
        Event(
            event_type=EventType.DEPLOYMENT,
            summary="部署事件",
            time_start=now,
            time_end=now - timedelta(hours=1),
            evidence_uids=[generate_uid("evi")],
        )


def test_entity_creation_ok() -> None:
    entity = Entity(
        entity_type=EntityType.FACILITY,
        name="空军基地",
        aliases=["基地A"],
        evidence_uids=[generate_uid("evi")],
        geo_point=GeoPoint(lon=120.0, lat=30.0),
    )
    assert entity.entity_uid.startswith("ent_")


def test_event_creation_ok() -> None:
    event = Event(
        event_type=EventType.EXERCISE,
        summary="联合演训",
        time_start=datetime.now(UTC),
        location_name="海域",
        participants=[
            EventParticipant(entity_uid=generate_uid("ent"), role="participant")
        ],
        evidence_uids=[generate_uid("evi")],
        geo_bbox=GeoBBox(min_lon=120.0, min_lat=20.0, max_lon=122.0, max_lat=22.0),
    )
    assert event.event_uid.startswith("evt_")
