# Author: msq
"""add foundation gate-0 shared fields

Revision ID: 1dda8adf4f9b
Revises: a2e59547cc18
Create Date: 2026-02-06 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "1dda8adf4f9b"
down_revision: Union[str, None] = "a2e59547cc18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_claims", sa.Column("segment_ref", sa.String(128), nullable=True))
    op.add_column("source_claims", sa.Column("media_time_range", JSONB, nullable=True))
    op.add_column("assertions", sa.Column("modality", sa.String(32), nullable=True))
    op.add_column("assertions", sa.Column("segment_ref", sa.String(128), nullable=True))
    op.add_column("assertions", sa.Column("media_time_range", JSONB, nullable=True))
    op.add_column("actions", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column("actions", sa.Column("span_id", sa.String(64), nullable=True))
    op.add_column("tool_traces", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column("tool_traces", sa.Column("span_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("tool_traces", "span_id")
    op.drop_column("tool_traces", "trace_id")
    op.drop_column("actions", "span_id")
    op.drop_column("actions", "trace_id")
    op.drop_column("assertions", "media_time_range")
    op.drop_column("assertions", "segment_ref")
    op.drop_column("assertions", "modality")
    op.drop_column("source_claims", "media_time_range")
    op.drop_column("source_claims", "segment_ref")
