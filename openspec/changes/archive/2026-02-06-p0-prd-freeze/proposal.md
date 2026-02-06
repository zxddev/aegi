## Why

`docs/foundry/v0.2/prd.md` 仍是 draft 且核心章节为 TODO，导致实现会变成“写到哪算哪”。我们需要先把 P0 的需求冻结成可验收合同，才能进入开发与回归门禁。

P0 选择 `fixtures-only`（离线可回归）策略：先验证证据链合同与治理边界，不被外网与第三方服务稳定性拖慢。

## What Changes

- 将 P0 需求冻结为 3 个端到端用户流（离线可演示）与 DoD（Definition of Done）
- 明确 P0 的范围边界（Scope/Non-goals）与合规约束（robots/ToS、license_note、PII、retention）
- 明确 P0 的领域焦点：国际防务/地缘事件（影响 fixtures 主题与用例），但本体（ontology）保持“通用最小集合 + 可扩展位”
- 将上述冻结内容写入 PRD：`docs/foundry/v0.2/prd.md`

## Capabilities

### New Capabilities
- `p0-prd-frozen`: P0 scope/user-flows/DoD freeze as a reviewable, testable contract
- `p0-domain-profile-defense`: Defense/geopolitics domain profile (fixtures + examples), without forcing domain-specific ontology in P0

### Modified Capabilities

（无；当前 `openspec/specs/` 为空，本次只新增）

## Impact

- 文档：`docs/foundry/v0.2/prd.md`（从 TODO 变为可验收条目）
- 规划：`openspec/changes/p0-prd-freeze/specs/*`（P0 冻结合同的规范化表达）
- 后续 change 将依赖本 change 的冻结输出（P0 fixtures/metrics、ontology、API/error model、gateway policy）
