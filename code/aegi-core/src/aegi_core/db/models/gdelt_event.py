# Author: msq
"""GDELT 事件模型，存储从 GDELT DOC API 拉取的文章元数据。"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegi_core.db.base import Base
from aegi_core.db.utils import utcnow


class GdeltEvent(Base):
    __tablename__ = "gdelt_events"

    uid: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    gdelt_id: Mapped[str] = mapped_column(sa.String(128), unique=True, nullable=False)
    case_uid: Mapped[str | None] = mapped_column(
        sa.String(64),
        sa.ForeignKey("cases.uid", ondelete="SET NULL"),
        nullable=True,
    )

    # 核心字段
    title: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    url: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    source_domain: Mapped[str] = mapped_column(
        sa.String(256), nullable=False, default=""
    )
    language: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    # CAMEO 字段（Phase 1 全 nullable，后续 Events CSV 接入时填充）
    cameo_code: Mapped[str | None] = mapped_column(sa.String(16))
    cameo_root: Mapped[str | None] = mapped_column(sa.String(8))
    goldstein_scale: Mapped[float | None] = mapped_column(sa.Float())

    # Actor 字段
    actor1: Mapped[str | None] = mapped_column(sa.String(256))
    actor2: Mapped[str | None] = mapped_column(sa.String(256))
    actor1_country: Mapped[str | None] = mapped_column(sa.String(8))
    actor2_country: Mapped[str | None] = mapped_column(sa.String(8))

    # Geo 字段
    geo_lat: Mapped[float | None] = mapped_column(sa.Float())
    geo_lon: Mapped[float | None] = mapped_column(sa.Float())
    geo_country: Mapped[str | None] = mapped_column(sa.String(8))
    geo_name: Mapped[str | None] = mapped_column(sa.String(256))

    tone: Mapped[float | None] = mapped_column(sa.Float())

    # new | ingested | skipped | error
    status: Mapped[str] = mapped_column(sa.String(16), default="new", nullable=False)

    matched_subscription_uids: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False
    )
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        sa.Index("ix_gdelt_country_cameo", "geo_country", "cameo_root"),
        sa.Index("ix_gdelt_published", "published_at"),
        sa.Index("ix_gdelt_status", "status"),
    )
