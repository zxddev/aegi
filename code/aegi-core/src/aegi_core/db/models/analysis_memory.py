# Author: msq
"""AnalysisMemory 持久化记录。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class AnalysisMemoryRecord(Base):
    __tablename__ = "analysis_memory"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    scenario_summary: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    hypotheses: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    key_evidence: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    conclusion: Mapped[str] = mapped_column(sa.Text(), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(sa.Float(), nullable=False, default=0.0)

    outcome: Mapped[str | None] = mapped_column(sa.Text())
    prediction_accuracy: Mapped[float | None] = mapped_column(sa.Float())
    lessons_learned: Mapped[str | None] = mapped_column(sa.Text())
    pattern_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

