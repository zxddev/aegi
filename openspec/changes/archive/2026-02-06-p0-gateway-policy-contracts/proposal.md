## Why

AEGI 的外联必须通过 `aegi-mcp-gateway` 统一治理（deny-by-default），否则 robots/ToS、限流、缓存、审计与可回放性都无法工程化。P0 虽然采用 fixtures-only，但仍需要冻结 gateway 的工具契约与策略合同，避免后续接入真实工具时破坏系统不变量。

## What Changes

- 冻结 gateway 的工具端点合同（/tools/*）与统一错误形状
- 冻结 deny-by-default 策略：域名 allowlist、robots/ToS 记录、限流、缓存、审计字段
- 冻结 tool_trace 记录要求与 policy decision 关联要求

## Capabilities

### New Capabilities
- `gateway-tool-contracts-p0`: P0 gateway tool endpoints and schemas
- `gateway-deny-by-default-policy`: Domain/tool policy contract (allowlist/robots/rate-limit/cache)
- `gateway-audit-tool-trace`: ToolTrace + policy decision requirements for audit/replay

### Modified Capabilities

（无）

## Impact

- `code/aegi-mcp-gateway/`：routes/policy/audit（实现阶段）
- `code/aegi-core/`：ToolClient 依赖稳定契约
