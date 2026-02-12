# Author: msq
"""add analysis_memory table

Revision ID: 4d9e0aa1f2b3
Revises: 3aa9b7d62b4c, 3c7e4a8b0d12
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "4d9e0aa1f2b3"
down_revision = ("3aa9b7d62b4c", "3c7e4a8b0d12")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_memory",
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("case_uid", sa.String(length=64), nullable=False),
        sa.Column("scenario_summary", sa.Text(), nullable=False),
        sa.Column(
            "hypotheses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "key_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("conclusion", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("prediction_accuracy", sa.Float(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column(
            "pattern_tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
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
        sa.ForeignKeyConstraint(["case_uid"], ["cases.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid"),
    )
    op.create_index(
        "ix_analysis_memory_case_uid",
        "analysis_memory",
        ["case_uid"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_memory_created_at",
        "analysis_memory",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_memory_created_at", table_name="analysis_memory")
    op.drop_index("ix_analysis_memory_case_uid", table_name="analysis_memory")
    op.drop_table("analysis_memory")

