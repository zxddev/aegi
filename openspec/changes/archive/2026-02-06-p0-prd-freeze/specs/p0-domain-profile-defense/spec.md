## ADDED Requirements

### Requirement: P0 domain focus SHALL be defense/geopolitics, without ontology lock-in
P0 MUST use international defense/geopolitics examples for user flows and fixtures, but MUST NOT require domain-specific ontology types in P0. P0 ontology MUST remain a minimal general set with extension points.

#### Scenario: Fixtures theme is defense/geopolitics
- **WHEN** a reviewer inspects the P0 fixtures manifest
- **THEN** the examples are clearly defense/geopolitics themed

#### Scenario: Ontology is minimal and extensible
- **WHEN** a reviewer inspects the P0 ontology definition
- **THEN** it contains only the minimal general set plus extension points

### Requirement: PRD MUST include the domain profile statement
The PRD MUST explicitly state the chosen domain focus and the non-lock-in ontology decision.

#### Scenario: PRD states domain focus
- **WHEN** a reviewer reads the PRD scope
- **THEN** the PRD states defense/geopolitics as the P0 focus and clarifies ontology non-lock-in
