## Context

AEGI Foundry v0.2 的核心合同与不变量在下列文档里已明确：
- `docs/foundry/v0.2/technical-architecture.md`
- `docs/foundry/v0.2/implementation-architecture.md`

本 change 的目标是把这些“原则”变成：
1) 可验收的 PRD（P0/P1 里程碑）
2) 可执行的工程任务（含验证命令与离线 fixtures）
3) 端到端闭环：`Judgment → Assertion → SourceClaim → Evidence → Chunk(anchor_set/health) → ArtifactVersion → ArtifactIdentity`

工程形态：monorepo（`code/`），分两条主线：
- `code/aegi-core/`：权威数据（Postgres）+ 对象存储（MinIO）+ API + pipelines
- `code/aegi-mcp-gateway/`：唯一外联出口 + 工具治理 + tool traces

端口段：本项目统一使用 `87xx`（见 `docs/ops/ports.md` 与根目录 `.env.example`）。

开源参考（只学习/服务化集成，不直接拷贝 AGPL 代码入核心）：
- 元搜索：SearxNG（AGPL，外部服务，经 gateway 调用）
- 归档固化：ArchiveBox（外部服务，经 gateway 调用）
- 文档解析：Unstructured + Tika（外部服务，经 gateway 调用）
- 对象化参照：MISP/OpenCTI（互操作目标，P2 做 import/export）

## Goals / Non-Goals

**Goals (v0.2):**
- P0：离线可回归的证据链闭环（Search/URL -> Archive -> Evidence -> SourceClaim -> Assertion），并且 Action-only + tool trace 有最小实现
- P1：强锚点与 anchor health、SourceClaim 抽取与 Assertion 融合、冲突/不确定性一等公民
- P2：Watchlist/增量更新、MISP/STIX 互操作、Eval-as-a-Product 指标面板
- P3：协作、权限、派生索引（可重建）与规模化

**Non-Goals (P0):**
- 不做“大而全 UI/图谱/向量检索”优先于证据闭环
- 不引入复杂分布式与全家桶；先模块化单体，再拆
- 不绕过 gateway 直连外网

## Decisions

### Decision 1: 端口段统一 87xx

**选择**：本 repo 内所有服务与依赖端口都映射到 `87xx`。

**理由**：避免与系统/其他项目的常用端口冲突；运维识别成本更低；可一键停/启/排障。

### Decision 2: Evidence-first + Archive-first 强制落库

**选择**：任何外部内容必须先成为 `ArtifactVersion`（可校验 hash 与 storage_ref），再解析/切块/引用。

**理由**：没有版本固化，引用无法复核；后续所有“评测/回放/差分”都失效。

### Decision 3: SourceClaim-first 两阶段抽取

**选择**：先产 SourceClaim（贴近原文，必须带 selectors），再融合成 Assertion（可冲突）。

**理由**：保证可解释与可审计；降低模型“总结性幻觉”进入主线的概率。

### Decision 4: AGPL 组件边界

**选择**：AGPL 组件一律“外部服务 + HTTP 调用 + gateway 适配”，不拷贝源码进核心。

**理由**：合规与边界清晰；也符合“工具平面”架构。

## Risks / Trade-offs

- **[Risk] 早期就做多智能体，容易绕开证据链**
  → Mitigation: P0 强制 fixtures + schema 校验 + selectors 约束；所有输出必须带证据。

- **[Risk] 锚点漂移导致引用不可用**
  → Mitigation: anchor_set 冗余选择器 + anchor_health；漂移检测进入质量闸门与回归。

- **[Risk] 需求不冻结导致 scope 膨胀**
  → Mitigation: PRD 先冻结 3 个 P0 用户流 + DoD；其它需求排入 P1+。

## Migration Plan

1) 需求研究：把 `docs/foundry/v0.2/prd.md` 的 TODO 全部变成可验收条目（围绕 P0 3 个用户流）。
2) P0：打通离线闭环（fixtures 驱动），只做最小 API 与数据结构。
3) P1：强锚点/claim extraction/fusion/conflict。
4) P2：watchlist + interop + eval。
5) P3：协作/权限/派生索引重建与规模化。

## Open Questions

1) P0 的“最小本体（ontology）”要覆盖哪些实体/事件类型？（建议先只覆盖 P0 三流必要集合）
2) P0 的 archive/parse 是否必须接入真实服务（SearxNG/ArchiveBox/Unstructured），还是先 fixtures stub？
3) 导出策略：P1 是否就需要可导出 EvidencePackage（manifest+sha+anchor_map）？
