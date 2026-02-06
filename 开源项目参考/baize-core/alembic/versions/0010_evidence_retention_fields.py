"""Evidence retention 字段。

- tasks.retention_days
- artifacts/chunks/evidence.expires_at + deleted_at
- artifacts.reference_count
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_evidence_retention_fields"
down_revision = "0009_tos_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("retention_days", sa.Integer(), nullable=True),
        schema="baize_core",
    )

    op.add_column(
        "artifacts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "artifacts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "artifacts",
        sa.Column(
            "reference_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema="baize_core",
    )

    op.add_column(
        "chunks",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "chunks",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )

    op.add_column(
        "evidence",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "evidence",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="baize_core",
    )

    # 清理任务会按 deleted_at/expires_at 查询
    op.create_index(
        "artifacts_deleted_at_idx",
        "artifacts",
        ["deleted_at"],
        schema="baize_core",
    )
    op.create_index(
        "artifacts_expires_at_idx",
        "artifacts",
        ["expires_at"],
        schema="baize_core",
    )
    op.create_index(
        "chunks_deleted_at_idx",
        "chunks",
        ["deleted_at"],
        schema="baize_core",
    )
    op.create_index(
        "chunks_expires_at_idx",
        "chunks",
        ["expires_at"],
        schema="baize_core",
    )
    op.create_index(
        "evidence_deleted_at_idx",
        "evidence",
        ["deleted_at"],
        schema="baize_core",
    )
    op.create_index(
        "evidence_expires_at_idx",
        "evidence",
        ["expires_at"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "evidence_expires_at_idx",
        table_name="evidence",
        schema="baize_core",
    )
    op.drop_index(
        "evidence_deleted_at_idx",
        table_name="evidence",
        schema="baize_core",
    )
    op.drop_index(
        "chunks_expires_at_idx",
        table_name="chunks",
        schema="baize_core",
    )
    op.drop_index(
        "chunks_deleted_at_idx",
        table_name="chunks",
        schema="baize_core",
    )
    op.drop_index(
        "artifacts_expires_at_idx",
        table_name="artifacts",
        schema="baize_core",
    )
    op.drop_index(
        "artifacts_deleted_at_idx",
        table_name="artifacts",
        schema="baize_core",
    )

    op.drop_column("evidence", "deleted_at", schema="baize_core")
    op.drop_column("evidence", "expires_at", schema="baize_core")
    op.drop_column("chunks", "deleted_at", schema="baize_core")
    op.drop_column("chunks", "expires_at", schema="baize_core")
    op.drop_column("artifacts", "reference_count", schema="baize_core")
    op.drop_column("artifacts", "deleted_at", schema="baize_core")
    op.drop_column("artifacts", "expires_at", schema="baize_core")
    op.drop_column("tasks", "retention_days", schema="baize_core")

