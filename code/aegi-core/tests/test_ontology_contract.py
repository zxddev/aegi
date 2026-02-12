# Author: msq
"""Ontology contract compatibility and validation tests."""

from __future__ import annotations

from datetime import datetime, timezone

from aegi_core.services.ontology_versioning import (
    ChangeLevel,
    OntologyVersion,
    compute_compatibility,
    register_version,
    reset_registry,
    validate_against_ontology,
)


def test_legacy_list_string_payload_is_backward_compatible() -> None:
    version = OntologyVersion(
        version="1.0.0",
        entity_types=["Person"],
        event_types=["Meeting"],
        relation_types=["AFFILIATED_WITH"],
        created_at=datetime.now(timezone.utc),
    )

    assert version.entity_types[0].name == "Person"
    assert version.relation_types[0].cardinality == "many-to-many"


def test_contract_diff_detects_property_and_constraint_breaking() -> None:
    reset_registry()
    now = datetime.now(timezone.utc)

    register_version(
        OntologyVersion(
            version="1.0.0",
            entity_types=[
                {
                    "name": "Person",
                    "required_properties": ["name"],
                    "optional_properties": ["age"],
                }
            ],
            event_types=[
                {
                    "name": "Meeting",
                    "participant_roles": ["actor", "target"],
                    "required_properties": ["location"],
                }
            ],
            relation_types=[
                {
                    "name": "AFFILIATED_WITH",
                    "domain": [],
                    "range": [],
                    "properties": ["role"],
                }
            ],
            created_at=now,
        )
    )
    register_version(
        OntologyVersion(
            version="2.0.0",
            entity_types=[
                {
                    "name": "Person",
                    "required_properties": ["name", "nationality"],
                    "optional_properties": [],
                    "deprecated": True,
                    "deprecated_by": "Human",
                }
            ],
            event_types=[
                {
                    "name": "Meeting",
                    "participant_roles": ["actor"],
                    "required_properties": ["location", "agenda"],
                }
            ],
            relation_types=[
                {
                    "name": "AFFILIATED_WITH",
                    "domain": ["Person"],
                    "range": ["Organization"],
                    "cardinality": "one-to-many",
                    "properties": [],
                }
            ],
            created_at=now,
        )
    )

    report = compute_compatibility("1.0.0", "2.0.0")
    assert report.overall_level == ChangeLevel.BREAKING
    levels = {change.level for change in report.changes}
    assert ChangeLevel.BREAKING in levels
    assert ChangeLevel.DEPRECATED in levels


def test_validate_against_ontology_entity_and_relation_contract() -> None:
    ontology = OntologyVersion(
        version="1.0.0",
        entity_types=[
            {
                "name": "Person",
                "required_properties": ["name"],
            },
            {
                "name": "Organization",
                "required_properties": ["name"],
            },
        ],
        event_types=[],
        relation_types=[
            {
                "name": "AFFILIATED_WITH",
                "domain": ["Person"],
                "range": ["Organization"],
                "properties": ["role"],
            }
        ],
        created_at=datetime.now(timezone.utc),
    )

    entity_error = validate_against_ontology(
        {"entity_type": "Person", "properties": {}},
        ontology,
    )
    assert entity_error is not None
    assert entity_error.error_code == "ontology_entity_missing_properties"

    relation_error = validate_against_ontology(
        {"relation_type": "AFFILIATED_WITH", "properties": {"role": "analyst"}},
        ontology,
        source_entity={"entity_type": "Organization"},
        target_entity={"entity_type": "Organization"},
    )
    assert relation_error is not None
    assert relation_error.error_code == "ontology_relation_domain_violation"

    relation_ok = validate_against_ontology(
        {"relation_type": "AFFILIATED_WITH", "properties": {"role": "analyst"}},
        ontology,
        source_entity={"entity_type": "Person"},
        target_entity={"entity_type": "Organization"},
    )
    assert relation_ok is None
