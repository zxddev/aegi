## Context

`aegi-mcp-gateway` 已实现 deny-by-default policy 与 tool trace（内存），并在 tool trace 内记录 policy outcome。
`aegi-core` 已实现 ToolTrace 落库与 `POST /cases/{case_uid}/tools/archive_url` 记录 Action+ToolTrace。
但真实 core→gateway 调用时，gateway 2xx response 未携带 `policy`，导致 core 落库的 `tool_traces.policy` 为空。

## Goals / Non-Goals

**Goals:**
- Gateway 的工具 2xx 响应包含 `policy` 元数据（至少 archive_url）
- Core 从 response 中提取 policy 并落库（已存在逻辑，需回归保障）
- 增加一条跨项目（in-process）回归测试，验证 policy 在真实调用链路中不丢失

**Non-Goals:**
- 不把 gateway 的内存 tool trace 同步落库（P0 只要求 core 权威落库）
- 不引入真实外部服务

## Decisions

- 采用“gateway response 携带 policy”作为最小契约：core 无需知道 gateway 的内部 trace 存储。
- 跨服务回归测试使用 `httpx.ASGITransport`，避免起真实网络服务与端口依赖。

## Risks / Trade-offs

- **[Risk] 跨项目 import 带来测试路径依赖** → Mitigation: test 内部显式 sys.path 注入 gateway `src/`，仅用于回归测试。
