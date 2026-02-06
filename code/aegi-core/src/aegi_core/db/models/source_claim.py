from __future__ import annotations

# Author: msq

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class SourceClaim(Base):
    __tablename__ = "source_claims"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    artifact_version_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("chunks.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evidence_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("evidence.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    quote: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    selectors: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)

    attributed_to: Mapped[str | None] = mapped_column(sa.Text())
    modality: Mapped[str | None] = mapped_column(sa.String(32))
    segment_ref: Mapped[str | None] = mapped_column(sa.String(128))
    media_time_range: Mapped[dict | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(sa.String(16))
    original_quote: Mapped[str | None] = mapped_column(sa.Text())
    translation: Mapped[str | None] = mapped_column(sa.Text())
    translation_meta: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
