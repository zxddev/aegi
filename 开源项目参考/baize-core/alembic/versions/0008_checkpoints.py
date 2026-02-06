"""检查点表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_checkpoints"
down_revision = "0007_audit_task_and_model_traces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkpoints",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("checkpoint_id", sa.Text(), nullable=False, unique=True),
        sa.Column("thread_id", sa.Text(), nullable=False, index=True),
        sa.Column("state_json", JSONB(), nullable=False),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", JSONB(), nullable=True),
        schema="baize_core",
    )
    # 复合索引：按 thread_id 和 created_at 排序查询最新检查点
    op.create_index(
        "ix_checkpoints_thread_created",
        "checkpoints",
        ["thread_id", "created_at"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_checkpoints_thread_created",
        table_name="checkpoints",
        schema="baize_core",
    )
    op.drop_table("checkpoints", schema="baize_core")
