# Author: msq
"""normalize ontology type payloads to contract dict format

Revision ID: 1a9c2f5e7d10
Revises: 08029bef1b60
Create Date: 2026-02-12
"""

from alembic import op

revision = "1a9c2f5e7d10"
down_revision = "08029bef1b60"
branch_labels = None
depends_on = None


def _normalize_column(column: str, *, kind: str) -> None:
    if kind == "entity":
        template = (
            "jsonb_build_object("  # noqa: ISC003
            "'name', trim(both '\"' from item::text),"
            "'required_properties', '[]'::jsonb,"
            "'optional_properties', '[]'::jsonb,"
            "'description', '',"
            "'deprecated', false,"
            "'deprecated_by', null"
            ")"
        )
    elif kind == "event":
        template = (
            "jsonb_build_object("  # noqa: ISC003
            "'name', trim(both '\"' from item::text),"
            "'participant_roles', '[]'::jsonb,"
            "'required_properties', '[]'::jsonb,"
            "'description', '',"
            "'deprecated', false"
            ")"
        )
    else:
        template = (
            "jsonb_build_object("  # noqa: ISC003
            "'name', trim(both '\"' from item::text),"
            "'domain', '[]'::jsonb,"
            "'range', '[]'::jsonb,"
            "'cardinality', 'many-to-many',"
            "'properties', '[]'::jsonb,"
            "'temporal', false,"
            "'description', '',"
            "'deprecated', false"
            ")"
        )

    op.execute(
        f"""
        UPDATE ontology_versions
        SET {column} = (
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item) = 'string' THEN {template}
                        WHEN jsonb_typeof(item) = 'object' THEN item
                        ELSE item
                    END
                ),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(
                CASE
                    WHEN {column} IS NULL THEN '[]'::jsonb
                    WHEN jsonb_typeof({column}::jsonb) = 'array' THEN {column}::jsonb
                    ELSE '[]'::jsonb
                END
            ) AS item
        );
        """
    )


def upgrade() -> None:
    _normalize_column("entity_types", kind="entity")
    _normalize_column("event_types", kind="event")
    _normalize_column("relation_types", kind="relation")


def downgrade() -> None:
    # 仅回退内容形态，不丢弃信息：对象保留 name，字符串原样保留。
    op.execute(
        """
        UPDATE ontology_versions
        SET entity_types = (
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item) = 'object' THEN to_jsonb(item->>'name')
                        ELSE item
                    END
                ),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(COALESCE(entity_types::jsonb, '[]'::jsonb)) AS item
        );
        """
    )
    op.execute(
        """
        UPDATE ontology_versions
        SET event_types = (
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item) = 'object' THEN to_jsonb(item->>'name')
                        ELSE item
                    END
                ),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(COALESCE(event_types::jsonb, '[]'::jsonb)) AS item
        );
        """
    )
    op.execute(
        """
        UPDATE ontology_versions
        SET relation_types = (
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(item) = 'object' THEN to_jsonb(item->>'name')
                        ELSE item
                    END
                ),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(COALESCE(relation_types::jsonb, '[]'::jsonb)) AS item
        );
        """
    )
