# Author: msq
"""Hypothesis DB model – reuses foundation HypothesisV1 contract fields.

Source: openspec/changes/ach-hypothesis-analysis/tasks.md (1.1)
Evidence: No private schema; columns mirror HypothesisV1 contract.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    supporting_assertion_uids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    contradicting_assertion_uids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    coverage_score: Mapped[float | None] = mapped_column(sa.Float())
    confidence: Mapped[float | None] = mapped_column(sa.Float())
    gap_list: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    adversarial_result: Mapped[dict | None] = mapped_column(JSONB)
    trace_id: Mapped[str | None] = mapped_column(sa.String(64))
    prompt_version: Mapped[str | None] = mapped_column(sa.String(64))
    modality: Mapped[str | None] = mapped_column(sa.String(32))
    segment_ref: Mapped[str | None] = mapped_column(sa.String(128))
    media_time_range: Mapped[dict | None] = mapped_column(JSONB)

    prior_probability: Mapped[float | None] = mapped_column(
        sa.Float(), default=None, comment="先验概率（初始 = 1/N）"
    )
    posterior_probability: Mapped[float | None] = mapped_column(
        sa.Float(), default=None, comment="当前后验概率"
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
