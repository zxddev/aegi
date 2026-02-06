<!-- Author: msq -->

## 1. 依赖检查

- [ ] 1.1 验证 KG/ACH 的输入合同可用
- [ ] 1.2 对 Narrative 依赖缺失时启用降级路径

## 2. 核心服务

- [ ] 2.1 新增 `services/causal_reasoner.py`
- [ ] 2.2 新增 `services/predictive_signals.py`
- [ ] 2.3 新增 `services/scenario_generator.py`

## 3. API 与风控

- [ ] 3.1 新增 forecast generate/backtest/explain API
- [ ] 3.2 增加高风险自动 HITL 门禁
- [ ] 3.3 增加证据不足降级输出

## 4. 测试

- [ ] 4.1 新增 `test_causal_predictive_scenarios.py`
- [ ] 4.2 增加 `defgeo-forecast-001/002/003` fixtures
- [ ] 4.3 覆盖 backtest 成功/失败与降级场景
