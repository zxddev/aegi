"""ProbabilityUpdate DB model — audit trail for Bayesian probability updates."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class ProbabilityUpdate(Base):
    __tablename__ = "probability_updates"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    hypothesis_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evidence_uid: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    prior: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    posterior: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    likelihood: Mapped[float] = mapped_column(sa.Float(), nullable=False)
    likelihood_ratio: Mapped[float | None] = mapped_column(sa.Float())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
