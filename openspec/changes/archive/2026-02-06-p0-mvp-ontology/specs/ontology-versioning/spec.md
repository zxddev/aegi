## ADDED Requirements

### Requirement: System MUST version ontology changes
The system MUST store ontology versions with a content hash and a semantic version identifier.

#### Scenario: New ontology version is recorded
- **WHEN** a new ontology definition is introduced
- **THEN** the system records a new ontology_version with a hash

### Requirement: System MUST support case pinning to ontology_version
Each Case MUST reference an ontology_version and MUST NOT change it implicitly.

#### Scenario: Case pins ontology version
- **WHEN** a Case is created
- **THEN** it is assigned an ontology_version

#### Scenario: Ontology upgrade requires explicit approval
- **WHEN** an ontology_version upgrade is requested for a Case
- **THEN** it requires an Action approval and records a migration plan

### Requirement: System MUST generate a compatibility report for ontology changes
Any ontology change MUST produce a compatibility report that classifies changes as compatible, deprecated, or breaking.

#### Scenario: Breaking change is flagged
- **WHEN** a field is removed or its type changes
- **THEN** the compatibility report flags it as breaking
