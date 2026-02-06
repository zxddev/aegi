## 1. Gateway Response Contract

- [x] 1.1 Include `policy` in 2xx `/tools/archive_url` response payload
- [x] 1.2 Add a gateway unit test asserting policy is present in success response

## 2. Core Persistence + Regression

- [x] 2.1 Add a core integration regression test (in-process gateway) to assert ToolTrace.policy is non-empty
- [x] 2.2 Ensure core stores gateway policy into `tool_traces.policy` for archive_url calls
- [x] 2.3 Ensure core stores ToolTrace for denied/error archive_url calls
