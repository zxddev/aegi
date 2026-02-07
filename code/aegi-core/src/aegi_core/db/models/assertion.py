from __future__ import annotations

# Author: msq

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Assertion(Base):
    __tablename__ = "assertions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_claim_uids: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(sa.Float())
    modality: Mapped[str | None] = mapped_column(sa.String(32))
    segment_ref: Mapped[str | None] = mapped_column(sa.String(128))
    media_time_range: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
