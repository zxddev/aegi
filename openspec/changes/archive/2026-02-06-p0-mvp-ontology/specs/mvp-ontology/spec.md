## ADDED Requirements

### Requirement: P0 SHALL define a minimal general ontology with extension points
The system MUST define a minimal general ontology sufficient for P0 flows and MUST include extension points for future domain-specific types.

Minimal entity types (P0):
- Person
- Organization
- Location

Minimal event representation (P0):
- Event (with a `category` field)

#### Scenario: Reviewer can identify minimal types
- **WHEN** a reviewer inspects the ontology definition
- **THEN** the minimal types Person/Organization/Location/Event are present

#### Scenario: Domain-specific types are not required in P0
- **WHEN** a P0 case is created and processed
- **THEN** it does not require weapon/unit/installation types to be present

### Requirement: Ontology MUST include stable identifiers for types and fields
Ontology definitions MUST use stable IDs for each type and field so that compatibility can be assessed across versions.

#### Scenario: Type and field IDs are stable
- **WHEN** an ontology version is updated
- **THEN** unchanged types/fields retain the same IDs
