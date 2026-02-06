"""初始化存储表结构。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS baize_core")
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("task_id", sa.Text(), nullable=False, unique=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "constraints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("time_window", sa.Text()),
        sa.Column("region", sa.Text()),
        sa.Column("sensitivity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="baize_core",
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("artifact_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("source_url", sa.Text()),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("fetch_trace_id", sa.Text()),
        sa.Column("license_note", sa.Text()),
        schema="baize_core",
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("chunk_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("artifact_uid", sa.Text(), nullable=False),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_ref", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_uid"], ["baize_core.artifacts.artifact_uid"]),
        schema="baize_core",
    )
    op.create_index("chunks_artifact_uid_idx", "chunks", ["artifact_uid"], schema="baize_core")

    op.create_table(
        "evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("evidence_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("chunk_uid", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("uri", sa.Text()),
        sa.Column("collected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("base_credibility", sa.Float(), nullable=False),
        sa.Column("score", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "conflict_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "conflict_with",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("summary", sa.Text()),
        sa.ForeignKeyConstraint(["chunk_uid"], ["baize_core.chunks.chunk_uid"]),
        schema="baize_core",
    )
    op.create_index("evidence_chunk_uid_idx", "evidence", ["chunk_uid"], schema="baize_core")

    op.create_table(
        "claims",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("claim_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "contradictions",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        schema="baize_core",
    )

    op.create_table(
        "claim_evidence",
        sa.Column("claim_uid", sa.Text(), primary_key=True),
        sa.Column("evidence_uid", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(["claim_uid"], ["baize_core.claims.claim_uid"]),
        sa.ForeignKeyConstraint(["evidence_uid"], ["baize_core.evidence.evidence_uid"]),
        schema="baize_core",
    )
    op.create_index(
        "claim_evidence_evidence_uid_idx",
        "claim_evidence",
        ["evidence_uid"],
        schema="baize_core",
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("report_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("content_ref", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["baize_core.tasks.task_id"]),
        schema="baize_core",
    )
    op.create_index("reports_task_id_idx", "reports", ["task_id"], schema="baize_core")

    op.create_table(
        "report_references",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("report_uid", sa.Text(), nullable=False),
        sa.Column("citation", sa.Integer(), nullable=False),
        sa.Column("evidence_uid", sa.Text(), nullable=False),
        sa.Column("chunk_uid", sa.Text(), nullable=False),
        sa.Column("artifact_uid", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_ref", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["report_uid"], ["baize_core.reports.report_uid"]),
        sa.ForeignKeyConstraint(["evidence_uid"], ["baize_core.evidence.evidence_uid"]),
        sa.ForeignKeyConstraint(["chunk_uid"], ["baize_core.chunks.chunk_uid"]),
        sa.ForeignKeyConstraint(["artifact_uid"], ["baize_core.artifacts.artifact_uid"]),
        schema="baize_core",
    )
    op.create_index(
        "report_references_report_uid_idx",
        "report_references",
        ["report_uid"],
        schema="baize_core",
    )

    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("decision_id", sa.Text(), nullable=False, unique=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("allow", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        schema="baize_core",
    )
    op.create_index(
        "policy_decisions_request_id_idx",
        "policy_decisions",
        ["request_id"],
        schema="baize_core",
    )

    op.create_table(
        "tool_traces",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("trace_id", sa.Text(), nullable=False, unique=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("result_ref", sa.Text()),
        sa.Column("policy_decision_id", sa.Text()),
        schema="baize_core",
    )
    op.create_index("tool_traces_tool_name_idx", "tool_traces", ["tool_name"], schema="baize_core")

    op.create_table(
        "review_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("review_id", sa.Text(), nullable=False, unique=True),
        sa.Column("task_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("resume_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True)),
        schema="baize_core",
    )
    op.create_index(
        "review_requests_status_idx",
        "review_requests",
        ["status"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index("review_requests_status_idx", table_name="review_requests", schema="baize_core")
    op.drop_table("review_requests", schema="baize_core")
    op.drop_index("tool_traces_tool_name_idx", table_name="tool_traces", schema="baize_core")
    op.drop_table("tool_traces", schema="baize_core")
    op.drop_index("policy_decisions_request_id_idx", table_name="policy_decisions", schema="baize_core")
    op.drop_table("policy_decisions", schema="baize_core")
    op.drop_index("report_references_report_uid_idx", table_name="report_references", schema="baize_core")
    op.drop_table("report_references", schema="baize_core")
    op.drop_index("reports_task_id_idx", table_name="reports", schema="baize_core")
    op.drop_table("reports", schema="baize_core")
    op.drop_index("claim_evidence_evidence_uid_idx", table_name="claim_evidence", schema="baize_core")
    op.drop_table("claim_evidence", schema="baize_core")
    op.drop_table("claims", schema="baize_core")
    op.drop_index("evidence_chunk_uid_idx", table_name="evidence", schema="baize_core")
    op.drop_table("evidence", schema="baize_core")
    op.drop_index("chunks_artifact_uid_idx", table_name="chunks", schema="baize_core")
    op.drop_table("chunks", schema="baize_core")
    op.drop_table("artifacts", schema="baize_core")
    op.drop_table("tasks", schema="baize_core")
