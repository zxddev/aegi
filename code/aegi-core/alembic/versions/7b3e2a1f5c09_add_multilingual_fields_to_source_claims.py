# Author: msq
"""add multilingual fields to source_claims

Revision ID: 7b3e2a1f5c09
Revises: 1dda8adf4f9b
Create Date: 2026-02-06 18:54:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "7b3e2a1f5c09"
down_revision: Union[str, None] = "1dda8adf4f9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("source_claims", sa.Column("language", sa.String(16), nullable=True))
    op.add_column(
        "source_claims", sa.Column("original_quote", sa.Text(), nullable=True)
    )
    op.add_column("source_claims", sa.Column("translation", sa.Text(), nullable=True))
    op.add_column("source_claims", sa.Column("translation_meta", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("source_claims", "translation_meta")
    op.drop_column("source_claims", "translation")
    op.drop_column("source_claims", "original_quote")
    op.drop_column("source_claims", "language")
