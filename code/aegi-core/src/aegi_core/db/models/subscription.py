"""Subscription model for event-driven push notifications."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Subscription(Base):
    __tablename__ = "subscriptions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(128), index=True, nullable=False)

    # case | entity | region | topic | global
    sub_type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # 具体目标：case_uid / entity_uid / region_code / topic_tag / "*"
    sub_target: Mapped[str] = mapped_column(sa.String(256), nullable=False, default="*")

    # 只接收 >= 该优先级的事件（low=0, medium=1, high=2, critical=3）
    priority_threshold: Mapped[int] = mapped_column(
        sa.Integer(), default=0, nullable=False
    )

    # 事件类型过滤（空 = 全部）
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), default=list, nullable=False
    )
    # GDELT 等上游的匹配规则，如 {"keywords": [...], "countries": [...]}
    match_rules: Mapped[dict[str, list[str]]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    enabled: Mapped[bool] = mapped_column(sa.Boolean(), default=True, nullable=False)

    # 专家兴趣描述（用于生成 embedding）
    interest_text: Mapped[str | None] = mapped_column(sa.Text())
    # 兴趣 embedding 是否已同步到 Qdrant
    embedding_synced: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (sa.Index("ix_sub_type_target", "sub_type", "sub_target"),)
