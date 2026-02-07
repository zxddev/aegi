<!-- Author: msq -->

## 1. 数据与接口

- [x] 1.1 新增 `db/models/narrative.py` 与 Narrative 关系映射
- [x] 1.2 新增 `api/routes/narratives.py`（build/detect/trace）

## 2. 引擎实现

- [x] 2.1 实现 `services/narrative_builder.py`（聚类 + 溯源）
- [x] 2.2 实现 `services/coordination_detector.py`（协同检测）
- [x] 2.3 输出协同误报解释字段

## 3. 测试

- [x] 3.1 新增 `test_narrative_detection.py`
- [x] 3.2 增加 `defgeo-narrative-001/002/003` fixtures
- [x] 3.3 验证叙事回放和冲突并存
