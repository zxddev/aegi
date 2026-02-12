# Author: msq
"""Add gdelt_events table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "gdelt_events" in inspector.get_table_names():
        return

    op.create_table(
        "gdelt_events",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("gdelt_id", sa.String(128), unique=True, nullable=False),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_domain", sa.String(256), nullable=False, server_default=""),
        sa.Column("language", sa.String(16), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cameo_code", sa.String(16), nullable=True),
        sa.Column("cameo_root", sa.String(8), nullable=True),
        sa.Column("goldstein_scale", sa.Float(), nullable=True),
        sa.Column("actor1", sa.String(256), nullable=True),
        sa.Column("actor2", sa.String(256), nullable=True),
        sa.Column("actor1_country", sa.String(8), nullable=True),
        sa.Column("actor2_country", sa.String(8), nullable=True),
        sa.Column("geo_lat", sa.Float(), nullable=True),
        sa.Column("geo_lon", sa.Float(), nullable=True),
        sa.Column("geo_country", sa.String(8), nullable=True),
        sa.Column("geo_name", sa.String(256), nullable=True),
        sa.Column("tone", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column(
            "matched_subscription_uids", JSONB, nullable=False, server_default="[]"
        ),
        sa.Column("raw_data", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_gdelt_country_cameo", "gdelt_events", ["geo_country", "cameo_root"]
    )
    op.create_index("ix_gdelt_published", "gdelt_events", ["published_at"])
    op.create_index("ix_gdelt_status", "gdelt_events", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "gdelt_events" in inspector.get_table_names():
        op.drop_table("gdelt_events")
