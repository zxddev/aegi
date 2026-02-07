# Author: msq
"""Ontology 版本与 case pin 持久化模型。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class OntologyVersionRow(Base):
    __tablename__ = "ontology_versions"

    version: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    entity_types: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    event_types: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    relation_types: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )


class CasePinRow(Base):
    __tablename__ = "case_ontology_pins"

    case_uid: Mapped[str] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    ontology_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    pinned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )
