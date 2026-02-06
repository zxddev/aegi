"""新增 Artifact origin_tool 字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_artifact_origin_tool"
down_revision = "0005_scrape_guard_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("origin_tool", sa.Text(), nullable=True),
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_column("artifacts", "origin_tool", schema="baize_core")
