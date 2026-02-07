# Author: msq
"""add tool_traces

Revision ID: a2e59547cc18
Revises: 01195e08d027
Create Date: 2026-01-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "a2e59547cc18"
down_revision: Union[str, None] = "01195e08d027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_traces",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "action_uid",
            sa.String(64),
            sa.ForeignKey("actions.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("request", JSONB, server_default="{}", nullable=False),
        sa.Column("response", JSONB, server_default="{}", nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("policy", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("tool_traces")
