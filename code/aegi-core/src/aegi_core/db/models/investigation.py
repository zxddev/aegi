# Author: msq
"""Investigation model for autonomous hypothesis-driven research loops."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Investigation(Base):
    __tablename__ = "investigations"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    trigger_event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    trigger_event_uid: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(16), default="running", nullable=False
    )  # running | completed | failed | cancelled

    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    rounds: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    total_claims_extracted: Mapped[int] = mapped_column(
        sa.Integer(), default=0, nullable=False
    )
    gap_resolved: Mapped[bool] = mapped_column(
        sa.Boolean(), default=False, nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(sa.String(128))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
