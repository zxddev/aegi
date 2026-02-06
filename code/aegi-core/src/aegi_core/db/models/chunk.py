from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Chunk(Base):
    __tablename__ = "chunks"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    artifact_version_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text(), nullable=False)

    anchor_set: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    anchor_health: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
