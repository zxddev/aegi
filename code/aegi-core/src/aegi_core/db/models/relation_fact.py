# Author: msq
"""RelationFact 权威关系模型。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class RelationFact(Base):
    __tablename__ = "relation_facts"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_entity_uid: Mapped[str] = mapped_column(
        sa.String(64), index=True, nullable=False
    )
    target_entity_uid: Mapped[str] = mapped_column(
        sa.String(64), index=True, nullable=False
    )
    relation_type: Mapped[str] = mapped_column(
        sa.String(64), index=True, nullable=False
    )

    supporting_source_claim_uids: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )
    evidence_strength: Mapped[float] = mapped_column(
        sa.Float, default=0.0, nullable=False
    )
    assessed_by: Mapped[str] = mapped_column(
        sa.String(16), default="llm", nullable=False
    )

    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    conflicts_with: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    conflict_resolution: Mapped[str | None] = mapped_column(sa.Text)

    confidence: Mapped[float] = mapped_column(sa.Float, default=0.5, nullable=False)

    created_by_action_uid: Mapped[str | None] = mapped_column(
        sa.String(64),
        sa.ForeignKey("actions.uid", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
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
