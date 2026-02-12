"""Add Bayesian ACH: hypotheses new columns + evidence_assessments + probability_updates

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # hypotheses 表新增字段
    op.add_column(
        "hypotheses",
        sa.Column(
            "prior_probability",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "hypotheses",
        sa.Column(
            "posterior_probability",
            sa.Float(),
            nullable=True,
        ),
    )

    # evidence_assessments 新表
    op.create_table(
        "evidence_assessments",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "hypothesis_uid",
            sa.String(64),
            sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("evidence_uid", sa.String(64), nullable=False, index=True),
        sa.Column(
            "evidence_type", sa.String(16), nullable=False, server_default="assertion"
        ),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("likelihood", sa.Float(), nullable=False),
        sa.Column("assessed_by", sa.String(16), nullable=False, server_default="llm"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ea_hyp_evidence", "evidence_assessments", ["hypothesis_uid", "evidence_uid"]
    )
    op.create_unique_constraint(
        "uq_ea_hyp_evidence", "evidence_assessments", ["hypothesis_uid", "evidence_uid"]
    )

    # probability_updates 新表（修正 1：独立表替代 JSONB）
    op.create_table(
        "probability_updates",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "hypothesis_uid",
            sa.String(64),
            sa.ForeignKey("hypotheses.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("evidence_uid", sa.String(64), nullable=False),
        sa.Column("prior", sa.Float(), nullable=False),
        sa.Column("posterior", sa.Float(), nullable=False),
        sa.Column("likelihood", sa.Float(), nullable=False),
        sa.Column("likelihood_ratio", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("probability_updates")
    op.drop_table("evidence_assessments")
    op.drop_column("hypotheses", "posterior_probability")
    op.drop_column("hypotheses", "prior_probability")
