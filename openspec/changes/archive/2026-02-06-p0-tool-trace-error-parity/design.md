## Context

当前 `POST /cases/{case_uid}/tools/archive_url` 在 core 中会：
- 成功路径写 ToolTrace(status=ok)
- AegiHTTPError 路径写 ToolTrace(status=denied|error)

现有回归仅覆盖成功与 403 deny。需要补齐 429 与通用 gateway_error 的状态映射验证。

## Goals / Non-Goals

**Goals:**
- 冻结并验证 429 映射为 `denied`
- 冻结并验证非 403/429 的网关错误映射为 `error`

**Non-Goals:**
- 不改 gateway API 契约
- 不引入新端点

## Decisions

- 使用 fake tool client 注入 AegiHTTPError，不依赖外网或真实服务。

## Risks / Trade-offs

- **[Risk] 仅测试 fake client 与真实 tool client 行为偏差** → Mitigation: 保持错误对象一致（AegiHTTPError）并覆盖 status/error 字段断言。
