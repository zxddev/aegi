# Author: msq
"""add relation_facts table

Revision ID: 2b8d3f6a9c11
Revises: 1a9c2f5e7d10
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2b8d3f6a9c11"
down_revision = "1a9c2f5e7d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relation_facts",
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("case_uid", sa.String(length=64), nullable=False),
        sa.Column("source_entity_uid", sa.String(length=64), nullable=False),
        sa.Column("target_entity_uid", sa.String(length=64), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column(
            "supporting_source_claim_uids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("evidence_strength", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "assessed_by", sa.String(length=16), nullable=False, server_default="llm"
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "conflicts_with",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("conflict_resolution", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_by_action_uid", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_uid"], ["cases.uid"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_action_uid"], ["actions.uid"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("uid"),
    )
    op.create_index(
        "ix_relation_facts_case_uid", "relation_facts", ["case_uid"], unique=False
    )
    op.create_index(
        "ix_relation_facts_source_entity_uid",
        "relation_facts",
        ["source_entity_uid"],
        unique=False,
    )
    op.create_index(
        "ix_relation_facts_target_entity_uid",
        "relation_facts",
        ["target_entity_uid"],
        unique=False,
    )
    op.create_index(
        "ix_relation_facts_relation_type",
        "relation_facts",
        ["relation_type"],
        unique=False,
    )
    op.create_index(
        "ix_relation_facts_created_by_action_uid",
        "relation_facts",
        ["created_by_action_uid"],
        unique=False,
    )
    op.create_index(
        "ix_relation_facts_case_source_target",
        "relation_facts",
        ["case_uid", "source_entity_uid", "target_entity_uid"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_relation_facts_case_source_target", table_name="relation_facts")
    op.drop_index(
        "ix_relation_facts_created_by_action_uid", table_name="relation_facts"
    )
    op.drop_index("ix_relation_facts_relation_type", table_name="relation_facts")
    op.drop_index("ix_relation_facts_target_entity_uid", table_name="relation_facts")
    op.drop_index("ix_relation_facts_source_entity_uid", table_name="relation_facts")
    op.drop_index("ix_relation_facts_case_uid", table_name="relation_facts")
    op.drop_table("relation_facts")
