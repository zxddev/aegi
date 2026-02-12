<!-- Author: msq -->

## 1. 依赖检查

- [x] 1.1 验证 KG/ACH 的输入合同可用
- [x] 1.2 对 Narrative 依赖缺失时启用降级路径

## 2. 核心服务

- [x] 2.1 新增 `services/causal_reasoner.py`
- [x] 2.2 新增 `services/predictive_signals.py`
- [x] 2.3 新增 `services/scenario_generator.py`

## 3. API 与风控

- [x] 3.1 新增 forecast generate/backtest/explain API
- [x] 3.2 增加高风险自动 HITL 门禁
- [x] 3.3 增加证据不足降级输出

## 4. 测试

- [x] 4.1 新增 `test_causal_predictive_scenarios.py`
- [x] 4.2 增加 `defgeo-forecast-001/002/003` fixtures
- [x] 4.3 覆盖 backtest 成功/失败与降级场景
