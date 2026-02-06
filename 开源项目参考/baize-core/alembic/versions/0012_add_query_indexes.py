"""添加查询性能索引。

为审计表和证据链表添加常用查询的索引，优化查询性能。
"""

from __future__ import annotations

from alembic import op

revision = "0012_add_query_indexes"
down_revision = "0011_checkpoint_meta_and_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """添加查询索引。"""
    # ==========================================================================
    # 审计表索引
    # ==========================================================================

    # tool_traces 表：按 task_id 和 started_at 查询
    op.create_index(
        "ix_tool_traces_task_id",
        "tool_traces",
        ["task_id"],
        schema="baize_core",
    )
    op.create_index(
        "ix_tool_traces_started_at",
        "tool_traces",
        ["started_at"],
        schema="baize_core",
    )

    # model_traces 表：按 task_id 和 started_at 查询
    op.create_index(
        "ix_model_traces_task_id",
        "model_traces",
        ["task_id"],
        schema="baize_core",
    )
    op.create_index(
        "ix_model_traces_started_at",
        "model_traces",
        ["started_at"],
        schema="baize_core",
    )

    # policy_decisions 表：按 task_id 和 decided_at 查询
    op.create_index(
        "ix_policy_decisions_task_id",
        "policy_decisions",
        ["task_id"],
        schema="baize_core",
    )
    op.create_index(
        "ix_policy_decisions_decided_at",
        "policy_decisions",
        ["decided_at"],
        schema="baize_core",
    )

    # ==========================================================================
    # 证据链表索引
    # ==========================================================================

    # evidence 表：按 chunk_uid 关联查询，按过期/删除状态清理
    op.create_index(
        "ix_evidence_chunk_uid",
        "evidence",
        ["chunk_uid"],
        schema="baize_core",
    )
    op.create_index(
        "ix_evidence_expires_deleted",
        "evidence",
        ["expires_at", "deleted_at"],
        schema="baize_core",
    )

    # chunks 表：按 artifact_uid 关联查询，按过期/删除状态清理
    op.create_index(
        "ix_chunks_artifact_uid",
        "chunks",
        ["artifact_uid"],
        schema="baize_core",
    )
    op.create_index(
        "ix_chunks_expires_deleted",
        "chunks",
        ["expires_at", "deleted_at"],
        schema="baize_core",
    )

    # artifacts 表：按过期/删除状态清理，按引用计数查询
    op.create_index(
        "ix_artifacts_expires_deleted",
        "artifacts",
        ["expires_at", "deleted_at"],
        schema="baize_core",
    )
    op.create_index(
        "ix_artifacts_reference_count",
        "artifacts",
        ["reference_count"],
        schema="baize_core",
    )


def downgrade() -> None:
    """移除查询索引。"""
    # 证据链表索引
    op.drop_index(
        "ix_artifacts_reference_count",
        table_name="artifacts",
        schema="baize_core",
    )
    op.drop_index(
        "ix_artifacts_expires_deleted",
        table_name="artifacts",
        schema="baize_core",
    )
    op.drop_index(
        "ix_chunks_expires_deleted",
        table_name="chunks",
        schema="baize_core",
    )
    op.drop_index(
        "ix_chunks_artifact_uid",
        table_name="chunks",
        schema="baize_core",
    )
    op.drop_index(
        "ix_evidence_expires_deleted",
        table_name="evidence",
        schema="baize_core",
    )
    op.drop_index(
        "ix_evidence_chunk_uid",
        table_name="evidence",
        schema="baize_core",
    )

    # 审计表索引
    op.drop_index(
        "ix_policy_decisions_decided_at",
        table_name="policy_decisions",
        schema="baize_core",
    )
    op.drop_index(
        "ix_policy_decisions_task_id",
        table_name="policy_decisions",
        schema="baize_core",
    )
    op.drop_index(
        "ix_model_traces_started_at",
        table_name="model_traces",
        schema="baize_core",
    )
    op.drop_index(
        "ix_model_traces_task_id",
        table_name="model_traces",
        schema="baize_core",
    )
    op.drop_index(
        "ix_tool_traces_started_at",
        table_name="tool_traces",
        schema="baize_core",
    )
    op.drop_index(
        "ix_tool_traces_task_id",
        table_name="tool_traces",
        schema="baize_core",
    )
