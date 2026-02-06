"""ToS（服务条款）检查表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_tos_checks"
down_revision = "0008_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_guard_tos_checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False, index=True),
        sa.Column("tos_url", sa.Text(), nullable=True),
        sa.Column("tos_found", sa.Boolean(), nullable=False),
        sa.Column("scraping_allowed", sa.Boolean(), nullable=True),
        sa.Column("tos_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="baize_core",
    )
    # 索引：按 host 和 checked_at 查询最新记录
    op.create_index(
        "ix_tos_checks_host_checked",
        "scrape_guard_tos_checks",
        ["host", "checked_at"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tos_checks_host_checked",
        table_name="scrape_guard_tos_checks",
        schema="baize_core",
    )
    op.drop_table("scrape_guard_tos_checks", schema="baize_core")
