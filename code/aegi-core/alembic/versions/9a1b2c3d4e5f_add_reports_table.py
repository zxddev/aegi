"""add reports table

Revision ID: 9a1b2c3d4e5f
Revises: 377e829ab430
Create Date: 2026-02-10 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: Union[str, None] = "377e829ab430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sections", JSONB, nullable=False, server_default="{}"),
        sa.Column("rendered_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("reports")
