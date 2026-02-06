<!-- Author: msq -->

## 1. 数据与接口

- [ ] 1.1 新增 `db/models/hypothesis.py`（不新增私有 schema，复用 foundation 合同）
- [ ] 1.2 新增 `api/routes/hypotheses.py`（generate/score/explain）

## 2. 推理引擎

- [ ] 2.1 实现 `services/hypothesis_engine.py`（支持/反证/缺口）
- [ ] 2.2 实现 `services/hypothesis_adversarial.py`（Defense/Prosecution/Judge）
- [ ] 2.3 评分输出覆盖率、置信度、冲突解释

## 3. 审计与治理

- [ ] 3.1 记录 hypothesis 推理 trace_id 与 prompt_version
- [ ] 3.2 对无证据支持的结论强制降级

## 4. 回归测试

- [ ] 4.1 新增 `test_ach_hypothesis_engine.py`
- [ ] 4.2 新增 `defgeo-ach-001/002/003` fixtures
- [ ] 4.3 验证支持/反证/缺口输出完整
