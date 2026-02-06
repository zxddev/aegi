## ADDED Requirements

### Requirement: Core MUST route all external tool calls through the gateway
`aegi-core` MUST NOT call external tools/services directly. All external access MUST go through `aegi-mcp-gateway` using stable tool endpoints.

#### Scenario: Core uses gateway for meta_search
- **WHEN** `aegi-core` performs a meta search
- **THEN** it calls `aegi-mcp-gateway` `/tools/meta_search`
- **THEN** the tool invocation is recorded in ToolTrace

### Requirement: Gateway MUST enforce deny-by-default policies
The gateway MUST enforce a deny-by-default policy for outbound access. Domains not explicitly allowed MUST be rejected.

#### Scenario: Blocked domain is rejected
- **WHEN** a tool request targets a domain not in the allowlist
- **THEN** the gateway rejects the request with a structured policy error

### Requirement: Gateway MUST record tool audit metadata
The gateway MUST capture enough metadata for audit and replay:
- inputs (normalized)
- outputs (or result reference)
- timing, status, and errors
- policy decision outcome

#### Scenario: Policy decision is captured for tool call
- **WHEN** a tool request is allowed or denied
- **THEN** the gateway records the policy decision outcome alongside the tool trace
