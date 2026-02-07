# Author: msq
"""add cases and actions

Revision ID: 3f52046a1239
Revises: bc5052692a40
Create Date: 2026-01-15 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "3f52046a1239"
down_revision: Union[str, None] = "bc5052692a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "actions",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("inputs", JSONB, server_default="{}", nullable=False),
        sa.Column("outputs", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("actions")
    op.drop_table("cases")
