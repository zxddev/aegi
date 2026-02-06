## ADDED Requirements

### Requirement: Gateway SHALL expose stable tool endpoints
The gateway MUST expose stable tool endpoints (even if stubbed in P0):
- `POST /tools/meta_search`
- `POST /tools/archive_url`
- `POST /tools/doc_parse`

#### Scenario: Tool endpoint exists and returns structured response
- **WHEN** a client calls a tool endpoint
- **THEN** the response contains an `ok` field

### Requirement: Gateway errors MUST use the unified error model
Gateway non-2xx responses MUST use the unified structured error response.

#### Scenario: Policy denied returns structured error
- **WHEN** a request is denied by policy
- **THEN** the response contains `error_code` and `details`
