## Why

AEGI Foundry 的对象平台需要一个最小可用本体（ontology）来保证：
- Assertion/Entity/Event 的结构化表达一致
- 版本化与兼容性（case pinning）可审计
- 未来可与 STIX/MISP 等互操作，但不要求 P0 全覆盖

当前架构文档已描述 ontology 服务与版本化思路，但尚未冻结 P0 的最小集合与扩展位策略。

## What Changes

- 冻结 P0 的最小 ontology（通用集合 + 扩展位），不锁死为防务专用
- 冻结 ontology versioning、compatibility、case pinning 的行为合同
- 冻结与 STIX/MISP 的“映射边界”（P2 做 import/export，但 P0 要预留字段与语义）

## Capabilities

### New Capabilities
- `mvp-ontology`: Minimal general ontology for P0 with extension points
- `ontology-versioning`: Ontology versions, compatibility reporting, and case pinning
- `interop-mapping-boundary`: Mapping boundary notes for future STIX/MISP interop

### Modified Capabilities

（无）

## Impact

- 规范：`openspec/changes/p0-mvp-ontology/specs/*`
- 后续实现：`code/aegi-core/ontology/`（YAML/JSON）与 `ontology_versions` 等表将以本 change 为合同来源
