# Author: msq
"""RelationFact 权威层服务。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.relation_fact import RelationFact
from aegi_core.db.utils import utcnow
from aegi_core.services.ontology_versioning import (
    get_version,
    get_version_db,
    validate_against_ontology,
)


_CONFLICT_RELATIONS: dict[str, set[str]] = {
    "ALLIED_WITH": {"HOSTILE_TO"},
    "HOSTILE_TO": {"ALLIED_WITH", "COOPERATES_WITH"},
    "COOPERATES_WITH": {"HOSTILE_TO"},
}


class RelationFactCreate(BaseModel):
    case_uid: str
    source_entity_uid: str
    target_entity_uid: str
    relation_type: str
    ontology_version: str
    source_entity_type: str | None = None
    target_entity_type: str | None = None
    supporting_source_claim_uids: list[str] = Field(default_factory=list)
    assessed_by: str = "llm"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    conflict_resolution: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    created_by_action_uid: str | None = None
    properties: dict = Field(default_factory=dict)


class RelationFactUpdate(BaseModel):
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    conflict_resolution: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_strength: float | None = Field(default=None, ge=0.0, le=1.0)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i for i in items if i))


class RelationFactService:
    """RelationFact CRUD、冲突检测和证据强度计算。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def is_conflicting_relation(existing_type: str, new_type: str) -> bool:
        if existing_type == new_type:
            return False
        conflicts = _CONFLICT_RELATIONS.get(existing_type, set())
        if new_type in conflicts:
            return True
        reverse_conflicts = _CONFLICT_RELATIONS.get(new_type, set())
        return existing_type in reverse_conflicts

    @staticmethod
    def calculate_evidence_strength(
        source_claim_uids: list[str],
        confidence: float,
    ) -> float:
        """根据证据数量与置信度计算证据强度。"""
        quantity_score = min(len(_unique(source_claim_uids)), 5) / 5
        quality_score = max(0.0, min(1.0, confidence))
        return round((0.4 * quantity_score) + (0.6 * quality_score), 3)

    async def detect_conflicts(
        self,
        *,
        case_uid: str,
        source_entity_uid: str,
        target_entity_uid: str,
        relation_type: str,
    ) -> list[str]:
        rows = (
            (
                await self._session.execute(
                    sa.select(RelationFact).where(
                        RelationFact.case_uid == case_uid,
                        RelationFact.source_entity_uid == source_entity_uid,
                        RelationFact.target_entity_uid == target_entity_uid,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [
            row.uid
            for row in rows
            if self.is_conflicting_relation(row.relation_type, relation_type)
        ]

    async def create(self, payload: RelationFactCreate) -> RelationFact:
        ontology = get_version(payload.ontology_version)
        if ontology is None:
            ontology = await get_version_db(payload.ontology_version, self._session)
        if ontology is None:
            raise ValueError(f"Ontology version not found: {payload.ontology_version}")

        error = validate_against_ontology(
            {
                "relation_type": payload.relation_type,
                "properties": payload.properties,
            },
            ontology,
            source_entity=(
                {"entity_type": payload.source_entity_type}
                if payload.source_entity_type
                else None
            ),
            target_entity=(
                {"entity_type": payload.target_entity_type}
                if payload.target_entity_type
                else None
            ),
        )
        if error is not None:
            raise ValueError(error.detail or "ontology relation validation failed")

        conflict_uids = await self.detect_conflicts(
            case_uid=payload.case_uid,
            source_entity_uid=payload.source_entity_uid,
            target_entity_uid=payload.target_entity_uid,
            relation_type=payload.relation_type,
        )

        evidence_strength = payload.evidence_strength
        if evidence_strength is None:
            evidence_strength = self.calculate_evidence_strength(
                payload.supporting_source_claim_uids,
                payload.confidence,
            )

        now = utcnow()
        row = RelationFact(
            uid=f"rf_{uuid4().hex}",
            case_uid=payload.case_uid,
            source_entity_uid=payload.source_entity_uid,
            target_entity_uid=payload.target_entity_uid,
            relation_type=payload.relation_type,
            supporting_source_claim_uids=_unique(payload.supporting_source_claim_uids),
            evidence_strength=evidence_strength,
            assessed_by=payload.assessed_by,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            conflicts_with=_unique(conflict_uids),
            conflict_resolution=payload.conflict_resolution,
            confidence=payload.confidence,
            created_by_action_uid=payload.created_by_action_uid,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()

        if conflict_uids:
            conflict_rows = (
                (
                    await self._session.execute(
                        sa.select(RelationFact).where(
                            RelationFact.uid.in_(conflict_uids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for conflict_row in conflict_rows:
                conflict_row.conflicts_with = _unique(
                    [*conflict_row.conflicts_with, row.uid]
                )

        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def get(self, uid: str) -> RelationFact | None:
        return await self._session.get(RelationFact, uid)

    async def list_by_case(
        self, case_uid: str, *, limit: int = 100
    ) -> list[RelationFact]:
        return (
            (
                await self._session.execute(
                    sa.select(RelationFact)
                    .where(RelationFact.case_uid == case_uid)
                    .order_by(RelationFact.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def update(self, uid: str, payload: RelationFactUpdate) -> RelationFact:
        row = await self._session.get(RelationFact, uid)
        if row is None:
            raise ValueError(f"RelationFact not found: {uid}")

        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = utcnow()

        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def delete(self, uid: str) -> None:
        row = await self._session.get(RelationFact, uid)
        if row is None:
            return
        await self._session.delete(row)
        await self._session.commit()
