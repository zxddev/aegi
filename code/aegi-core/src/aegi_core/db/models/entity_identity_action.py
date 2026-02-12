# Author: msq
"""实体身份版本化动作模型。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class EntityIdentityAction(Base):
    __tablename__ = "entity_identity_actions"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    entity_uids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    result_entity_uid: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    performed_by: Mapped[str] = mapped_column(sa.String(16), nullable=False)

    approved: Mapped[bool] = mapped_column(sa.Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(16), default="pending", nullable=False
    )
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_by_action_uid: Mapped[str | None] = mapped_column(
        sa.String(64),
        sa.ForeignKey("actions.uid", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
