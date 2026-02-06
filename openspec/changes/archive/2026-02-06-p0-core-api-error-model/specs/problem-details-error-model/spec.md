## ADDED Requirements

### Requirement: API MUST use a unified structured error response
All non-2xx responses MUST use a unified structured error response with at least:
- `error_code` (stable identifier)
- `message`
- `details` (object)
- `trace_id` (string, optional)

#### Scenario: Not found returns structured error
- **WHEN** a client requests a non-existent UID
- **THEN** the response contains `error_code`, `message`, and `details`

#### Scenario: Validation error returns structured error
- **WHEN** a client sends invalid input
- **THEN** the response contains a stable `error_code` and validation details
