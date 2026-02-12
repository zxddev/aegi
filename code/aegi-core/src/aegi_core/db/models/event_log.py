"""EventLog model for event-driven layer audit trail."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class EventLog(Base):
    __tablename__ = "event_log"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(sa.String(64), index=True, nullable=False)
    case_uid: Mapped[str | None] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="SET NULL"),
        index=True,
    )

    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    entities: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), default=list, nullable=False
    )
    regions: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), default=list, nullable=False
    )
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text()), default=list, nullable=False
    )

    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(
        sa.String(16), default="medium", nullable=False
    )
    # 去重标识（同一 source_event_uid 不重复处理）
    source_event_uid: Mapped[str] = mapped_column(
        sa.String(128), unique=True, nullable=False
    )

    # 处理状态：pending | processing | done | failed
    status: Mapped[str] = mapped_column(
        sa.String(16), default="pending", nullable=False
    )
    push_count: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
