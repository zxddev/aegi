## ADDED Requirements

### Requirement: Gateway MUST emit ToolTrace for each tool invocation
Each tool invocation MUST produce a ToolTrace record capturing inputs, outputs (or result refs), status, duration, and errors.

#### Scenario: ToolTrace exists for a call
- **WHEN** a tool endpoint is called
- **THEN** a ToolTrace record is created

### Requirement: ToolTrace MUST be linked to a policy decision outcome
Each ToolTrace MUST include a link or embedded fields capturing the policy decision outcome.

#### Scenario: ToolTrace includes policy outcome
- **WHEN** a tool call is allowed or denied
- **THEN** the tool trace includes the policy outcome and reason
