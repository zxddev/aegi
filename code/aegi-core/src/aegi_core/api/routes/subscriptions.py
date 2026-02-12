"""订阅 CRUD API 路由。"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aegi_core.api.deps import get_db_session
from aegi_core.api.errors import AegiHTTPError
from aegi_core.db.models.subscription import Subscription

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# ── Schema ───────────────────────────────────────────────────────


class CreateSubscriptionRequest(BaseModel):
    user_id: str
    sub_type: str = Field(..., pattern="^(case|entity|region|topic|global)$")
    sub_target: str = "*"
    priority_threshold: int = Field(default=0, ge=0, le=3)
    event_types: list[str] = Field(default_factory=list)
    match_rules: dict[str, list[str]] = Field(default_factory=dict)
    interest_text: str | None = None


class PatchSubscriptionRequest(BaseModel):
    sub_target: str | None = None
    priority_threshold: int | None = Field(default=None, ge=0, le=3)
    event_types: list[str] | None = None
    match_rules: dict[str, list[str]] | None = None
    enabled: bool | None = None
    interest_text: str | None = None


class SubscriptionResponse(BaseModel):
    uid: str
    user_id: str
    sub_type: str
    sub_target: str
    priority_threshold: int
    event_types: list[str]
    match_rules: dict[str, list[str]] = Field(default_factory=dict)
    enabled: bool
    interest_text: str | None = None
    embedding_synced: bool
    created_at: str | None = None
    updated_at: str | None = None


class PaginatedSubscriptions(BaseModel):
    items: list[SubscriptionResponse]
    total: int


def _sub_to_response(sub: Subscription) -> SubscriptionResponse:
    raw_match_rules = getattr(sub, "match_rules", {})
    match_rules = raw_match_rules if isinstance(raw_match_rules, dict) else {}
    return SubscriptionResponse(
        uid=sub.uid,
        user_id=sub.user_id,
        sub_type=sub.sub_type,
        sub_target=sub.sub_target,
        priority_threshold=sub.priority_threshold,
        event_types=sub.event_types or [],
        match_rules=match_rules,
        enabled=sub.enabled,
        interest_text=sub.interest_text,
        embedding_synced=sub.embedding_synced,
        created_at=sub.created_at.isoformat() if sub.created_at else None,
        updated_at=sub.updated_at.isoformat() if sub.updated_at else None,
    )


# ── 端点 ─────────────────────────────────────────────────────


@router.post("", response_model=SubscriptionResponse)
async def create_subscription(
    body: CreateSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    sub = Subscription(
        uid=f"sub_{uuid4().hex}",
        user_id=body.user_id,
        sub_type=body.sub_type,
        sub_target=body.sub_target,
        priority_threshold=body.priority_threshold,
        event_types=body.event_types,
        match_rules=body.match_rules,
        interest_text=body.interest_text,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return _sub_to_response(sub)


@router.get("", response_model=PaginatedSubscriptions)
async def list_subscriptions(
    user_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedSubscriptions:
    base = sa.select(Subscription)
    count_base = sa.select(sa.func.count()).select_from(Subscription)
    if user_id:
        base = base.where(Subscription.user_id == user_id)
        count_base = count_base.where(Subscription.user_id == user_id)

    total = (await session.execute(count_base)).scalar() or 0
    rows = (
        (
            await session.execute(
                base.order_by(Subscription.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return PaginatedSubscriptions(
        items=[_sub_to_response(r) for r in rows],
        total=total,
    )


@router.get("/{sub_uid}", response_model=SubscriptionResponse)
async def get_subscription(
    sub_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    sub = (
        await session.execute(
            sa.select(Subscription).where(Subscription.uid == sub_uid)
        )
    ).scalar_one_or_none()
    if not sub:
        raise AegiHTTPError(404, "not_found", f"Subscription {sub_uid} not found", {})
    return _sub_to_response(sub)


@router.patch("/{sub_uid}", response_model=SubscriptionResponse)
async def patch_subscription(
    sub_uid: str,
    body: PatchSubscriptionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionResponse:
    sub = (
        await session.execute(
            sa.select(Subscription).where(Subscription.uid == sub_uid)
        )
    ).scalar_one_or_none()
    if not sub:
        raise AegiHTTPError(404, "not_found", f"Subscription {sub_uid} not found", {})

    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(sub, field_name, value)
        if field_name == "interest_text":
            sub.embedding_synced = False

    await session.commit()
    await session.refresh(sub)
    return _sub_to_response(sub)


@router.delete("/{sub_uid}")
async def delete_subscription(
    sub_uid: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    sub = (
        await session.execute(
            sa.select(Subscription).where(Subscription.uid == sub_uid)
        )
    ).scalar_one_or_none()
    if not sub:
        raise AegiHTTPError(404, "not_found", f"Subscription {sub_uid} not found", {})
    await session.delete(sub)
    await session.commit()
    return {"status": "deleted"}
