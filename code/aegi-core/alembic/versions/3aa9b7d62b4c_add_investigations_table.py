# Author: msq
"""add investigations table

Revision ID: 3aa9b7d62b4c
Revises: 08029bef1b60
Create Date: 2026-02-12 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3aa9b7d62b4c"
down_revision = "08029bef1b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("uid", sa.String(64), nullable=False),
        sa.Column("case_uid", sa.String(64), nullable=False),
        sa.Column("trigger_event_type", sa.String(64), nullable=False),
        sa.Column("trigger_event_uid", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "rounds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "total_claims_extracted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("gap_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["case_uid"], ["cases.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid"),
    )
    op.create_index(
        "ix_investigations_case_uid",
        "investigations",
        ["case_uid"],
        unique=False,
    )
    op.create_index(
        "ix_investigations_status",
        "investigations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_investigations_created_at",
        "investigations",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_investigations_created_at", table_name="investigations")
    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_index("ix_investigations_case_uid", table_name="investigations")
    op.drop_table("investigations")
