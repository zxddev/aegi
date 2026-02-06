## ADDED Requirements

### Requirement: All state changes MUST be recorded as Actions
The system MUST record an `Action` for every operation that creates, updates, or deletes any authoritative record (Case, Artifact*, Chunk, Evidence, SourceClaim, Assertion). An Action MUST include:
- `action_type`
- `actor_id` (or a system actor)
- `rationale` (may be empty, but the field MUST exist)
- `inputs` and `outputs` payloads

#### Scenario: Creating a Case produces an Action
- **WHEN** a user creates a Case
- **THEN** the system creates an Action with `action_type` describing the operation
- **THEN** the Action outputs include the created `case_uid`

#### Scenario: Mutations without Action context are rejected
- **WHEN** a mutation is attempted without creating an Action
- **THEN** the system rejects the mutation and records an audit error

### Requirement: Tool traces MUST be linked to Actions
The system MUST record a `ToolTrace` for every tool invocation and MUST link it to the Action that triggered it. ToolTrace MUST include:
- tool name
- request/response metadata
- status and duration
- error (if any)

#### Scenario: Tool invocation records a ToolTrace
- **WHEN** a tool call is executed via `aegi-mcp-gateway`
- **THEN** the system records a ToolTrace with status and duration
- **THEN** the ToolTrace is linked to the triggering Action
