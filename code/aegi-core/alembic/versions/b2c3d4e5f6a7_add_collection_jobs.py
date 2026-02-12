"""add collection_jobs table

Revision ID: b2c3d4e5f6a7
Revises: 9a1b2c3d4e5f
Create Date: 2026-02-11 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "9a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collection_jobs",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column(
            "categories", sa.String(64), nullable=False, server_default="general"
        ),
        sa.Column("language", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("max_results", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("urls_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urls_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urls_deduped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claims_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_meta", JSONB, nullable=False, server_default="{}"),
        sa.Column("cron_expression", sa.String(64), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Dedup index on artifact_versions for faster content-based dedup queries
    op.create_index(
        "ix_artifact_versions_case_sha256",
        "artifact_versions",
        ["case_uid", "content_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_artifact_versions_case_sha256", table_name="artifact_versions")
    op.drop_table("collection_jobs")
