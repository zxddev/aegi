<!-- Author: msq -->

## ADDED Requirements

### Requirement: Ontology changes MUST be versioned and auditable
本体变更 MUST 带版本、兼容性报告与审计记录。

#### Scenario: Upgrade emits compatibility report
- **WHEN** 执行 ontology upgrade
- **THEN** 返回 compatible/deprecated/breaking 分类结果

### Requirement: KG mapping MUST consume frozen assertion schema
图谱映射 MUST 以 foundation + claim-extraction 冻结后的 Assertion schema 为准。

#### Scenario: Schema mismatch blocks graph build
- **WHEN** Assertion 输入与冻结 schema 不兼容
- **THEN** 拒绝构图并返回 schema mismatch 错误

### Requirement: Case ontology pinning MUST be enforceable
每个 case MUST 固定 ontology_version，跨版本读取需审批。

#### Scenario: Unauthorized version jump is denied
- **WHEN** 未经审批请求切换 ontology_version
- **THEN** 返回 deny 并记录 Action 审计
