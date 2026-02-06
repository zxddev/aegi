"""Add caller trace fields to tool_traces.

Revision ID: 0001_add_tool_trace_caller_fields
Revises:
Create Date: 2026-01-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_add_tool_trace_caller_fields"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_traces",
        sa.Column("caller_trace_id", sa.String(), nullable=True),
        schema="agent_fabric",
    )
    op.add_column(
        "tool_traces",
        sa.Column("caller_policy_decision_id", sa.String(), nullable=True),
        schema="agent_fabric",
    )
    op.create_index(
        "tool_traces_caller_trace_id_idx",
        "tool_traces",
        ["caller_trace_id"],
        schema="agent_fabric",
    )
    op.create_index(
        "tool_traces_caller_policy_decision_id_idx",
        "tool_traces",
        ["caller_policy_decision_id"],
        schema="agent_fabric",
    )


def downgrade() -> None:
    op.drop_index(
        "tool_traces_caller_policy_decision_id_idx",
        table_name="tool_traces",
        schema="agent_fabric",
    )
    op.drop_index(
        "tool_traces_caller_trace_id_idx",
        table_name="tool_traces",
        schema="agent_fabric",
    )
    op.drop_column(
        "tool_traces",
        "caller_policy_decision_id",
        schema="agent_fabric",
    )
    op.drop_column(
        "tool_traces",
        "caller_trace_id",
        schema="agent_fabric",
    )

