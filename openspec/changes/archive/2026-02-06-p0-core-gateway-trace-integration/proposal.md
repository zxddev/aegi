## Why

P0 需要“可回放的工具审计链”。目前 gateway 只在 tool trace 内存记录 policy outcome，而 core 已把 ToolTrace 落库，但真实 core→gateway 调用时 response 未携带 policy，导致 core 落库的 policy 为空，审计链断裂。

## What Changes

- Gateway tool responses（至少 `archive_url`）在 2xx 情况下返回 `policy` 元数据（allowed/domain/robots/cache/rate-limit knobs）
- Core 在调用 gateway 工具后，将 response 中的 `policy` 落入 `tool_traces.policy`
- 增加一条跨服务（in-process）回归测试：core 调用真实 gateway stub 并验证 tool_traces.policy 非空

## Capabilities

### New Capabilities
- `core-gateway-trace-integration`: Core <-> Gateway tool call integration preserves policy outcome for audit replay

### Modified Capabilities

- `gateway-tool-contracts-p0`: Gateway tool success responses include policy metadata

## Impact

- `code/aegi-mcp-gateway/`: `/tools/archive_url` response payload
- `code/aegi-core/`: tool call recording path + integration regression test
