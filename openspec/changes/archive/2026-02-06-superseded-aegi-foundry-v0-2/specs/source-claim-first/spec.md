## ADDED Requirements

### Requirement: SourceClaim MUST be grounded with selectors
The system MUST represent extracted statements as `SourceClaim` records that contain:
- a verbatim `quote`
- `selectors` sufficient to locate the quote within the underlying evidence (anchor contract)
- links to `evidence_uid`, `chunk_uid`, and `artifact_version_uid`

The system MUST reject any SourceClaim that does not include selectors.

#### Scenario: Extracted SourceClaim includes selectors
- **WHEN** the system extracts claims from a chunk
- **THEN** each SourceClaim includes a `quote`
- **THEN** each SourceClaim includes non-empty `selectors`

#### Scenario: Ungrounded claim is rejected
- **WHEN** a SourceClaim candidate is produced without selectors
- **THEN** the system rejects it and records a validation error

### Requirement: Assertions are derived from SourceClaims
The system MUST create `Assertion` records only by fusing one or more `SourceClaim` records. Every Assertion MUST be linked to at least one SourceClaim.

#### Scenario: Create Assertion with SourceClaims
- **WHEN** the system fuses multiple SourceClaims into an Assertion
- **THEN** the Assertion is created
- **THEN** the system records links from the Assertion to all contributing SourceClaims

#### Scenario: Assertion without sources is rejected
- **WHEN** an Assertion is created with an empty list of SourceClaims
- **THEN** the system rejects the request with a structured error

### Requirement: Conflicts are first-class
The system MUST allow multiple Assertions that conflict with each other to coexist, and MUST preserve the underlying SourceClaims for each side.

#### Scenario: Conflicting Assertions coexist
- **WHEN** two different sources assert incompatible facts about the same event
- **THEN** the system stores both Assertions
- **THEN** each Assertion remains traceable to its SourceClaims
