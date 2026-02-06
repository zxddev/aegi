## ADDED Requirements

### Requirement: Gateway MUST be deny-by-default for outbound domains
Requests targeting domains not explicitly allowed MUST be rejected.

#### Scenario: Unlisted domain is denied
- **WHEN** a request targets an unlisted domain
- **THEN** the gateway denies it with a policy error

### Requirement: Gateway MUST record robots/ToS decision metadata
For any outbound request, the gateway MUST record whether robots/ToS checks were performed and the decision outcome.

#### Scenario: Robots decision is recorded
- **WHEN** a tool request is processed
- **THEN** the audit record includes robots/ToS decision metadata

### Requirement: Gateway SHALL support rate limiting and caching policies
The gateway MUST support rate limiting and caching policy knobs (exact algorithms may evolve).

#### Scenario: Rate limit policy can deny requests
- **WHEN** requests exceed configured limits
- **THEN** the gateway denies further requests with a structured error
