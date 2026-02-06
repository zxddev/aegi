## Context

技术架构与实现架构均把 Ontology 作为对象平台的核心支撑：
- 版本化（ontology_versions）
- 兼容性报告（breaking/deprecate/migrate/remove）
- case pinning（每个 case 固定 ontology_version，升级需 Action 审批）

本 change 将把这些原则冻结为 P0 的最小合同。

## Goals / Non-Goals

**Goals:**
- 定义 P0 最小 ontology（通用集合）
- 定义 extension points（不强迫 P0 内置防务专有类型）
- 定义 ontology versioning + case pinning + compatibility 的规范化行为
- 定义与 STIX/MISP 的映射边界（未来导入导出）

**Non-Goals:**
- 不在本 change 中实现 STIX/TAXII 或 MISP 的真实集成
- 不在 P0 中追求完整领域覆盖（防务扩展放 P1+）

## Decisions

### Decision 1: P0 ontology 仅冻结“通用最小集合”

P0 最小类型集合建议：
- Entity: Person, Organization, Location
- Event: Event (typed via category)
- Artifact/Doc: Document (or Source)
- Claim: SourceClaim / Assertion（由证据链模型承载）

领域专有类型（WeaponSystem/Unit/Installation 等）通过 extension points（tags/attributes/type registry）在 P1+ 引入。

### Decision 2: Ontology 版本化必须可审计

任何 ontology 变更都必须：
- 生成 compat report
- 通过 Action 审批
- 支持 case pinning 与逐 case 升级

## Risks / Trade-offs

- **[Risk] 类型过少导致表达力不足】【Mitigation】用 category/attributes 承载领域差异；P1+ 再引入强类型。
- **[Risk] 过早引入 STIX 全量复杂度】【Mitigation】仅冻结映射边界与最小对应关系，避免 P0 被标准绑架。
