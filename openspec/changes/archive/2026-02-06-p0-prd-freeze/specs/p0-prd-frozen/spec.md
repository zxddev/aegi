## ADDED Requirements

### Requirement: PRD SHALL define exactly three P0 end-to-end user flows
The PRD MUST define exactly three P0 end-to-end user flows and their acceptance criteria. Each flow MUST be verifiable offline using fixtures only.

#### Scenario: Reviewer can identify the three P0 flows
- **WHEN** a reviewer opens the PRD
- **THEN** the PRD contains a section listing exactly three P0 user flows

### Requirement: P0 SHALL be fixtures-only for acceptance and regression
P0 acceptance testing MUST NOT require live internet access or live third-party services. P0 MUST ship a fixtures pack sufficient to run all acceptance scenarios offline.

#### Scenario: Run P0 regression without network access
- **WHEN** regression tests are executed in an environment without internet
- **THEN** they complete using fixtures only

### Requirement: PRD MUST specify Scope and Non-goals for P0
The PRD MUST explicitly define the P0 scope and non-goals so that implementation cannot expand implicitly.

#### Scenario: Non-goals are explicitly listed
- **WHEN** a reviewer opens the PRD
- **THEN** there is a Non-goals section with explicit exclusions for P0

### Requirement: PRD MUST define P0 DoD (Definition of Done)
The PRD MUST define a P0 DoD that includes at minimum: offline regression, evidence-chain traceability, and governance constraints.

#### Scenario: DoD is checkable
- **WHEN** a reviewer reads the Milestones/DoD section
- **THEN** the DoD is expressed as checkable criteria
