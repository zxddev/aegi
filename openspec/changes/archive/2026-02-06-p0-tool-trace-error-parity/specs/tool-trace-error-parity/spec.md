## ADDED Requirements

### Requirement: Core SHALL persist ToolTrace for rate-limited archive_url calls
When archive_url fails with a rate-limited policy error, core MUST persist a ToolTrace linked to the triggering Action and mark status as `denied`.

#### Scenario: 429 rate-limited call records denied trace
- **WHEN** archive_url call fails with `rate_limited`
- **THEN** a ToolTrace is persisted with `status = denied`
- **THEN** ToolTrace `error = rate_limited`

### Requirement: Core SHALL persist ToolTrace for generic gateway errors
When archive_url fails with a non-policy gateway error, core MUST persist a ToolTrace and mark status as `error`.

#### Scenario: gateway_error call records error trace
- **WHEN** archive_url call fails with `gateway_error`
- **THEN** a ToolTrace is persisted with `status = error`
- **THEN** ToolTrace `error = gateway_error`
