# Author: msq
"""实体身份动作服务。"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.db.models.entity_identity_action import EntityIdentityAction
from aegi_core.db.utils import utcnow


class EntityIdentityActionCreate(BaseModel):
    case_uid: str
    action_type: str = Field(pattern="^(merge|split|create|alias_add|alias_remove)$")
    entity_uids: list[str] = Field(default_factory=list)
    result_entity_uid: str
    reason: str
    performed_by: str = "llm"
    approved: bool = False
    approved_by: str | None = None
    created_by_action_uid: str | None = None


class EntityIdentityActionUpdateDecision(BaseModel):
    reviewer: str
    reason: str | None = None


def _unique_uids(uids: list[str]) -> list[str]:
    return list(dict.fromkeys(uid for uid in uids if uid))


async def create_identity_action(
    session: AsyncSession,
    payload: EntityIdentityActionCreate,
) -> EntityIdentityAction:
    now = utcnow()
    row = EntityIdentityAction(
        uid=f"eia_{uuid4().hex}",
        case_uid=payload.case_uid,
        action_type=payload.action_type,
        entity_uids=_unique_uids(payload.entity_uids),
        result_entity_uid=payload.result_entity_uid,
        reason=payload.reason,
        performed_by=payload.performed_by,
        approved=payload.approved,
        approved_by=payload.approved_by,
        status="approved" if payload.approved else "pending",
        rejection_reason=None,
        created_by_action_uid=payload.created_by_action_uid,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_identity_action(
    session: AsyncSession,
    uid: str,
) -> EntityIdentityAction | None:
    return await session.get(EntityIdentityAction, uid)


async def list_pending_identity_actions(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[EntityIdentityAction]:
    return (
        (
            await session.execute(
                sa.select(EntityIdentityAction)
                .where(EntityIdentityAction.status == "pending")
                .order_by(EntityIdentityAction.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def approve_identity_action(
    session: AsyncSession,
    uid: str,
    *,
    approved_by: str,
) -> EntityIdentityAction:
    row = await get_identity_action(session, uid)
    if row is None:
        raise ValueError(f"EntityIdentityAction not found: {uid}")

    row.approved = True
    row.approved_by = approved_by
    row.status = "approved"
    row.rejection_reason = None
    row.updated_at = utcnow()

    await session.commit()
    await session.refresh(row)
    return row


async def reject_identity_action(
    session: AsyncSession,
    uid: str,
    *,
    rejected_by: str,
    reason: str | None,
) -> EntityIdentityAction:
    row = await get_identity_action(session, uid)
    if row is None:
        raise ValueError(f"EntityIdentityAction not found: {uid}")

    row.approved = False
    row.approved_by = rejected_by
    row.status = "rejected"
    row.rejection_reason = reason
    row.updated_at = utcnow()

    await session.commit()
    await session.refresh(row)
    return row


async def rollback_identity_action(
    session: AsyncSession,
    action_uid: str,
) -> EntityIdentityAction:
    row = await get_identity_action(session, action_uid)
    if row is None:
        raise ValueError(f"EntityIdentityAction not found: {action_uid}")
    if row.action_type not in {"merge", "split"}:
        raise ValueError("rollback_identity_action only supports merge/split actions")

    row.status = "rolled_back"
    row.updated_at = utcnow()

    await session.commit()
    await session.refresh(row)
    return row
