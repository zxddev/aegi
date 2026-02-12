<!-- Author: msq -->

## 1. 依赖检查

- [x] 1.1 验证 `automated-claim-extraction-fusion` 已冻结 Assertion schema
- [x] 1.2 若 schema 缺口，提交 schema-change-request（不直接改 migration）

## 2. 数据与服务

- [x] 2.1 新增 `entity.py/event.py/relation.py` 模型
- [x] 2.2 新增 `services/kg_mapper.py`（Assertion -> Graph）
- [x] 2.3 新增 `services/ontology_versioning.py`（version + compatibility report）

## 3. API

- [x] 3.1 新增 `POST /kg/build_from_assertions`
- [x] 3.2 新增 `POST /ontology/upgrade`
- [x] 3.3 新增 `GET /ontology/{version}/compatibility_report`

## 4. 测试

- [x] 4.1 新增 `test_kg_mapping_and_ontology_versioning.py`
- [x] 4.2 增加 `defgeo-kg-001/002/003` fixtures
- [x] 4.3 覆盖兼容/弃用/破坏三种升级路径
