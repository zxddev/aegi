"""新增实体事件结构。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0002_entity_event_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA IF NOT EXISTS baize_core")

    op.create_table(
        "entity_types",
        sa.Column(
            "entity_type_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        schema="baize_core",
    )

    op.create_table(
        "event_types",
        sa.Column(
            "event_type_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        schema="baize_core",
    )

    op.create_table(
        "entities",
        sa.Column(
            "entity_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
        ),
        sa.Column("entity_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("entity_type_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "attrs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("geo_point", Geometry("POINT", srid=4326)),
        sa.Column("geo_bbox", Geometry("POLYGON", srid=4326)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(attrs) = 'object'", name="entities_attrs_object_check"
        ),
        sa.ForeignKeyConstraint(
            ["entity_type_id"], ["baize_core.entity_types.entity_type_id"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "entities_entity_type_id_idx",
        "entities",
        ["entity_type_id"],
        schema="baize_core",
    )
    op.create_index(
        "entities_geo_point_gist_idx",
        "entities",
        ["geo_point"],
        postgresql_using="gist",
        schema="baize_core",
    )
    op.create_index(
        "entities_geo_bbox_gist_idx",
        "entities",
        ["geo_bbox"],
        postgresql_using="gist",
        schema="baize_core",
    )

    op.create_table(
        "entity_aliases",
        sa.Column("entity_id", sa.BigInteger(), primary_key=True),
        sa.Column("alias", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(["entity_id"], ["baize_core.entities.entity_id"]),
        schema="baize_core",
    )
    op.create_index(
        "entity_aliases_alias_idx",
        "entity_aliases",
        ["alias"],
        schema="baize_core",
    )

    op.create_table(
        "events",
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            primary_key=True,
        ),
        sa.Column("event_uid", sa.Text(), nullable=False, unique=True),
        sa.Column("event_type_id", sa.BigInteger(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("time_start", sa.TIMESTAMP(timezone=True)),
        sa.Column("time_end", sa.TIMESTAMP(timezone=True)),
        sa.Column("location_name", sa.Text()),
        sa.Column("geo_point", Geometry("POINT", srid=4326)),
        sa.Column("geo_bbox", Geometry("POLYGON", srid=4326)),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "attrs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="events_confidence_check",
        ),
        sa.CheckConstraint(
            "time_end IS NULL OR time_start IS NULL OR time_end >= time_start",
            name="events_time_range_check",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(attrs) = 'object'", name="events_attrs_object_check"
        ),
        sa.ForeignKeyConstraint(
            ["event_type_id"], ["baize_core.event_types.event_type_id"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "events_event_type_id_idx",
        "events",
        ["event_type_id"],
        schema="baize_core",
    )
    op.create_index(
        "events_time_start_idx",
        "events",
        ["time_start"],
        schema="baize_core",
    )
    op.create_index(
        "events_geo_point_gist_idx",
        "events",
        ["geo_point"],
        postgresql_using="gist",
        schema="baize_core",
    )
    op.create_index(
        "events_geo_bbox_gist_idx",
        "events",
        ["geo_bbox"],
        postgresql_using="gist",
        schema="baize_core",
    )

    op.create_table(
        "event_participants",
        sa.Column("event_id", sa.BigInteger(), primary_key=True),
        sa.Column("entity_id", sa.BigInteger(), primary_key=True),
        sa.Column("role", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(["event_id"], ["baize_core.events.event_id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["baize_core.entities.entity_id"]),
        schema="baize_core",
    )
    op.create_index(
        "event_participants_entity_id_idx",
        "event_participants",
        ["entity_id"],
        schema="baize_core",
    )

    op.create_table(
        "event_evidence",
        sa.Column("event_id", sa.BigInteger(), primary_key=True),
        sa.Column("evidence_uid", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(["event_id"], ["baize_core.events.event_id"]),
        sa.ForeignKeyConstraint(
            ["evidence_uid"], ["baize_core.evidence.evidence_uid"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "event_evidence_evidence_uid_idx",
        "event_evidence",
        ["evidence_uid"],
        schema="baize_core",
    )

    op.create_table(
        "entity_evidence",
        sa.Column("entity_id", sa.BigInteger(), primary_key=True),
        sa.Column("evidence_uid", sa.Text(), primary_key=True),
        sa.ForeignKeyConstraint(["entity_id"], ["baize_core.entities.entity_id"]),
        sa.ForeignKeyConstraint(
            ["evidence_uid"], ["baize_core.evidence.evidence_uid"]
        ),
        schema="baize_core",
    )
    op.create_index(
        "entity_evidence_evidence_uid_idx",
        "entity_evidence",
        ["evidence_uid"],
        schema="baize_core",
    )


def downgrade() -> None:
    op.drop_index(
        "entity_evidence_evidence_uid_idx",
        table_name="entity_evidence",
        schema="baize_core",
    )
    op.drop_table("entity_evidence", schema="baize_core")
    op.drop_index(
        "event_evidence_evidence_uid_idx",
        table_name="event_evidence",
        schema="baize_core",
    )
    op.drop_table("event_evidence", schema="baize_core")
    op.drop_index(
        "event_participants_entity_id_idx",
        table_name="event_participants",
        schema="baize_core",
    )
    op.drop_table("event_participants", schema="baize_core")
    op.drop_index(
        "events_geo_bbox_gist_idx",
        table_name="events",
        schema="baize_core",
    )
    op.drop_index(
        "events_geo_point_gist_idx",
        table_name="events",
        schema="baize_core",
    )
    op.drop_index(
        "events_time_start_idx",
        table_name="events",
        schema="baize_core",
    )
    op.drop_index(
        "events_event_type_id_idx",
        table_name="events",
        schema="baize_core",
    )
    op.drop_table("events", schema="baize_core")
    op.drop_index(
        "entity_aliases_alias_idx",
        table_name="entity_aliases",
        schema="baize_core",
    )
    op.drop_table("entity_aliases", schema="baize_core")
    op.drop_index(
        "entities_geo_bbox_gist_idx",
        table_name="entities",
        schema="baize_core",
    )
    op.drop_index(
        "entities_geo_point_gist_idx",
        table_name="entities",
        schema="baize_core",
    )
    op.drop_index(
        "entities_entity_type_id_idx",
        table_name="entities",
        schema="baize_core",
    )
    op.drop_table("entities", schema="baize_core")
    op.drop_table("event_types", schema="baize_core")
    op.drop_table("entity_types", schema="baize_core")
