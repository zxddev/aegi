## Why

我们要做的不是“多智能体写报告”，而是一个 **证据链驱动（Evidence-first + Archive-first）** 的 OSINT 工作台平台。
当前仓库已经有 v0.2 的架构文档（不变量/分层/证据链合同），也已经开始搭建 `aegi-core` 与 `aegi-mcp-gateway` 的代码骨架，但仍缺少“从需求到可验收闭环”的完整工程规划与可回归的 P0 端到端闭环。

核心问题：如果没有强制的 `SourceClaim → Evidence → ArtifactVersion` 回源链路、Action-only writes 与工具治理（robots/限流/审计），平台会迅速退化为“不可复核的写作器”。

## What Changes

以 OpenSpec Change 的形式把 AEGI Foundry v0.2 的“需求研究 → P0 闭环 → P1/P2/P3 演进”固化为可执行的 artifacts：

- 冻结 P0 的 3 个用户流（离线可演示、可回归）与 DoD
- 在 monorepo `code/` 下推进两条主线：
  - `code/aegi-mcp-gateway/`：工具平面（外联治理 + 适配器 + tool trace）
  - `code/aegi-core/`：控制/数据平面（Case/Evidence/Claims/Actions/Audit + pipelines）
- 统一端口段：本项目专用 `87xx`（避免端口冲突与运维混乱）
- 以 fixtures 驱动的回归：无外网也能验证证据链、锚点定位与抽取质量

## Capabilities

### New Capabilities

- `evidence-first-ingest`: Search/URL → Archive → Parse → Chunk(anchor_set/health) → Evidence
- `source-claim-first`: 从 chunk 抽取 SourceClaim（quote + selectors + attribution + modality），禁止无 selectors 的输出
- `action-only-writes`: 所有关键写入通过 Action（审计/回放/回滚基础）
- `tool-governance`: 工具调用统一从 gateway 出口（allowlist/robots/限流/缓存/审计）
- `offline-regression`: 固定 fixtures 包与指标（anchor locate/drift、claim grounding 等）

### Modified Capabilities

- `docs`: 将现有架构文档的“原则”落成 PRD 可验收条目与工程任务

## Impact

- `docs/foundry/v0.2/prd.md`: 从 TODO 变成可验收合同（P0/P1 里程碑）
- `docs/ops/ports.md`: 87xx 端口段统一与启动手册
- `openspec/changes/aegi-foundry-v0-2/*`: proposal/design/tasks（本 change 作为主规划载体）
- `docker-compose.yml` + `.env.example`: 87xx 端口映射与最小依赖（Postgres/MinIO）
- `code/aegi-core/`: 数据模型/迁移/API/pipelines/tests
- `code/aegi-mcp-gateway/`: 工具契约/策略/审计/适配器/tests
