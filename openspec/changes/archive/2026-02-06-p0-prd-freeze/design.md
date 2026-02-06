## Context

当前 P0 的架构不变量与技术路线在以下文档里已经写得比较清楚，但 PRD 本身仍是 TODO：
- `docs/foundry/v0.2/technical-architecture.md`
- `docs/foundry/v0.2/implementation-architecture.md`
- `docs/foundry/v0.2/prd.md`（目前大段 TODO）

本 change 的工作是“冻结需求合同”，而不是做实现：
- 输出一个可以评审与签字的 P0 PRD（3 个用户流 + DoD + 边界）
- 确保 P0 选择 `fixtures-only`：所有验收用离线 fixtures 完成
- 明确领域焦点（国际防务/地缘事件）只影响 fixtures 与用例，不强迫 P0 ontology 变成防务专用

## Goals / Non-Goals

**Goals:**
- 明确 P0 的 3 个端到端用户流（离线可演示）
- 明确 P0 DoD：通过哪些离线回归与指标门禁才算“完成”
- 明确 Scope/Non-goals：避免 scope 漂移
- 明确 P0 合规与边界：robots/ToS、license_note、PII、retention 的最低要求（进入后续 gateway policy change）

**Non-Goals:**
- 不在本 change 中实现任何 API/数据库/网关策略（这些会在后续 change 中做）
- 不在 P0 中接入真实外部工具（SearxNG/ArchiveBox/Unstructured 等）
- 不在 P0 中引入领域专用“防务本体”类型（只做通用最小集合 + 扩展位）

## Decisions

### Decision 1: P0 选择 fixtures-only

**选择**：P0 的验收与回归只依赖固定 fixtures（归档产物 + 解析产物 + 预期 anchors/claims）。

**理由**：先把证据链合同与可回放性做成硬门禁，避免外网/站点变化/反爬导致验收不可复现。

### Decision 2: 领域焦点不等于本体锁死

**选择**：P0 用例/fixtures 聚焦国际防务/地缘事件，但 ontology 先只冻结通用最小集合（Person/Org/Location/Event/Doc/Claim 等），防务专有类型作为 P1+ 扩展。

**理由**：保持平台通用性与可演进；领域扩展通过 profile/attributes/扩展位完成。

### Decision 3: PRD 冻结优先于实现

**选择**：先把 `docs/foundry/v0.2/prd.md` 的 TODO 全部替换为可验收条目，并把 3 个用户流写成“可测试场景”。

**理由**：PRD 未冻结会直接导致实现无边界、回归无门禁。

## Risks / Trade-offs

- **[Risk] fixtures-only 被误解为“不需要真实集成”】【Mitigation】明确将“真服务集成”放入 P0.1/P1 的独立 change（gateway adapters），但不阻塞 P0 验收。
- **[Risk] 领域焦点导致需求膨胀】【Mitigation】PRD 明确 Non-goals：P0 不做全域情报、不开箱即用多数据源；只做 3 个用户流闭环。
- **[Risk] 合规条款停留在口号】【Mitigation】把 robots/ToS、license、PII、retention 写成 PRD 的 NFR + 后续 gateway policy specs 的可测试场景。
