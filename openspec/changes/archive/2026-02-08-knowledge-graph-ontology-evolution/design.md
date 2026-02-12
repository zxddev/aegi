<!-- Author: msq -->

## Decisions

1. 本体变更必须生成 compatibility_report。
2. case pinning 与升级通过 Action 审批。
3. KG 映射必须消费已冻结的 Assertion schema，不允许独立定义冲突字段。

## Input / Output Contracts

- 输入：`AssertionV1[]`（必须包含结构化 `subject/predicate/object` 或可映射字段）
- 输出：`EntityV1[]`、`EventV1[]`、`RelationV1[]`
- 本体输出：`ontology_version`、`compatibility_report`、`migration_plan`

## API Contract

- `POST /cases/{case_uid}/kg/build_from_assertions`
- `POST /cases/{case_uid}/ontology/upgrade`
- `GET /cases/{case_uid}/ontology/{version}/compatibility_report`

## Mapping Rules

1. Assertion 中可识别实体映射为 Entity 节点。
2. 事件类 Assertion 映射为 Event 节点。
3. 关系由 predicate 规范化映射 Relation 边。

## Fixtures

- `defgeo-kg-001`：稳定 SPO 映射
- `defgeo-kg-002`：本体升级兼容
- `defgeo-kg-003`：breaking 变更需拒绝自动升级

## Acceptance

1. KG 构建可回放到 Assertion 与 SourceClaim。
2. 兼容性报告必须包含 compatible/deprecated/breaking 分类。
3. case pinning 生效，未经审批不得越版本读取。
