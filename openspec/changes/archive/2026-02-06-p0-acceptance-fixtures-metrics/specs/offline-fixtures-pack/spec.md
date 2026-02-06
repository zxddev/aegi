## ADDED Requirements

### Requirement: P0 SHALL ship an offline fixtures pack with a manifest
The system MUST provide an offline fixtures pack that allows P0 acceptance and regression to run without internet access. The fixtures pack MUST include a manifest describing each fixture item.

#### Scenario: Fixtures can be enumerated by manifest
- **WHEN** a reviewer inspects the fixtures directory
- **THEN** a manifest file exists and lists all fixtures with IDs and metadata

### Requirement: Fixtures MUST include archived artifacts and expected anchor contracts
The fixtures pack MUST include, for each fixture:
- archived artifact bytes (HTML and/or PDF)
- expected parse output (or a stable intermediate representation)
- expected `Chunk` anchor contracts (`anchor_set`)
- expected `SourceClaim` records with selectors grounded to anchors

#### Scenario: Fixture contains anchor_set and SourceClaims
- **WHEN** a fixture is loaded for regression
- **THEN** the fixture includes expected `anchor_set` for chunks
- **THEN** the fixture includes expected SourceClaims with non-empty selectors

### Requirement: Fixtures SHALL be defense/geopolitics themed for P0
P0 fixtures MUST use international defense/geopolitics themed examples.

#### Scenario: Manifest indicates domain profile
- **WHEN** a reviewer reads the fixtures manifest
- **THEN** each fixture includes a domain tag indicating defense/geopolitics
