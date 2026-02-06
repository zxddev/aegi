from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class ArtifactIdentity(Base):
    __tablename__ = "artifact_identities"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(sa.Text())

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    artifact_identity_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("artifact_identities.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    retrieved_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    storage_ref: Mapped[str | None] = mapped_column(sa.Text())
    content_sha256: Mapped[str | None] = mapped_column(sa.String(64))
    content_type: Mapped[str | None] = mapped_column(sa.Text())
    source_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
