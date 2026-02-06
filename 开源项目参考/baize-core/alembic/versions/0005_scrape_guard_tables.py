"""新增 Scrape Guard 表结构。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_scrape_guard_tables"
down_revision = "0004_policy_enforced_and_conflict_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_guard_domains",
        sa.Column("domain", sa.Text(), primary_key=True),
        sa.Column("policy", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "policy IN ('allow', 'deny')",
            name="scrape_guard_domains_policy_check",
        ),
        sa.CheckConstraint(
            "domain = lower(domain)",
            name="scrape_guard_domains_lowercase_check",
        ),
        schema="baize_core",
    )

    op.create_table(
        "scrape_guard_settings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("domain_rps", sa.Float(), nullable=False),
        sa.Column("domain_concurrency", sa.Integer(), nullable=False),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("robots_require_allow", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("domain_rps > 0", name="scrape_guard_settings_rps_check"),
        sa.CheckConstraint(
            "domain_concurrency > 0",
            name="scrape_guard_settings_concurrency_check",
        ),
        sa.CheckConstraint(
            "cache_ttl_seconds > 0",
            name="scrape_guard_settings_cache_check",
        ),
        schema="baize_core",
    )
    op.create_index(
        "scrape_guard_settings_created_at_idx",
        "scrape_guard_settings",
        ["created_at"],
        schema="baize_core",
    )

    op.create_table(
        "scrape_guard_robots_checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("robots_url", sa.Text(), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "checked_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="baize_core",
    )
    op.create_index(
        "scrape_guard_robots_checks_host_idx",
        "scrape_guard_robots_checks",
        ["host"],
        schema="baize_core",
    )
    op.create_index(
        "scrape_guard_robots_checks_checked_at_idx",
        "scrape_guard_robots_checks",
        ["checked_at"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "scrape_guard_robots_checks_checked_at_idx",
        table_name="scrape_guard_robots_checks",
        schema="baize_core",
    )
    op.drop_index(
        "scrape_guard_robots_checks_host_idx",
        table_name="scrape_guard_robots_checks",
        schema="baize_core",
    )
    op.drop_table("scrape_guard_robots_checks", schema="baize_core")

    op.drop_index(
        "scrape_guard_settings_created_at_idx",
        table_name="scrape_guard_settings",
        schema="baize_core",
    )
    op.drop_table("scrape_guard_settings", schema="baize_core")

    op.drop_table("scrape_guard_domains", schema="baize_core")
