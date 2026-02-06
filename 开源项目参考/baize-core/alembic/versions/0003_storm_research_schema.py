"""STORM 研究结构表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_storm_research_schema"
down_revision = "0002_entity_event_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storm_outlines",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("outline_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "coverage_checklist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["baize_core.tasks.task_id"]),
        schema="baize_core",
    )
    op.create_index(
        "storm_outlines_task_id_idx",
        "storm_outlines",
        ["task_id"],
        schema="baize_core",
    )

    op.create_table(
        "storm_sections",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("section_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("outline_uid", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "coverage_item_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "depth_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["outline_uid"], ["baize_core.storm_outlines.outline_uid"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "storm_sections_outline_uid_idx",
        "storm_sections",
        ["outline_uid"],
        schema="baize_core",
    )

    op.create_table(
        "storm_section_iterations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("section_uid", sa.Text(), nullable=False),
        sa.Column("iteration_index", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["section_uid"], ["baize_core.storm_sections.section_uid"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "storm_section_iterations_section_uid_idx",
        "storm_section_iterations",
        ["section_uid"],
        schema="baize_core",
    )

    op.create_table(
        "storm_section_evidence",
        sa.Column("section_uid", sa.Text(), primary_key=True),
        sa.Column("evidence_uid", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(
            ["section_uid"], ["baize_core.storm_sections.section_uid"]
        ),
        sa.ForeignKeyConstraint(
            ["evidence_uid"], ["baize_core.evidence.evidence_uid"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "storm_section_evidence_evidence_uid_idx",
        "storm_section_evidence",
        ["evidence_uid"],
        schema="baize_core",
    )

    op.add_column(
        "reports",
        sa.Column("outline_uid", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.add_column(
        "reports",
        sa.Column("report_type", sa.Text(), nullable=True),
        schema="baize_core",
    )
    op.create_index(
        "reports_outline_uid_idx",
        "reports",
        ["outline_uid"],
        schema="baize_core",
    )
    op.create_foreign_key(
        "reports_outline_uid_fk",
        "reports",
        "storm_outlines",
        ["outline_uid"],
        ["outline_uid"],
        source_schema="baize_core",
        referent_schema="baize_core",
    )


def downgrade() -> None:
    op.drop_constraint(
        "reports_outline_uid_fk",
        "reports",
        schema="baize_core",
        type_="foreignkey",
    )
    op.drop_index(
        "reports_outline_uid_idx", table_name="reports", schema="baize_core"
    )
    op.drop_column("reports", "report_type", schema="baize_core")
    op.drop_column("reports", "outline_uid", schema="baize_core")

    op.drop_index(
        "storm_section_evidence_evidence_uid_idx",
        table_name="storm_section_evidence",
        schema="baize_core",
    )
    op.drop_table("storm_section_evidence", schema="baize_core")
    op.drop_index(
        "storm_section_iterations_section_uid_idx",
        table_name="storm_section_iterations",
        schema="baize_core",
    )
    op.drop_table("storm_section_iterations", schema="baize_core")
    op.drop_index(
        "storm_sections_outline_uid_idx",
        table_name="storm_sections",
        schema="baize_core",
    )
    op.drop_table("storm_sections", schema="baize_core")
    op.drop_index(
        "storm_outlines_task_id_idx",
        table_name="storm_outlines",
        schema="baize_core",
    )
    op.drop_table("storm_outlines", schema="baize_core")
