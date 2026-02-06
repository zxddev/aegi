## Context

架构明确要求：外联全部走 MCP Gateway，并记录 robots/ToS、限流与审计。
P0 fixtures-only 不阻塞，但必须先冻结网关契约与策略合同。

## Goals / Non-Goals

**Goals:**
- 冻结工具端点合同与统一错误形状
- 冻结 deny-by-default 的策略要素与最小可审计字段
- 冻结 tool_trace 与 policy decision 的关联要求

**Non-Goals:**
- 不在本 change 中实现真实的 robots 解析器或复杂 WAF
- 不在 P0 中接入真实第三方服务

## Decisions

### Decision 1: Policy 结果必须显式记录

每次工具调用必须产生 policy decision 结果（allow/deny + reason），并与 tool_trace 关联。

### Decision 2: P0 tool contracts 先稳定 schema，再实现 adapter

契约先行可以让 core 与 tests 先稳定，adapter 集成放入后续 change。

## Risks / Trade-offs

- **[Risk] 早期 policy 过于复杂】【Mitigation】P0 只冻结最小合同；实现先从 allowlist + 结构化审计开始。
