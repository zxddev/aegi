# Author: msq
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    query: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    categories: Mapped[str] = mapped_column(
        sa.String(64), default="general", nullable=False
    )
    language: Mapped[str] = mapped_column(
        sa.String(16), default="zh-CN", nullable=False
    )
    max_results: Mapped[int] = mapped_column(sa.Integer(), default=10, nullable=False)

    status: Mapped[str] = mapped_column(
        sa.String(16), default="pending", nullable=False
    )  # pending | running | completed | failed | cancelled
    error: Mapped[str | None] = mapped_column(sa.Text())

    # Result stats
    urls_found: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)
    urls_ingested: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)
    urls_deduped: Mapped[int] = mapped_column(sa.Integer(), default=0, nullable=False)
    claims_extracted: Mapped[int] = mapped_column(
        sa.Integer(), default=0, nullable=False
    )
    result_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Scheduling (null = one-shot)
    cron_expression: Mapped[str | None] = mapped_column(sa.String(64))
    next_run_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
