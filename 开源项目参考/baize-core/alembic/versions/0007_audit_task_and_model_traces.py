"""扩展审计字段与模型审计表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_audit_task_and_model_traces"
down_revision = "0006_artifact_origin_tool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_traces",
        sa.Column("task_id", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column("task_id", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.create_table(
        "model_traces",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("trace_id", sa.Text(), nullable=False, unique=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text()),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("result_ref", sa.Text()),
        sa.Column("policy_decision_id", sa.Text()),
        schema="baize_core",
    )
    op.create_index(
        "model_traces_model_idx",
        "model_traces",
        ["model"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "model_traces_model_idx",
        table_name="model_traces",
        schema="baize_core",
    )
    op.drop_table("model_traces", schema="baize_core")
    op.drop_column("policy_decisions", "task_id", schema="baize_core")
    op.drop_column("tool_traces", "task_id", schema="baize_core")
