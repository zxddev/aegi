"""Add event-driven tables: subscriptions, event_log, push_log

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ──
    op.create_table(
        "subscriptions",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False, index=True),
        sa.Column("sub_type", sa.String(16), nullable=False),
        sa.Column("sub_target", sa.String(256), nullable=False, server_default="*"),
        sa.Column(
            "priority_threshold", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("event_types", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("interest_text", sa.Text(), nullable=True),
        sa.Column(
            "embedding_synced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sub_type_target", "subscriptions", ["sub_type", "sub_target"])

    # ── event_log ──
    op.create_table(
        "event_log",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="SET NULL"),
            index=True,
            nullable=True,
        ),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("entities", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("regions", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("topics", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("source_event_uid", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("push_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )

    # ── push_log ──
    op.create_table(
        "push_log",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "event_uid",
            sa.String(64),
            sa.ForeignKey("event_log.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.String(128), nullable=False, index=True),
        sa.Column("subscription_uid", sa.String(64), nullable=True),
        sa.Column("match_method", sa.String(16), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("push_log")
    op.drop_table("event_log")
    op.drop_table("subscriptions")
