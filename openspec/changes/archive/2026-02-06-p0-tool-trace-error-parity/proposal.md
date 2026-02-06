## Why

`aegi-core` 已在 archive_url 工具调用的成功和 403 deny 路径记录 ToolTrace，但尚未明确验证 429 rate_limited 与通用 gateway_error 的状态映射和持久化行为。需要把错误路径审计语义补齐为可回归合同。

## What Changes

- 定义并验证 archive_url 工具调用在不同错误类别下的 ToolTrace 状态映射
- 增加回归测试覆盖 429 (`denied`) 与 5xx/通用网关错误 (`error`) 的落库行为

## Capabilities

### New Capabilities
- `tool-trace-error-parity`: ToolTrace persistence and status parity across denied and error classes

### Modified Capabilities

- `core-gateway-trace-integration`: expand from success+403 to full error-path parity (429 and generic gateway errors)

## Impact

- `code/aegi-core/tests/test_tool_trace_recording.py`
- (if needed) `code/aegi-core/src/aegi_core/api/routes/cases.py`
