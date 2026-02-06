from __future__ import annotations

# Author: msq

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Action(Base):
    __tablename__ = "actions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(sa.Text())
    rationale: Mapped[str | None] = mapped_column(sa.Text())

    inputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))
    span_id: Mapped[str | None] = mapped_column(sa.String(64))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
