<!-- Author: msq -->

## ADDED Requirements

### Requirement: Shared schema migrations MUST have single owner
共享 schema migration MUST 由 schema 协调者统一生成和合并，避免 Alembic down_revision 分叉。

#### Scenario: Feature branch needs schema change
- **WHEN** 功能分支发现 schema 缺口
- **THEN** 提交 schema-change-request，而不是直接创建新 migration

### Requirement: Post-foundation feature branches MUST be migration-free by default
foundation 完成后，功能分支默认不改 Alembic revision，除非协调者明确授权。

#### Scenario: Unauthorized migration is blocked
- **WHEN** 功能分支提交新的 Alembic revision
- **THEN** CI 标记为违反迁移所有权策略
