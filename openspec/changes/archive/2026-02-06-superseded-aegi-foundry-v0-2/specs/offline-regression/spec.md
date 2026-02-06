## ADDED Requirements

### Requirement: P0 regression MUST run offline
The system MUST provide an offline regression suite that can validate the P0 evidence loop without any live internet access.

#### Scenario: Run tests without network access
- **WHEN** the regression suite is executed in an environment without internet
- **THEN** the suite completes using fixtures only
- **THEN** the suite reports PASS/FAIL deterministically

### Requirement: Fixtures MUST include archived artifacts and expected selectors
The system MUST ship fixtures that include:
- archived artifact bytes (or references) for HTML/PDF
- expected parse outputs
- expected chunk anchors (`anchor_set`)
- expected SourceClaims with selectors

#### Scenario: Anchor locate regression
- **WHEN** the anchor regression is executed on fixtures
- **THEN** the system reports an anchor locate rate metric

#### Scenario: Claim grounding regression
- **WHEN** SourceClaim extraction is executed on fixtures
- **THEN** the system reports a claim grounding rate metric
