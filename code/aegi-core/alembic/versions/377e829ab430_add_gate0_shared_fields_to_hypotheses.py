"""add gate0 shared fields to hypotheses

Revision ID: 377e829ab430
Revises: c4a7e3b21d06
Create Date: 2026-02-08 14:40:55.443223

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "377e829ab430"
down_revision: Union[str, None] = "c4a7e3b21d06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hypotheses", sa.Column("modality", sa.String(32), nullable=True))
    op.add_column("hypotheses", sa.Column("segment_ref", sa.String(128), nullable=True))
    op.add_column("hypotheses", sa.Column("media_time_range", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("hypotheses", "media_time_range")
    op.drop_column("hypotheses", "segment_ref")
    op.drop_column("hypotheses", "modality")
