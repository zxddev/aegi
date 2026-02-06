<!-- Author: msq -->

## 1. 依赖检查

- [ ] 1.1 验证 `automated-claim-extraction-fusion` 已冻结 Assertion schema
- [ ] 1.2 若 schema 缺口，提交 schema-change-request（不直接改 migration）

## 2. 数据与服务

- [ ] 2.1 新增 `entity.py/event.py/relation.py` 模型
- [ ] 2.2 新增 `services/kg_mapper.py`（Assertion -> Graph）
- [ ] 2.3 新增 `services/ontology_versioning.py`（version + compatibility report）

## 3. API

- [ ] 3.1 新增 `POST /kg/build_from_assertions`
- [ ] 3.2 新增 `POST /ontology/upgrade`
- [ ] 3.3 新增 `GET /ontology/{version}/compatibility_report`

## 4. 测试

- [ ] 4.1 新增 `test_kg_mapping_and_ontology_versioning.py`
- [ ] 4.2 增加 `defgeo-kg-001/002/003` fixtures
- [ ] 4.3 覆盖兼容/弃用/破坏三种升级路径
