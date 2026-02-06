## ADDED Requirements

### Requirement: PRD MUST define P0 user flows and acceptance criteria
The PRD MUST define the P0 scope as 3 end-to-end user flows, each with clear acceptance criteria and offline regression requirements.

#### Scenario: PRD contains P0 flows
- **WHEN** a reviewer opens `docs/foundry/v0.2/prd.md`
- **THEN** it contains exactly the P0 user flows and their acceptance criteria

### Requirement: Docs MUST remain consistent with the 87xx port segment
Operational documentation MUST use the reserved `87xx` port segment for this repo's services.

#### Scenario: Ports doc matches environment defaults
- **WHEN** a reviewer opens `docs/ops/ports.md`
- **THEN** the documented ports match `.env.example` defaults
