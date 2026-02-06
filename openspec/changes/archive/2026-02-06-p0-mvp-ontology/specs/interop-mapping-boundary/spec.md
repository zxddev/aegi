## ADDED Requirements

### Requirement: Ontology SHALL document mapping boundaries for STIX and MISP
The system MUST document a mapping boundary for future STIX 2.1 and MISP interoperability.
This mapping boundary MUST state:
- what P0 types map to (or can be exported as) in STIX/MISP
- what is intentionally not mapped in P0

#### Scenario: Mapping boundary is documented
- **WHEN** a reviewer reads the interop mapping spec
- **THEN** it lists P0 minimal types and their intended STIX/MISP mapping targets

### Requirement: Export SHALL preserve provenance and versioning
Any future export format MUST preserve provenance links and the ontology_version used.

#### Scenario: Export requires ontology_version
- **WHEN** an export package is generated
- **THEN** it includes ontology_version and provenance references
