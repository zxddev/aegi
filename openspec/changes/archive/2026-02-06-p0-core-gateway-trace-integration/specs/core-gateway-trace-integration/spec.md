## ADDED Requirements

### Requirement: Core SHALL persist gateway policy outcome in ToolTrace
When `aegi-core` invokes a gateway tool and records a ToolTrace, it MUST persist the gateway policy outcome in `tool_traces.policy`.

#### Scenario: Successful archive_url call records policy
- **WHEN** core calls gateway tool `archive_url` and records a ToolTrace
- **THEN** `tool_traces.policy.allowed` is present
- **THEN** `tool_traces.policy.domain` is present when applicable

#### Scenario: Denied archive_url call still records trace
- **WHEN** core calls gateway tool `archive_url` and gateway denies the request
- **THEN** core still records a ToolTrace linked to the Action
- **THEN** ToolTrace status is `denied` and includes policy/error metadata

### Requirement: Gateway tool success responses MUST include policy metadata
For 2xx tool responses, the gateway MUST include a `policy` object in the response payload.

#### Scenario: archive_url success response includes policy
- **WHEN** gateway returns a 2xx response from `/tools/archive_url`
- **THEN** the JSON body includes `policy.allowed`, `policy.domain`, and `policy.robots`
