<!-- Author: msq -->

## Decisions

1. 因果结论必须有证据链与替代解释。
2. 情景输出不是单点预测，必须给分支与条件。
3. 高风险结论默认进入 HITL。

## Input / Output Contracts

- 输入：`GraphSnapshotV1`、`HypothesisV1[]`、`NarrativeV1[]`、`IndicatorSeriesV1`
- 输出：`ForecastV1[]`
  - 必填：`scenario_id`、`probability`、`trigger_conditions`、`evidence_citations`、`alternatives`

## API Contract

- `POST /cases/{case_uid}/forecast/generate`
- `POST /cases/{case_uid}/forecast/backtest`
- `GET /cases/{case_uid}/forecast/{scenario_id}/explain`

## Staged Dependency Strategy

### P1 Minimal (without KG hard dependency)

1. 基于 `Assertion` 时序字段 + `Hypothesis` 输出做一致性检查与预警评分。
2. 不依赖图查询引擎即可生成最小情景分支。

### P2 Enhanced (with KG)

1. 接入 KG 路径增强因果链解释与路径搜索。
2. KG 仅增强召回与解释，不替代证据链约束。

## Risk Controls

1. 无证据预测结果禁止输出 probability。
2. 预测必须附替代解释，不允许单因果链闭环。
3. 高风险阈值命中时自动进入 HITL 审批。

## Fixtures

- `defgeo-forecast-001`：可解释预警
- `defgeo-forecast-002`：冲突信号
- `defgeo-forecast-003`：证据不足（应降级）

## Acceptance

1. explain 接口能回放触发指标与证据链。
2. backtest 输出包含成功/失败分解。
3. 证据不足场景不输出强结论。
