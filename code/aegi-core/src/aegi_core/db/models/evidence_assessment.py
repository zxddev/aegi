"""EvidenceAssessment DB model — LLM/expert judgment of evidence vs hypothesis."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class EvidenceAssessment(Base):
    __tablename__ = "evidence_assessments"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    hypothesis_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evidence_uid: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        index=True,
        comment="指向 assertion.uid 或 source_claim.uid",
    )
    evidence_type: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default="assertion",
        comment="assertion | source_claim",
    )
    relation: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        comment="support | contradict | irrelevant",
    )
    strength: Mapped[float] = mapped_column(
        sa.Float(),
        nullable=False,
        comment="LLM 给出的强度 0.0~1.0",
    )
    likelihood: Mapped[float] = mapped_column(
        sa.Float(),
        nullable=False,
        comment="转换后的 P(E|H)",
    )
    assessed_by: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        default="llm",
        comment="llm | expert",
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    __table_args__ = (
        sa.Index("ix_ea_hyp_evidence", "hypothesis_uid", "evidence_uid"),
        sa.UniqueConstraint(
            "hypothesis_uid", "evidence_uid", name="uq_ea_hyp_evidence"
        ),
    )
