# Author: msq
"""Narrative ORM model.

Source: openspec/changes/narrative-intelligence-detection/design.md
Evidence: Narrative <-> SourceClaim many-to-many; theme + time range required.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Narrative(Base):
    __tablename__ = "narratives"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    theme: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    source_claim_uids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    latest_seen_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
