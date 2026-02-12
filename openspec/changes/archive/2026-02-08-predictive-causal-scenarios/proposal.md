<!-- Author: msq -->

## Why

预测/因果/情景推演属于高风险能力，需要单独严格定义可解释与风控门禁。

## What Changes

- 新增因果一致性检查、预警评分、情景分支输出。
- 增加回测框架与失败降级策略，禁止“无依据预测”。

## Capabilities

### New Capabilities

- `predictive-causal-scenarios`

## Dependencies

- Hard dependency: `foundation-common-contracts`
- Soft dependency: `knowledge-graph-ontology-evolution`（P2 增强）
- Hard dependency: `ach-hypothesis-analysis`
- Soft dependency: `narrative-intelligence-detection`

## Impact

- `code/aegi-core/src/aegi_core/services/causal_reasoner.py`
- `code/aegi-core/src/aegi_core/services/predictive_signals.py`
- `code/aegi-core/src/aegi_core/services/scenario_generator.py`
- `code/aegi-core/src/aegi_core/api/routes/forecast.py`
- `code/aegi-core/tests/test_causal_predictive_scenarios.py`
