from __future__ import annotations

# Author: msq

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class ToolTrace(Base):
    __tablename__ = "tool_traces"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("actions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    tool_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error: Mapped[str | None] = mapped_column(sa.Text())
    policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))
    span_id: Mapped[str | None] = mapped_column(sa.String(64))


    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
