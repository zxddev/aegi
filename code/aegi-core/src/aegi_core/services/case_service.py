# Author: msq
from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.errors import not_found
from aegi_core.db.models.action import Action
from aegi_core.db.models.artifact import ArtifactVersion
from aegi_core.db.models.case import Case


async def create_case(
    session: AsyncSession,
    *,
    title: str,
    actor_id: str | None,
    rationale: str | None,
    inputs: dict,
) -> dict:
    """创建 Case 记录及对应 Action，返回响应字典。"""
    case_uid = f"case_{uuid4().hex}"
    action_uid = f"act_{uuid4().hex}"

    case = Case(uid=case_uid, title=title)
    action = Action(
        uid=action_uid,
        case_uid=case_uid,
        action_type="case.create",
        actor_id=actor_id,
        rationale=rationale,
        inputs=inputs,
        outputs={"case_uid": case_uid},
    )

    session.add(case)
    await session.flush()
    session.add(action)
    await session.commit()

    return {"case_uid": case_uid, "title": title, "action_uid": action_uid}


async def get_case(session: AsyncSession, *, case_uid: str) -> dict:
    """按 uid 查询 Case，不存在则抛 404。"""
    case = await session.get(Case, case_uid)
    if case is None:
        raise not_found("Case", case_uid)
    return {"case_uid": case.uid, "title": case.title}


async def list_case_artifacts(session: AsyncSession, *, case_uid: str) -> dict:
    """列出 Case 下所有 ArtifactVersion。"""
    result = await session.execute(
        sa.select(ArtifactVersion).where(ArtifactVersion.case_uid == case_uid)
    )
    items = [
        {
            "artifact_version_uid": av.uid,
            "content_sha256": av.content_sha256,
            "storage_ref": av.storage_ref,
        }
        for av in result.scalars().all()
    ]
    return {"items": items}
