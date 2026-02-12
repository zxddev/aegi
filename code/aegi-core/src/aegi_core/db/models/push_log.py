"""PushLog model for event-driven push audit trail."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class PushLog(Base):
    __tablename__ = "push_log"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    event_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("event_log.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(sa.String(128), index=True, nullable=False)
    subscription_uid: Mapped[str | None] = mapped_column(sa.String(64))

    # rule | semantic | llm
    match_method: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    match_score: Mapped[float] = mapped_column(sa.Float(), default=1.0, nullable=False)
    match_reason: Mapped[str | None] = mapped_column(sa.Text())

    # delivered | throttled | failed
    status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text())

    # 用户反馈：null=未反馈, true=有用, false=没用
    feedback: Mapped[bool | None] = mapped_column(sa.Boolean())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
