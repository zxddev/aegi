# Author: msq
"""add entity_identity_actions table

Revision ID: 3c7e4a8b0d12
Revises: 2b8d3f6a9c11
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3c7e4a8b0d12"
down_revision = "2b8d3f6a9c11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_identity_actions",
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("case_uid", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column(
            "entity_uids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("result_entity_uid", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("performed_by", sa.String(length=16), nullable=False),
        sa.Column(
            "approved", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
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
        "ix_entity_identity_actions_case_uid",
        "entity_identity_actions",
        ["case_uid"],
        unique=False,
    )
    op.create_index(
        "ix_entity_identity_actions_created_by_action_uid",
        "entity_identity_actions",
        ["created_by_action_uid"],
        unique=False,
    )
    op.create_index(
        "ix_entity_identity_actions_status",
        "entity_identity_actions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_entity_identity_actions_status", table_name="entity_identity_actions"
    )
    op.drop_index(
        "ix_entity_identity_actions_created_by_action_uid",
        table_name="entity_identity_actions",
    )
    op.drop_index(
        "ix_entity_identity_actions_case_uid", table_name="entity_identity_actions"
    )
    op.drop_table("entity_identity_actions")
