# Author: msq
"""分析师对 Assertion 的反馈记录。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class AssertionFeedback(Base):
    __tablename__ = "assertion_feedback"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    assertion_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("assertions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)

    # agree | disagree | need_more_evidence | partially_agree
    verdict: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    confidence_override: Mapped[float | None] = mapped_column(sa.Float())
    comment: Mapped[str | None] = mapped_column(sa.Text())
    suggested_value: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id",
            "assertion_uid",
            name="uq_feedback_user_assertion",
        ),
        sa.Index("ix_feedback_user_assertion", "user_id", "assertion_uid"),
        sa.Index("ix_feedback_case_assertion", "case_uid", "assertion_uid"),
    )
