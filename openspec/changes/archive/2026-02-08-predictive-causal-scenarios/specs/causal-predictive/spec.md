<!-- Author: msq -->

## ADDED Requirements

### Requirement: Causal outputs MUST be explainable and evidence-linked
因果与预测输出 MUST 包含证据链、假设条件、替代解释。

#### Scenario: Prediction without evidence is downgraded
- **WHEN** 预测结果缺少有效 evidence citations
- **THEN** 输出降级为 hypothesis，不返回高置信 probability

### Requirement: Forecasts MUST include backtest evidence
发布级预测 MUST 附带最近回测结果与失败分解。

#### Scenario: Backtest report is mandatory
- **WHEN** 请求发布 scenario forecast
- **THEN** 返回 backtest_summary（precision/false_alarm/missed_alert）

### Requirement: High-risk predictions MUST pass HITL
高风险预测 MUST 通过人工审批后才可对外可见。

#### Scenario: HITL required for high-risk scenario
- **WHEN** 风险等级达到 high
- **THEN** 状态为 pending_review，未经审批不可发布
