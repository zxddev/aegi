# Author: msq
"""add assertion_feedback table

Revision ID: 08029bef1b60
Revises: f6a7b8c9d0e1
Create Date: 2026-02-12 14:04:31.584041
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "08029bef1b60"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assertion_feedback",
        sa.Column("uid", sa.String(64), nullable=False),
        sa.Column("assertion_uid", sa.String(64), nullable=False),
        sa.Column("case_uid", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=False),
        sa.Column("confidence_override", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "suggested_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assertion_uid"], ["assertions.uid"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["case_uid"], ["cases.uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid"),
        sa.UniqueConstraint(
            "user_id", "assertion_uid", name="uq_feedback_user_assertion"
        ),
    )
    op.create_index(
        "ix_assertion_feedback_assertion_uid",
        "assertion_feedback",
        ["assertion_uid"],
        unique=False,
    )
    op.create_index(
        "ix_assertion_feedback_case_uid",
        "assertion_feedback",
        ["case_uid"],
        unique=False,
    )
    op.create_index(
        "ix_assertion_feedback_user_id",
        "assertion_feedback",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_feedback_case_assertion",
        "assertion_feedback",
        ["case_uid", "assertion_uid"],
        unique=False,
    )
    op.create_index(
        "ix_feedback_user_assertion",
        "assertion_feedback",
        ["user_id", "assertion_uid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_user_assertion", table_name="assertion_feedback")
    op.drop_index("ix_feedback_case_assertion", table_name="assertion_feedback")
    op.drop_index("ix_assertion_feedback_user_id", table_name="assertion_feedback")
    op.drop_index("ix_assertion_feedback_case_uid", table_name="assertion_feedback")
    op.drop_index(
        "ix_assertion_feedback_assertion_uid", table_name="assertion_feedback"
    )
    op.drop_table("assertion_feedback")
