# Author: msq
"""add ontology_versions and case_ontology_pins tables

Revision ID: c4a7e3b21d06
Revises: 7b3e2a1f5c09
Create Date: 2026-02-07 20:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4a7e3b21d06"
down_revision: Union[str, None] = "7b3e2a1f5c09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ontology_versions",
        sa.Column("version", sa.String(64), primary_key=True),
        sa.Column("entity_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("relation_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "case_ontology_pins",
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ontology_version", sa.String(64), nullable=False),
        sa.Column(
            "pinned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("case_ontology_pins")
    op.drop_table("ontology_versions")
