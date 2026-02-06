from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class Evidence(Base):
    __tablename__ = "evidence"

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

    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    license_note: Mapped[str | None] = mapped_column(sa.Text())

    pii_flags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    retention_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
