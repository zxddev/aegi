# Author: msq
"""add p0 evidence chain tables

Revision ID: 01195e08d027
Revises: 3f52046a1239
Create Date: 2026-01-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "01195e08d027"
down_revision: Union[str, None] = "3f52046a1239"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact_identities",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "artifact_versions",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "artifact_identity_uid",
            sa.String(64),
            sa.ForeignKey("artifact_identities.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("source_meta", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "chunks",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "artifact_version_uid",
            sa.String(64),
            sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("anchor_set", JSONB, server_default="[]", nullable=False),
        sa.Column("anchor_health", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "evidence",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "artifact_version_uid",
            sa.String(64),
            sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chunk_uid",
            sa.String(64),
            sa.ForeignKey("chunks.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=True),
        sa.Column("pii_flags", JSONB, server_default="{}", nullable=False),
        sa.Column("retention_policy", JSONB, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "source_claims",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "artifact_version_uid",
            sa.String(64),
            sa.ForeignKey("artifact_versions.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "chunk_uid",
            sa.String(64),
            sa.ForeignKey("chunks.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "evidence_uid",
            sa.String(64),
            sa.ForeignKey("evidence.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("selectors", JSONB, server_default="[]", nullable=False),
        sa.Column("attributed_to", sa.Text(), nullable=True),
        sa.Column("modality", sa.String(32), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("original_quote", sa.Text(), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("translation_meta", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "assertions",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value", JSONB, server_default="{}", nullable=False),
        sa.Column("source_claim_uids", JSONB, server_default="[]", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "judgments",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("assertion_uids", JSONB, server_default="[]", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "hypotheses",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "supporting_assertion_uids",
            JSONB,
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "contradicting_assertion_uids",
            JSONB,
            server_default="[]",
            nullable=False,
        ),
        sa.Column("coverage_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("gap_list", JSONB, server_default="[]", nullable=False),
        sa.Column("adversarial_result", JSONB, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "narratives",
        sa.Column("uid", sa.String(64), primary_key=True),
        sa.Column(
            "case_uid",
            sa.String(64),
            sa.ForeignKey("cases.uid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("theme", sa.Text(), nullable=False),
        sa.Column("source_claim_uids", JSONB, server_default="[]", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("narratives")
    op.drop_table("hypotheses")
    op.drop_table("judgments")
    op.drop_table("assertions")
    op.drop_table("source_claims")
    op.drop_table("evidence")
    op.drop_table("chunks")
    op.drop_table("artifact_versions")
    op.drop_table("artifact_identities")
