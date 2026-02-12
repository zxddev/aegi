# Author: msq
"""实体身份审批队列 API。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session, get_neo4j_store
from aegi_core.api.errors import not_found
from aegi_core.db.models.action import Action
from aegi_core.db.models.entity_identity_action import EntityIdentityAction
from aegi_core.infra.neo4j_store import Neo4jStore
from aegi_core.services.entity_identity_service import (
    approve_identity_action,
    list_pending_identity_actions,
    reject_identity_action,
)

router = APIRouter(prefix="/api/entity-identity", tags=["entity-identity"])


class ApproveIdentityRequest(BaseModel):
    approved_by: str = Field(min_length=1)


class RejectIdentityRequest(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str | None = None


def _to_payload(row: EntityIdentityAction) -> dict:
    return {
        "uid": row.uid,
        "case_uid": row.case_uid,
        "action_type": row.action_type,
        "entity_uids": row.entity_uids,
        "result_entity_uid": row.result_entity_uid,
        "reason": row.reason,
        "performed_by": row.performed_by,
        "approved": row.approved,
        "approved_by": row.approved_by,
        "status": row.status,
        "rejection_reason": row.rejection_reason,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/pending")
async def pending_identity_actions(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = await list_pending_identity_actions(session, limit=limit)
    return {"items": [_to_payload(row) for row in rows], "total": len(rows)}


@router.post("/{uid}/approve")
async def approve_identity(
    uid: str,
    body: ApproveIdentityRequest,
    session: AsyncSession = Depends(get_db_session),
    neo4j: Neo4jStore = Depends(get_neo4j_store),
) -> dict:
    try:
        row = await approve_identity_action(session, uid, approved_by=body.approved_by)
    except ValueError:
        raise not_found("EntityIdentityAction", uid)

    # 审批通过后执行 merge 投影。
    if row.action_type == "merge":
        aliases = [euid for euid in row.entity_uids if euid != row.result_entity_uid]
        if aliases:
            await neo4j.upsert_edges(
                "Entity",
                "Entity",
                "SAME_AS",
                [
                    {
                        "source_uid": row.result_entity_uid,
                        "target_uid": alias_uid,
                        "properties": {
                            "identity_action_uid": row.uid,
                            "approved_by": body.approved_by,
                        },
                    }
                    for alias_uid in aliases
                ],
            )

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=row.case_uid,
            action_type="entity_identity.approve",
            inputs={"entity_identity_action_uid": uid, "approved_by": body.approved_by},
            outputs={"status": row.status, "approved": row.approved},
            trace_id=uuid4().hex,
        )
    )
    await session.commit()

    return {"item": _to_payload(row), "action_uid": action_uid}


@router.post("/{uid}/reject")
async def reject_identity(
    uid: str,
    body: RejectIdentityRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        row = await reject_identity_action(
            session,
            uid,
            rejected_by=body.rejected_by,
            reason=body.reason,
        )
    except ValueError:
        raise not_found("EntityIdentityAction", uid)

    action_uid = f"act_{uuid4().hex}"
    session.add(
        Action(
            uid=action_uid,
            case_uid=row.case_uid,
            action_type="entity_identity.reject",
            inputs={
                "entity_identity_action_uid": uid,
                "rejected_by": body.rejected_by,
                "reason": body.reason,
            },
            outputs={"status": row.status, "approved": row.approved},
            trace_id=uuid4().hex,
        )
    )
    await session.commit()

    return {"item": _to_payload(row), "action_uid": action_uid}
