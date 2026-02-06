"""补充策略审计与冲突说明字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_policy_enforced_and_conflict_notes"
down_revision = "0003_storm_research_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic 默认 version_num 为 VARCHAR(32)，但本项目 revision id 超过 32 字符。
    # 必须先扩展为 TEXT，否则升级到本 revision 时会在写入 alembic_version 失败。
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE TEXT")

    op.add_column(
        "reports",
        sa.Column("conflict_notes", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column(
            "enforced",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="baize_core",
    )
    op.add_column(
        "policy_decisions",
        sa.Column(
            "hitl",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_column("policy_decisions", "hitl", schema="baize_core")
    op.drop_column("policy_decisions", "enforced", schema="baize_core")
    op.drop_column("reports", "conflict_notes", schema="baize_core")
