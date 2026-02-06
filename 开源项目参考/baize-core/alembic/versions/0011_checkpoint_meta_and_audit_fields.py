"""检查点字段调整与审计扩展。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_checkpoint_meta_and_audit_fields"
down_revision = "0010_evidence_retention_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "checkpoints",
        "metadata",
        new_column_name="checkpoint_meta",
        schema="baize_core",
    )

    op.add_column(
        "model_traces",
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "model_traces",
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        schema="baize_core",
    )

    op.add_column(
        "policy_decisions",
        sa.Column("action", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column("stage", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column(
            "hitl_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_column("policy_decisions", "decided_at", schema="baize_core")
    op.drop_column("policy_decisions", "hitl_required", schema="baize_core")
    op.drop_column("policy_decisions", "stage", schema="baize_core")
    op.drop_column("policy_decisions", "action", schema="baize_core")

    op.drop_column("model_traces", "output_tokens", schema="baize_core")
    op.drop_column("model_traces", "input_tokens", schema="baize_core")

    op.alter_column(
        "checkpoints",
        "checkpoint_meta",
        new_column_name="metadata",
        schema="baize_core",
    )
