"""实体与事件 Repository。

负责实体（Entity）、事件（Event）及其关联关系的数据库操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from geoalchemy2 import WKTElement
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from baize_core.schemas.entity_event import (
    Entity,
    EntityType,
    Event,
    EventParticipant,
    EventType,
    GeoBBox,
    GeoPoint,
)
from baize_core.storage import models


def _point_to_wkt(point: GeoPoint | None) -> WKTElement | None:
    """将点位转换为 WKT。"""
    if point is None:
        return None
    return WKTElement(f"POINT({point.lon} {point.lat})", srid=4326)


def _bbox_to_wkt(bbox: GeoBBox | None) -> WKTElement | None:
    """将范围转换为 WKT。"""
    if bbox is None:
        return None
    wkt = (
        "POLYGON(("
        f"{bbox.min_lon} {bbox.min_lat},"
        f"{bbox.max_lon} {bbox.min_lat},"
        f"{bbox.max_lon} {bbox.max_lat},"
        f"{bbox.min_lon} {bbox.max_lat},"
        f"{bbox.min_lon} {bbox.min_lat}"
        "))"
    )
    return WKTElement(wkt, srid=4326)


def _point_from_wkt(wkt: str | None) -> GeoPoint | None:
    """从 WKT 解析点位。"""
    if not wkt:
        return None
    if not wkt.startswith("POINT(") or not wkt.endswith(")"):
        raise ValueError(f"无法解析点位 WKT: {wkt}")
    coords = wkt.removeprefix("POINT(").removesuffix(")").strip()
    parts = coords.split()
    if len(parts) != 2:
        raise ValueError(f"无法解析点位坐标: {wkt}")
    lon, lat = (float(parts[0]), float(parts[1]))
    return GeoPoint(lon=lon, lat=lat)


def _bbox_from_wkt(wkt: str | None) -> GeoBBox | None:
    """从 WKT 解析范围。"""
    if not wkt:
        return None
    if not wkt.startswith("POLYGON((") or not wkt.endswith("))"):
        raise ValueError(f"无法解析范围 WKT: {wkt}")
    coords = wkt.removeprefix("POLYGON((").removesuffix("))")
    points = [segment.strip() for segment in coords.split(",") if segment.strip()]
    lon_values: list[float] = []
    lat_values: list[float] = []
    for point in points:
        parts = point.split()
        if len(parts) != 2:
            raise ValueError(f"无法解析范围坐标: {wkt}")
        lon_values.append(float(parts[0]))
        lat_values.append(float(parts[1]))
    if not lon_values or not lat_values:
        raise ValueError(f"范围坐标为空: {wkt}")
    return GeoBBox(
        min_lon=min(lon_values),
        min_lat=min(lat_values),
        max_lon=max(lon_values),
        max_lat=max(lat_values),
    )


@dataclass
class EntityRepository:
    """实体与事件 Repository。

    Attributes:
        session_factory: SQLAlchemy 异步会话工厂
    """

    session_factory: async_sessionmaker[AsyncSession]

    # =========================================================================
    # 实体操作
    # =========================================================================

    async def store_entities(self, entities: list[Entity]) -> None:
        """写入实体与证据关联。

        Args:
            entities: 实体列表
        """
        if not entities:
            return
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            entity_type_map = await self._ensure_entity_types(session)
            records: list[tuple[Entity, models.EntityModel]] = []
            for entity in entities:
                entity_type_id = entity_type_map.get(entity.entity_type.value)
                if entity_type_id is None:
                    raise ValueError(f"未知实体类型: {entity.entity_type}")
                record = models.EntityModel(
                    entity_uid=entity.entity_uid,
                    entity_type_id=entity_type_id,
                    name=entity.name,
                    summary=entity.summary,
                    attrs=entity.attrs,
                    geo_point=_point_to_wkt(entity.geo_point),
                    geo_bbox=_bbox_to_wkt(entity.geo_bbox),
                    created_at=now,
                )
                session.add(record)
                records.append((entity, record))
            await session.flush()
            for entity, record in records:
                for alias in entity.aliases:
                    session.add(
                        models.EntityAliasModel(
                            entity_id=record.entity_id,
                            alias=alias,
                        )
                    )
                for evidence_uid in entity.evidence_uids:
                    session.add(
                        models.EntityEvidenceModel(
                            entity_id=record.entity_id,
                            evidence_uid=evidence_uid,
                        )
                    )
            await session.commit()

    async def get_by_uid(self, entity_uid: str) -> Entity | None:
        """按 UID 读取实体。

        Args:
            entity_uid: 实体 UID

        Returns:
            实体，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    models.EntityModel.entity_id,
                    models.EntityModel.entity_uid,
                    models.EntityTypeModel.code,
                    models.EntityModel.name,
                    models.EntityModel.summary,
                    models.EntityModel.attrs,
                    func.ST_AsText(models.EntityModel.geo_point),
                    func.ST_AsText(models.EntityModel.geo_bbox),
                )
                .join(
                    models.EntityTypeModel,
                    models.EntityTypeModel.entity_type_id
                    == models.EntityModel.entity_type_id,
                )
                .where(models.EntityModel.entity_uid == entity_uid)
            )
            row = result.one_or_none()
            if row is None:
                return None
            entity_id = row[0]
            alias_rows = await session.execute(
                select(models.EntityAliasModel.alias).where(
                    models.EntityAliasModel.entity_id == entity_id
                )
            )
            evidence_rows = await session.execute(
                select(models.EntityEvidenceModel.evidence_uid).where(
                    models.EntityEvidenceModel.entity_id == entity_id
                )
            )
            return Entity(
                entity_uid=row[1],
                entity_type=EntityType(row[2]),
                name=row[3],
                summary=row[4],
                attrs=row[5] or {},
                geo_point=_point_from_wkt(row[6]),
                geo_bbox=_bbox_from_wkt(row[7]),
                aliases=[alias for (alias,) in alias_rows.all()],
                evidence_uids=[evidence for (evidence,) in evidence_rows.all()],
            )

    async def list_entities(
        self,
        *,
        entity_types: list[EntityType] | None,
        bbox: GeoBBox | None,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        """按条件查询实体列表。

        Args:
            entity_types: 实体类型过滤
            bbox: 地理范围过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            实体列表
        """
        async with self.session_factory() as session:
            query = (
                select(
                    models.EntityModel.entity_id,
                    models.EntityModel.entity_uid,
                    models.EntityTypeModel.code,
                    models.EntityModel.name,
                    models.EntityModel.summary,
                    models.EntityModel.attrs,
                    func.ST_AsText(models.EntityModel.geo_point),
                    func.ST_AsText(models.EntityModel.geo_bbox),
                )
                .join(
                    models.EntityTypeModel,
                    models.EntityTypeModel.entity_type_id
                    == models.EntityModel.entity_type_id,
                )
                .order_by(models.EntityModel.entity_id)
                .limit(limit)
                .offset(offset)
            )
            if entity_types:
                query = query.where(
                    models.EntityTypeModel.code.in_(
                        [entity_type.value for entity_type in entity_types]
                    )
                )
            if bbox is not None:
                envelope = func.ST_MakeEnvelope(
                    bbox.min_lon,
                    bbox.min_lat,
                    bbox.max_lon,
                    bbox.max_lat,
                    4326,
                )
                query = query.where(
                    or_(
                        func.ST_Intersects(models.EntityModel.geo_point, envelope),
                        func.ST_Intersects(models.EntityModel.geo_bbox, envelope),
                    )
                )
            result = await session.execute(query)
            rows = result.all()
            if not rows:
                return []
            entity_ids = [row[0] for row in rows]
            alias_rows = await session.execute(
                select(
                    models.EntityAliasModel.entity_id, models.EntityAliasModel.alias
                ).where(models.EntityAliasModel.entity_id.in_(entity_ids))
            )
            evidence_rows = await session.execute(
                select(
                    models.EntityEvidenceModel.entity_id,
                    models.EntityEvidenceModel.evidence_uid,
                ).where(models.EntityEvidenceModel.entity_id.in_(entity_ids))
            )
            alias_map: dict[int, list[str]] = {}
            for entity_id, alias in alias_rows.all():
                alias_map.setdefault(entity_id, []).append(alias)
            evidence_map: dict[int, list[str]] = {}
            for entity_id, evidence_uid in evidence_rows.all():
                evidence_map.setdefault(entity_id, []).append(evidence_uid)
            return [
                Entity(
                    entity_uid=row[1],
                    entity_type=EntityType(row[2]),
                    name=row[3],
                    summary=row[4],
                    attrs=row[5] or {},
                    geo_point=_point_from_wkt(row[6]),
                    geo_bbox=_bbox_from_wkt(row[7]),
                    aliases=alias_map.get(row[0], []),
                    evidence_uids=evidence_map.get(row[0], []),
                )
                for row in rows
            ]

    # =========================================================================
    # 事件操作
    # =========================================================================

    async def store_events(self, events: list[Event]) -> None:
        """写入事件与关联关系。

        Args:
            events: 事件列表
        """
        if not events:
            return
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            event_type_map = await self._ensure_event_types(session)
            entity_uid_set = {
                participant.entity_uid
                for event in events
                for participant in event.participants
            }
            entity_id_map: dict[str, int] = {}
            if entity_uid_set:
                entity_rows = await session.execute(
                    select(
                        models.EntityModel.entity_uid, models.EntityModel.entity_id
                    ).where(models.EntityModel.entity_uid.in_(entity_uid_set))
                )
                entity_id_map = {uid: entity_id for uid, entity_id in entity_rows.all()}
                missing = entity_uid_set - set(entity_id_map.keys())
                if missing:
                    raise ValueError(f"参与方实体不存在: {sorted(missing)}")
            records: list[tuple[Event, models.EventModel]] = []
            for event in events:
                if not event.evidence_uids:
                    raise ValueError(f"事件缺少证据: {event.event_uid}")
                event_type_id = event_type_map.get(event.event_type.value)
                if event_type_id is None:
                    raise ValueError(f"未知事件类型: {event.event_type}")
                record = models.EventModel(
                    event_uid=event.event_uid,
                    event_type_id=event_type_id,
                    summary=event.summary,
                    time_start=event.time_start,
                    time_end=event.time_end,
                    location_name=event.location_name,
                    geo_point=_point_to_wkt(event.geo_point),
                    geo_bbox=_bbox_to_wkt(event.geo_bbox),
                    confidence=event.confidence,
                    tags=event.tags,
                    attrs=event.attrs,
                    created_at=now,
                )
                session.add(record)
                records.append((event, record))
            await session.flush()
            for event, record in records:
                for participant in event.participants:
                    entity_id = entity_id_map.get(participant.entity_uid)
                    if entity_id is None:
                        raise ValueError(f"参与方实体不存在: {participant.entity_uid}")
                    session.add(
                        models.EventParticipantModel(
                            event_id=record.event_id,
                            entity_id=entity_id,
                            role=participant.role,
                        )
                    )
                for evidence_uid in event.evidence_uids:
                    session.add(
                        models.EventEvidenceModel(
                            event_id=record.event_id,
                            evidence_uid=evidence_uid,
                        )
                    )
            await session.commit()

    async def get_event_by_uid(self, event_uid: str) -> Event | None:
        """按 UID 读取事件。

        Args:
            event_uid: 事件 UID

        Returns:
            事件，不存在时返回 None
        """
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    models.EventModel.event_id,
                    models.EventModel.event_uid,
                    models.EventTypeModel.code,
                    models.EventModel.summary,
                    models.EventModel.time_start,
                    models.EventModel.time_end,
                    models.EventModel.location_name,
                    models.EventModel.confidence,
                    models.EventModel.tags,
                    models.EventModel.attrs,
                    func.ST_AsText(models.EventModel.geo_point),
                    func.ST_AsText(models.EventModel.geo_bbox),
                )
                .join(
                    models.EventTypeModel,
                    models.EventTypeModel.event_type_id
                    == models.EventModel.event_type_id,
                )
                .where(models.EventModel.event_uid == event_uid)
            )
            row = result.one_or_none()
            if row is None:
                return None
            event_id = row[0]
            participant_rows = await session.execute(
                select(models.EntityModel.entity_uid, models.EventParticipantModel.role)
                .select_from(models.EventParticipantModel)
                .join(
                    models.EntityModel,
                    models.EntityModel.entity_id
                    == models.EventParticipantModel.entity_id,
                )
                .where(models.EventParticipantModel.event_id == event_id)
            )
            evidence_rows = await session.execute(
                select(models.EventEvidenceModel.evidence_uid).where(
                    models.EventEvidenceModel.event_id == event_id
                )
            )
            return Event(
                event_uid=row[1],
                event_type=EventType(row[2]),
                summary=row[3],
                time_start=row[4],
                time_end=row[5],
                location_name=row[6],
                confidence=row[7],
                tags=row[8] or [],
                attrs=row[9] or {},
                geo_point=_point_from_wkt(row[10]),
                geo_bbox=_bbox_from_wkt(row[11]),
                participants=[
                    EventParticipant(entity_uid=uid, role=role)
                    for uid, role in participant_rows.all()
                ],
                evidence_uids=[evidence for (evidence,) in evidence_rows.all()],
            )

    async def list_events(
        self,
        *,
        event_types: list[EventType] | None,
        time_start: datetime | None,
        time_end: datetime | None,
        bbox: GeoBBox | None,
        limit: int,
        offset: int,
    ) -> list[Event]:
        """按条件查询事件列表。

        Args:
            event_types: 事件类型过滤
            time_start: 时间范围起始过滤
            time_end: 时间范围结束过滤
            bbox: 地理范围过滤
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            事件列表
        """
        async with self.session_factory() as session:
            query = (
                select(
                    models.EventModel.event_id,
                    models.EventModel.event_uid,
                    models.EventTypeModel.code,
                    models.EventModel.summary,
                    models.EventModel.time_start,
                    models.EventModel.time_end,
                    models.EventModel.location_name,
                    models.EventModel.confidence,
                    models.EventModel.tags,
                    models.EventModel.attrs,
                    func.ST_AsText(models.EventModel.geo_point),
                    func.ST_AsText(models.EventModel.geo_bbox),
                )
                .join(
                    models.EventTypeModel,
                    models.EventTypeModel.event_type_id
                    == models.EventModel.event_type_id,
                )
                .order_by(models.EventModel.event_id)
                .limit(limit)
                .offset(offset)
            )
            if event_types:
                query = query.where(
                    models.EventTypeModel.code.in_(
                        [event_type.value for event_type in event_types]
                    )
                )
            if time_start or time_end:
                query = query.where(
                    or_(
                        models.EventModel.time_start.is_not(None),
                        models.EventModel.time_end.is_not(None),
                    )
                )
            if time_start is not None:
                query = query.where(
                    or_(
                        models.EventModel.time_end.is_(None),
                        models.EventModel.time_end >= time_start,
                    )
                )
            if time_end is not None:
                query = query.where(
                    or_(
                        models.EventModel.time_start.is_(None),
                        models.EventModel.time_start <= time_end,
                    )
                )
            if bbox is not None:
                envelope = func.ST_MakeEnvelope(
                    bbox.min_lon,
                    bbox.min_lat,
                    bbox.max_lon,
                    bbox.max_lat,
                    4326,
                )
                query = query.where(
                    or_(
                        func.ST_Intersects(models.EventModel.geo_point, envelope),
                        func.ST_Intersects(models.EventModel.geo_bbox, envelope),
                    )
                )
            result = await session.execute(query)
            rows = result.all()
            if not rows:
                return []
            event_ids = [row[0] for row in rows]
            participant_rows = await session.execute(
                select(
                    models.EventParticipantModel.event_id,
                    models.EntityModel.entity_uid,
                    models.EventParticipantModel.role,
                )
                .select_from(models.EventParticipantModel)
                .join(
                    models.EntityModel,
                    models.EntityModel.entity_id
                    == models.EventParticipantModel.entity_id,
                )
                .where(models.EventParticipantModel.event_id.in_(event_ids))
            )
            evidence_rows = await session.execute(
                select(
                    models.EventEvidenceModel.event_id,
                    models.EventEvidenceModel.evidence_uid,
                ).where(models.EventEvidenceModel.event_id.in_(event_ids))
            )
            participant_map: dict[int, list[EventParticipant]] = {}
            for event_id, entity_uid, role in participant_rows.all():
                participant_map.setdefault(event_id, []).append(
                    EventParticipant(entity_uid=entity_uid, role=role)
                )
            evidence_map: dict[int, list[str]] = {}
            for event_id, evidence_uid in evidence_rows.all():
                evidence_map.setdefault(event_id, []).append(evidence_uid)
            return [
                Event(
                    event_uid=row[1],
                    event_type=EventType(row[2]),
                    summary=row[3],
                    time_start=row[4],
                    time_end=row[5],
                    location_name=row[6],
                    confidence=row[7],
                    tags=row[8] or [],
                    attrs=row[9] or {},
                    geo_point=_point_from_wkt(row[10]),
                    geo_bbox=_bbox_from_wkt(row[11]),
                    participants=participant_map.get(row[0], []),
                    evidence_uids=evidence_map.get(row[0], []),
                )
                for row in rows
            ]

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def _ensure_entity_types(self, session: AsyncSession) -> dict[str, int]:
        """确保实体类型已登记。"""
        payload = [
            {"code": entity_type.value, "description": None}
            for entity_type in EntityType
        ]
        await session.execute(
            insert(models.EntityTypeModel)
            .values(payload)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        result = await session.execute(
            select(models.EntityTypeModel.code, models.EntityTypeModel.entity_type_id)
        )
        return {code: entity_type_id for code, entity_type_id in result.all()}

    async def _ensure_event_types(self, session: AsyncSession) -> dict[str, int]:
        """确保事件类型已登记。"""
        payload = [
            {"code": event_type.value, "description": None} for event_type in EventType
        ]
        await session.execute(
            insert(models.EventTypeModel)
            .values(payload)
            .on_conflict_do_nothing(index_elements=["code"])
        )
        result = await session.execute(
            select(models.EventTypeModel.code, models.EventTypeModel.event_type_id)
        )
        return {code: event_type_id for code, event_type_id in result.all()}
